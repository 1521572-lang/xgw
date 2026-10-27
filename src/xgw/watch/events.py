"""События сети, сна и правил, которые будят демон раньше очередного шага (Ф2).

Между шагами демон спит interval_s. Пропавшие правила nftables (чужой `flush ruleset`),
моргнувший WAN или пробуждение после сна он раньше замечал только на следующем шаге.
NetEvents слушает три программы — без библиотек, через подпроцессы с обычным пайпом:

- net:   `ip -o monitor link address route` — по строке на событие (текст: -j здесь не
         действует);
- sleep: `busctl monitor --json=short` по сигналу PrepareForSleep systemd-logind;
- rules: `nft monitor` без фильтра — `monitor tables` не видит ни flush table, ни правил.

Все три отдают каждое событие сразу, без буферизации (проверено на iproute2 6.19, nftables
1.1.6, systemd 259; тест test_monitor_events_arrive_while_process_runs). Сам NetEvents
ничего не меняет: он только зовёт wake(причина), а что делать, решает шаг демона.
"""

from __future__ import annotations

import contextlib
import fnmatch
import json
import queue
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable

from .. import log

SOURCES: dict[str, list[str]] = {
    "net": ["ip", "-o", "monitor", "link", "address", "route"],
    "sleep": [
        "busctl", "--system", "monitor", "--json=short",
        "--match=type='signal',interface='org.freedesktop.login1.Manager',"
        "member='PrepareForSleep'",
    ],
    "rules": ["nft", "monitor"],
}
DEBOUNCE = 2.0  # повторы одной причины внутри окна сливаются в одно пробуждение
# Строки одной пачки: `nft flush ruleset` или смена адреса дают их десятки за миллисекунды.
BURST = 0.25
RESTART_PAUSE = 1.0  # подпроцесс вышел — запустить снова через столько…
RESTART_PAUSE_MAX = 30.0  # …удваивая паузу, пока он падает сразу, но не дольше этого
STABLE_RUN = 10.0  # проработал дольше — пауза снова короткая
# Очередь пробуждений с пределом: при буре событий в ней и так есть что разбудить (пятый аудит).
QUEUE_MAX = 256
# Как часто диспетчер смотрит, закончилась ли своя загрузка правил, если в её окне были события.
QUIET_POLL = 0.5
# Интерфейсы, события которых шаг демона не ускоряют: loopback, TUN самого Xray (он
# опускает его при каждом перезапуске) и контейнеры Docker (мосты, veth).
IGNORED_IFS = ("lo", "docker*", "br-*", "veth*")
TABLES = (("ip", "xgw"), ("ip6", "xgw6"))

_LINK = re.compile(r"^(?:Deleted )?\d+: ([^:@\s]+)[@:]")
_ADDR = re.compile(r"^(?:Deleted )?\d+: ([^:@\s]+)\s+inet6? ")
_DEV = re.compile(r"\bdev (\S+)")


def parse_net(line: str, ignored: tuple[str, ...] = IGNORED_IFS) -> str | None:
    """Строка `ip -o monitor` → имя интерфейса, если событие стоит внеочередного шага.

    Стоят: удаление (адреса, маршрута, интерфейса — `Deleted …`), смена состояния линка
    (`state DOWN` / `state UP`) и появление маршрута по умолчанию. Обновление аренды DHCP
    (тот же адрес заново) и маршруты локальной таблицы при добавлении адреса — нет."""
    line = line.strip()
    if not line:
        return None
    match = _LINK.match(line) or _ADDR.match(line) or _DEV.search(line)
    name = match.group(1) if match else ""
    if not name or any(fnmatch.fnmatchcase(name, pattern) for pattern in ignored):
        return None
    if line.startswith("Deleted "):
        return name
    if _LINK.match(line) and re.search(r"\bstate (?:DOWN|UP)\b", line):
        return name
    if line.startswith("default "):
        return name
    return None


def parse_sleep(line: str) -> bool | None:
    """Строка `busctl monitor --json=short` → аргумент PrepareForSleep: True — машина
    засыпает, False — проснулась; None — не тот сигнал или не JSON."""
    try:
        message = json.loads(line)
    except ValueError:
        return None
    if not isinstance(message, dict) or message.get("member") != "PrepareForSleep":
        return None
    data = (message.get("payload") or {}).get("data")
    if isinstance(data, list) and data and isinstance(data[0], bool):
        return data[0]
    return None


def parse_rules(line: str, tables: tuple[tuple[str, str], ...] = TABLES) -> bool:
    """Строка `nft monitor` → убрано ли что-то из таблиц XGW.

    `nft flush table ip xgw` монитор показывает как `delete rule ip xgw <цепочка> handle N`
    по каждому правилу, `flush ruleset` — как `delete table …` по каждой таблице.
    Добавления (в том числе свои загрузки XGW) и чужие таблицы — не повод."""
    words = line.split()
    if len(words) >= 2 and words[0] == "flush" and words[1] == "ruleset":
        return True
    if len(words) < 4 or words[0] not in ("delete", "flush"):
        return False
    return (words[2], words[3]) in tables


class NetEvents:
    """Будит демон на событиях сети, сна и правил; сам ничего не меняет.

    wake(reason) — «net», «sleep» или «rules». quiet_rules() — True, пока события правил
    вызваны своей загрузкой (Capture.ignore_rules_until): их пропускаем. tun_name — TUN
    Xray, его события не учитываются."""

    def __init__(
        self,
        wake: Callable[[str], None],
        runner_popen=subprocess.Popen,
        *,
        quiet_rules: Callable[[], bool] = lambda: False,
        tun_name: str = "",
        sources: dict[str, list[str]] | None = None,
        debounce: float = DEBOUNCE,
        restart_pause: float = RESTART_PAUSE,
        logger=None,
        which=shutil.which,
    ) -> None:
        self.wake = wake
        self.popen = runner_popen
        self.quiet_rules = quiet_rules
        self.ignored = IGNORED_IFS + ((tun_name,) if tun_name else ())
        self.sources = dict(SOURCES if sources is None else sources)
        self.debounce = debounce
        self.restart_pause = restart_pause
        self.log = logger or log.get_logger("events")
        self.which = which
        self._stop = threading.Event()
        self._queue: queue.Queue[str] = queue.Queue(maxsize=QUEUE_MAX)
        # События правил пришли в окне своей загрузки (quiet_rules): среди них могли быть и
        # чужие — когда окно закроется, одна проверка (пятый аудит).
        self._quiet_seen = threading.Event()
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self.started: dict[str, int] = {}  # источник → сколько раз запускали подпроцесс

    # --- запуск и остановка -------------------------------------------------------

    def start(self) -> None:
        for name, argv in self.sources.items():
            if self.which(argv[0]) is None:
                self.log.warning("события %s не отслеживаются: нет программы %s", name, argv[0])
                continue
            self._spawn(f"events-{name}", self._reader, name, argv)
        self._spawn("events-wake", self._dispatch)

    def _spawn(self, title: str, target, *args) -> None:
        thread = threading.Thread(target=target, args=args, name=title, daemon=True)
        thread.start()
        self._threads.append(thread)

    def stop(self) -> None:
        """Останавливает подпроцессы и не ждёт их дольше долей секунды: остановка демона
        (systemctl restart xgw) не должна из-за событий затягиваться."""
        self._stop.set()
        self._put("")  # разбудить диспетчер
        with self._lock:
            procs = list(self._procs.values())
        for proc in procs:
            with contextlib.suppress(OSError):
                proc.terminate()
        deadline = time.monotonic() + 0.5
        for proc in procs:
            with contextlib.suppress(subprocess.TimeoutExpired, OSError):
                proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            if proc.poll() is None:
                with contextlib.suppress(OSError):
                    proc.kill()
        for thread in self._threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))

    # --- чтение ------------------------------------------------------------------

    def _reader(self, name: str, argv: list[str]) -> None:
        """Читает подпроцесс построчно; вышел — запускает снова (nft monitor завершается,
        например, когда netlink переполнен событиями)."""
        pause = self.restart_pause
        while not self._stop.is_set():
            began = time.monotonic()
            try:
                proc = self.popen(
                    argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, text=True, bufsize=1,
                )
            except OSError as exc:
                self.log.warning("события %s не отслеживаются: %s", name, exc)
                proc = None
            if proc is not None:
                self.started[name] = self.started.get(name, 0) + 1
                if self.started[name] > 1 and name in ("rules", "net"):
                    # Подпроцесс перезапущен: события, что пришли без него, потеряны — одна
                    # проверка (пятый аудит).
                    self._put(name)
                with self._lock:
                    self._procs[name] = proc
                if self._stop.is_set():  # остановка пришла между запуском и записью
                    with contextlib.suppress(OSError):
                        proc.terminate()
                with contextlib.suppress(OSError, ValueError):
                    for line in proc.stdout:
                        if self._stop.is_set():
                            break
                        self._line(name, line)
                with contextlib.suppress(OSError):
                    proc.stdout.close()
                with contextlib.suppress(subprocess.TimeoutExpired, OSError):
                    proc.wait(timeout=0.5)
            if self._stop.is_set():
                return
            if time.monotonic() - began >= STABLE_RUN:
                pause = self.restart_pause
            self.log.info("%s завершился — запускаю снова через %.0f с", argv[0], pause)
            if self._stop.wait(pause):
                return
            pause = min(pause * 2, RESTART_PAUSE_MAX)

    def _line(self, name: str, line: str) -> None:
        if name == "net":
            device = parse_net(line, self.ignored)
            if device:
                self.log.debug("событие сети: %s", line.strip()[:160])
                self._put("net")
        elif name == "sleep":
            if parse_sleep(line) is False:
                self.log.info("машина проснулась после сна")
                self._put("sleep")
        elif name == "rules" and parse_rules(line):
            if self.quiet_rules():
                # Своя загрузка правил: события netlink приходят уже после nft -f. Не будить
                # сейчас, но проверить, когда окно закроется.
                self._quiet_seen.set()
                return
            self.log.debug("событие правил: %s", line.strip()[:160])
            self._put("rules")

    def _put(self, reason: str) -> None:
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(reason)

    def _dispatch(self) -> None:
        """Повторы одной причины внутри окна debounce — одно пробуждение. Первое событие
        будит сразу. Строки той же пачки (одна команда — десятки строк подряд, без пауз
        дольше BURST) больше не будят; новая пачка внутри окна — ещё одно пробуждение в его
        конце: второй flush вслед за первым не должен ждать очередного шага."""
        fired: dict[str, float] = {}
        last: dict[str, float] = {}  # когда пришла предыдущая строка этой причины
        burst: set[str] = set()  # причины, чья текущая пачка уже разбудила демон
        pending: set[str] = set()
        while not self._stop.is_set():
            now = time.monotonic()
            due = [fired[reason] + self.debounce - now for reason in pending]
            timeout = max(0.0, min(due)) if due else None
            if self._quiet_seen.is_set():
                timeout = QUIET_POLL if timeout is None else min(timeout, QUIET_POLL)
            try:
                reason = self._queue.get(timeout=timeout)
            except queue.Empty:
                reason = ""
            if self._stop.is_set():
                return
            if self._quiet_seen.is_set() and not self.quiet_rules():
                self._quiet_seen.clear()
                self._put("rules")  # окно своей загрузки закрылось: проверить правила
            now = time.monotonic()
            if reason:
                same_burst = now - last.get(reason, float("-inf")) < BURST
                last[reason] = now
                if now - fired.get(reason, float("-inf")) >= self.debounce:
                    fired[reason] = now
                    pending.discard(reason)
                    burst.add(reason)
                    self._fire(reason)
                elif not (same_burst and reason in burst):
                    burst.discard(reason)
                    pending.add(reason)
            for late in [r for r in pending if now - fired[r] >= self.debounce]:
                pending.discard(late)
                fired[late] = now
                burst.discard(late)
                self._fire(late)

    def _fire(self, reason: str) -> None:
        try:
            self.wake(reason)
        except Exception:  # сбой обработчика не должен останавливать слежение
            self.log.exception("пробуждение демона (%s) не удалось", reason)
