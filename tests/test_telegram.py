"""Бот Telegram: команды из своего чата, защита от чужих и старых сообщений,
подключение чата кодом. Telegram подменён локальным сервером (fake_telegram)."""

import socket
import threading
import time

import fakexray
import pytest
from fake_telegram import BOT_NAME, OWNER, TOKEN, FakeTelegram
from fakenet import FakeKernel

from xgw import actions, config, engine, fetch, managed
from xgw.net import dnsmasq
from xgw.net.capture import Capture
from xgw.paths import Paths
from xgw.watch import status
from xgw.watch import telegram as telegram_module
from xgw.watch.telegram import HELP, PRIVATE_ONLY, Bot, TelegramError, parse_command

GROUP = -100777


def _snapshot() -> dict:
    now = time.time()
    return {
        "updated": now, "daemon": True, "state": "HEALTHY", "action": "", "since": now,
        "xray": {"ok": True, "version": "26.3.27"},
        "capture": {"mode": "on", "lan_if": "lan0", "lan": True, "local": True,
                    "bypass": ["192.168.50.23"], "loaded": True},
        "members": [
            {"tag": "proxy-nl-aaaa", "name": "NL-1", "alive": True, "delay_ms": 80},
            {"tag": "proxy-de-bbbb", "name": "DE-1", "alive": False, "delay_ms": None},
        ],
        "spares": [{"tag": "spare-fi-cccc", "name": "FI-1"}],
        "selecting": ["proxy-nl-aaaa"], "pin": None,
        "quota": {"main": {"upload": 1_000_000_000, "download": 2_000_000_000,
                           "total": 100_000_000_000}},
    }


class Rig:
    def __init__(self, tmp_path, monkeypatch, *, chat: str = str(OWNER), managed_token=False):
        self.fake = FakeTelegram().start()
        self.paths = Paths(root=tmp_path / "root")
        self.paths.ensure()
        fakexray.write(self.paths)  # Xray запущен с inbound'ом перехвата
        self.config_path = self.paths.config_file
        notify = f'telegram_bot_token = "{TOKEN}"\ntelegram_chat_id = "{chat}"\n'
        self.config_path.write_text(
            f'[network]\nlan_if = "lan0"\n[notify]\ntelegram_api = "{self.fake.url}"\n'
            + ("" if managed_token else notify)
            + '\n[[subscriptions]]\nname = "main"\nurl = "https://sub.example.net/s"\n',
            encoding="utf-8",
        )
        if managed_token:
            managed.set_telegram(managed.path_for(self.config_path), TOKEN, chat if chat else "")
        status.write_status(self.paths, _snapshot())
        self.kernel = FakeKernel()
        proc = tmp_path / "proc"
        (proc / "net/ipv4").mkdir(parents=True)
        (proc / "net/ipv4/ip_forward").write_text("0\n", encoding="ascii")
        self.xray_up = True
        monkeypatch.setattr(
            engine, "healthy_http_in", lambda _cfg: ("127.0.0.1", 10809) if self.xray_up else None
        )
        self.root_problem: str | None = None
        self.pinned: list[tuple[str, str]] = []
        self.unpinned = 0

        def fake_pin(cfg, paths, tag, ttl):
            self.pinned.append((tag, ttl))
            return actions.Outcome(0, f"{tag} закреплён на {ttl}")

        def fake_unpin(cfg, paths):
            self.unpinned += 1
            return actions.Outcome(0, "закрепление снято")

        monkeypatch.setattr(actions, "pin", fake_pin)
        monkeypatch.setattr(actions, "unpin", fake_unpin)
        self.daemon = type("Daemon", (), {
            "poke": threading.Event(), "asked": [],
            "request_refresh": lambda s: s.asked.append("refresh"),
            "request_scan": lambda s: s.asked.append("scan"),
            "request_speed": lambda s: s.asked.append("speed"),
        })()
        self.routes: list[str] = []  # каким путём шёл каждый запрос к Bot API

        def post(url, *, proxy=None, **kwargs):
            # Прокси Xray в тестах нет: путь «через Xray» отказывает сразу, не трогая
            # настоящий порт 10809 (на машине разработчика его может занимать чужая
            # программа), и бот идёт напрямую — как при Xray, который не отвечает.
            self.routes.append("xray" if proxy is not None else "direct")
            if proxy is not None:
                assert proxy == ("127.0.0.1", 10809)
                raise fetch.FetchError("прокси Xray в тестах нет")
            return fetch.fetch_url(url, **kwargs)

        self.bot = Bot(
            self.paths, self.config_path, long_poll=0, post=post,
            root_problem=lambda: self.root_problem,
            capture_factory=lambda cfg, paths, **kw: Capture(
                cfg, paths, runner=self.kernel, proc_sys=proc, time_uids=(), **kw),
        )
        self.reload()

    def reload(self) -> config.Config:
        self.cfg, _warnings = config.load(self.config_path)
        self.bot.configure(self.cfg, self.daemon, None)
        return self.cfg

    def poll(self) -> list[str]:
        """Один круг опроса; возвращает все ответы бота."""
        self.bot.poll_once(self.cfg)
        return self.fake.replies()

    def ask(self, text: str, **kwargs) -> str:
        """Сообщение боту → его ответ в тот же чат."""
        before = len(self.fake.sent)
        self.fake.say(text, **kwargs)
        self.bot.poll_once(self.cfg)
        new = self.fake.sent[before:]
        assert len(new) <= 1, new
        return new[0]["text"] if new else ""


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    instance = Rig(tmp_path, monkeypatch)
    yield instance
    instance.fake.stop()


# --- разбор команд -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/status", ("/status", "")),
        ("  /Pin 2 6h ", ("/pin", "2 6h")),
        (f"/pin@{BOT_NAME} 2", ("/pin", "2")),
        (f"/PIN@{BOT_NAME.upper()} 2", ("/pin", "2")),
        ("/pin@another_bot 2", None),  # в группе команда другому боту
        ("привет", None),
        ("status", None),
        ("", None),
    ],
)
def test_parse_command(text, expected):
    assert parse_command(text, BOT_NAME) == expected


# --- чтение состояния --------------------------------------------------------------------------


def test_owner_gets_help_and_status(rig):
    assert rig.ask("/start") == HELP
    text = rig.ask("/status")
    assert "Состояние: HEALTHY" in text and "Xray 26.3.27: отвечает" in text
    assert "Перехват: включён — сеть lan0 и эта машина; мимо VPN: 192.168.50.23" in text
    assert "Серверов в работе: 1 из 2; запасных: 1" in text and "Выбран: NL-1 (80 мс)" in text
    assert "Квота «main»: 3.0 ГБ из 100.0 ГБ" in text
    assert TOKEN not in str(rig.fake.sent)  # токен в ответы не попадает
    assert rig.bot.username == BOT_NAME


def test_servers_are_numbered_for_the_pin_command(rig):
    text = rig.ask("/servers")
    assert "1. NL-1 — жив, 80 мс ← выбран" in text and "2. DE-1 — НЕ ОТВЕЧАЕТ" in text
    assert "Запасных: 1" in text


def test_devices_show_where_each_one_goes(rig):
    leases = dnsmasq.leases_path(rig.paths)
    leases.parent.mkdir(parents=True, exist_ok=True)
    leases.write_text(
        "1791600000 aa:bb:cc:00:11:22 192.168.50.101 phone *\n"
        "1791600000 aa:bb:cc:00:11:23 192.168.50.23 tv *\n", encoding="utf-8")
    text = rig.ask("/devices")
    assert "192.168.50.101 — phone — через VPN" in text and "192.168.50.23 — tv — мимо VPN" in text


def test_daemon_down_is_said_plainly(rig):
    rig.paths.status_file.unlink()
    assert "Демон XGW не отвечает" in rig.ask("/status")
    assert "Демон XGW не отвечает" in rig.ask("/servers")


def test_unknown_command_and_plain_text(rig):
    assert "Не знаю такой команды" in rig.ask("/format_disk")
    assert rig.ask("просто текст") == ""  # не команда — молчим


def test_long_answers_are_split(rig, monkeypatch):
    monkeypatch.setattr(telegram_module, "MAX_TEXT", 50)
    rig.fake.say("/help")
    rig.poll()
    assert len(rig.fake.sent) > 1 and all(len(m["text"]) <= 50 for m in rig.fake.sent)
    assert "".join(m["text"] for m in rig.fake.sent) == HELP


# --- кому верить -------------------------------------------------------------------------------


def test_stranger_gets_no_answer_and_no_action(rig, caplog):
    for text in ("/status", "/disable", "/start"):
        rig.fake.say(text, chat=424242)
    rig.poll()
    assert rig.fake.sent == [] and rig.kernel.calls == []
    warnings = [r for r in caplog.records if "чужого чата 424242" in r.getMessage()]
    assert len(warnings) == 1  # одно предупреждение на чат, а не на каждое сообщение


def test_old_commands_are_never_executed(rig):
    """Telegram хранит неполученные сообщения сутки: после перезагрузки шлюза давняя
    «/disable» не должна сработать."""
    rig.fake.say("/disable", age=telegram_module.MAX_AGE + 30)
    rig.fake.say("/status", age=telegram_module.MAX_AGE - 30)
    rig.poll()
    assert [m["text"].split("\n")[0] for m in rig.fake.sent] == ["Состояние: HEALTHY"]
    assert rig.kernel.calls == []


def test_processed_messages_are_confirmed(rig):
    rig.fake.say("/status")
    rig.poll()
    rig.bot.poll_once(rig.cfg)
    assert rig.fake.offsets[0] == 0 and rig.fake.offsets[-1] > 100  # offset подтвердил
    assert len(rig.fake.sent) == 1  # второй круг ничего не повторил


def test_control_works_only_in_a_private_chat(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, chat=str(GROUP))
    try:
        assert "Состояние: HEALTHY" in rig.ask("/status", chat=GROUP, kind="supergroup")
        for command in ("/disable", "/enable", "/pin 1", "/unpin", "/refresh", "/scan", "/speed"):
            assert rig.ask(command, chat=GROUP, kind="supergroup") == PRIVATE_ONLY
        assert rig.kernel.calls == [] and rig.pinned == [] and rig.daemon.asked == []
    finally:
        rig.fake.stop()


def test_commands_for_another_bot_in_a_group_are_ignored(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, chat=str(GROUP))
    try:
        rig.bot.username = BOT_NAME
        assert rig.ask("/status@someone_else_bot", chat=GROUP, kind="group") == ""
    finally:
        rig.fake.stop()


# --- управление --------------------------------------------------------------------------------


def test_disable_and_enable_do_what_the_buttons_do(rig):
    assert "перехват снят" in rig.ask("/disable")
    assert "tproxy" not in rig.kernel.table and "masquerade" in rig.kernel.table
    rig.xray_up = False
    assert "Xray не отвечает — VPN не включён" in rig.ask("/enable")  # как кнопка панели
    assert "tproxy" not in rig.kernel.table
    rig.xray_up = True
    assert "перехват включён: сеть lan0 и эта машина" in rig.ask("/enable")
    assert "tproxy to 127.0.0.1:12345" in rig.kernel.table
    events = [e["detail"] for e in status.collect_status(
        rig.cfg, rig.paths, [], observatory=None, xray_ok=False)["events"]]
    assert any("Telegram: команда /disable" in text for text in events), events


def test_control_needs_root(rig):
    rig.root_problem = "нужны права root: sudo xgw …"
    assert rig.ask("/disable") == "Не получилось: нужны права root: sudo xgw …"
    assert rig.kernel.calls == []


def test_pin_by_number_with_default_and_given_term(rig):
    assert "закреплён на 1h" in rig.ask("/pin 1")
    assert "закреплён на 6h" in rig.ask("/pin 2 6h")
    assert rig.pinned == [("proxy-nl-aaaa", "1h"), ("proxy-de-bbbb", "6h")]
    for bad in ("/pin", "/pin x", "/pin 1 2 3", "/pin 9", "/pin 0"):
        assert rig.ask(bad).startswith(("Укажите номер", "Сервера с номером")), bad
    assert len(rig.pinned) == 2
    assert "закрепление снято" in rig.ask("/unpin") and rig.unpinned == 1


def test_refresh_and_scan_go_to_the_daemon(rig):
    assert "Обновляю подписки" in rig.ask("/refresh")
    assert "Проверяю запасные серверы" in rig.ask("/scan")
    assert "Замеряю скорость" in rig.ask("/speed")
    assert rig.daemon.asked == ["refresh", "scan", "speed"]


def test_a_failing_command_is_reported_and_logged(rig, monkeypatch, caplog):
    def broken(*_args, **_kwargs):
        raise RuntimeError("секрет-в-исключении-не-для-чата")

    monkeypatch.setattr(actions, "unpin", broken)
    text = rig.ask("/unpin")
    assert "внутренняя ошибка" in text and "секрет" not in text
    assert any("команда /unpin не выполнена" in r.getMessage() for r in caplog.records)
    assert "Состояние: HEALTHY" in rig.ask("/status")  # бот жив


# --- commands = false --------------------------------------------------------------------------


def test_with_commands_off_the_bot_does_not_even_poll(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    try:
        rig.config_path.write_text(
            rig.config_path.read_text(encoding="utf-8").replace(
                "[notify]", "[notify]\ncommands = false"), encoding="utf-8")
        cfg = rig.reload()
        assert cfg.notify.commands is False and rig.bot._active(cfg) is False
        assert rig.bot.info()["mode"] == "notify"
        rig.fake.say("/disable")
        rig.bot.start()
        time.sleep(0.6)
        rig.bot.stop()
        assert rig.fake.calls == [] and rig.kernel.calls == []
    finally:
        rig.fake.stop()


# --- подключение чата кодом --------------------------------------------------------------------


@pytest.fixture()
def pairing(tmp_path, monkeypatch):
    instance = Rig(tmp_path, monkeypatch, chat="", managed_token=True)
    yield instance
    instance.fake.stop()


def test_chat_is_paired_by_the_code_from_the_panel(pairing):
    rig = pairing
    assert rig.cfg.managed.telegram and rig.cfg.notify.telegram_chat_id == ""
    assert rig.bot.info()["mode"] == "pairing" and rig.bot.info()["code"] == ""
    # Пока код не запрошен, подключиться нельзя.
    assert "Код не запрашивался" in rig.ask("/start 000000")
    assert rig.cfg.notify.telegram_chat_id == ""

    code = rig.bot.new_code()
    info = rig.bot.info()
    assert info["code"] == code and len(code) == 6 and info["until"] > time.time()
    assert "Неверный код" in rig.ask("/start 000000" if code != "000000" else "/start 111111")
    assert "Отправьте /start и шесть цифр" in rig.ask("/start")
    answer = rig.ask(f"/start {code}")
    assert answer.startswith("Готово: шлюз подключён") and HELP in answer
    saved = managed.load(managed.path_for(rig.config_path))[0]["telegram"]
    assert saved == {"token": TOKEN, "chat_id": str(OWNER)}
    assert rig.cfg.notify.telegram_chat_id == str(OWNER) and rig.daemon.poke.is_set()
    assert rig.bot.info()["mode"] == "connected" and rig.bot.info()["code"] == ""
    # Дальше чат — свой, и тот же код больше не годится.
    assert rig.ask(f"/start {code}") == HELP
    assert rig.reload().notify.telegram_chat_id == str(OWNER)


def test_stale_reload_does_not_lose_the_code_or_the_chat(pairing):
    """Перечитывание настроек, начатое до записи токена, приходит позже панели и
    приносит конфиг без токена — код подключения и подключённый чат от этого не
    пропадают (так «машина» теряла код)."""
    rig = pairing
    stale = config.Config()  # как если бы config.toml прочли до сохранения токена
    code = rig.bot.new_code(TOKEN)
    rig.bot.configure(stale, rig.daemon, None)
    assert rig.bot.info()["mode"] == "off" and rig.bot.info()["code"] == ""
    rig.bot.configure(rig.cfg, rig.daemon, None)  # следом пришёл свежий
    assert rig.bot.info()["mode"] == "pairing" and rig.bot.info()["code"] == code
    # Код другого токена не подходит новому.
    other = config.Config()
    other.notify.telegram_bot_token = "987654321:" + "B" * 35
    other.managed.telegram = True
    rig.bot.configure(other, rig.daemon, None)
    assert rig.bot.info()["code"] == ""
    rig.bot.configure(rig.cfg, rig.daemon, None)
    assert rig.bot.info()["code"] == code

    assert rig.ask(f"/start {code}").startswith("Готово")
    # Устаревший конфиг без чата, пришедший после подключения, чат не отменяет.
    late, _warnings = config.load(rig.config_path)
    late.notify.telegram_chat_id = ""
    rig.bot.configure(late, rig.daemon, None)
    assert late.notify.telegram_chat_id == str(OWNER) and rig.bot.info()["mode"] == "connected"
    # Отключение в панели забывает и код, и чат.
    rig.bot.forget()
    again = config.Config()
    again.notify.telegram_bot_token = TOKEN
    again.managed.telegram = True
    rig.bot.configure(again, rig.daemon, None)
    assert again.notify.telegram_chat_id == "" and rig.bot.info()["mode"] == "pairing"


def test_reload_during_the_poll_does_not_lose_the_paired_chat(pairing):
    """Настройки перечитались, пока опрос ждал сообщений: код приходит в опросе со
    старыми настройками, а дальше бот живёт на новых. Так «машина» один раз
    осталась без ответа на /status после подключения."""
    rig = pairing
    code = rig.bot.new_code(TOKEN)
    in_flight = rig.cfg
    rig.fake.say(f"/start {code}")
    fresh = rig.reload()  # чата в panel.json ещё нет
    assert fresh is not in_flight and fresh.notify.telegram_chat_id == ""
    rig.bot.poll_once(in_flight)
    assert fresh.notify.telegram_chat_id == str(OWNER)
    assert rig.bot.info()["mode"] == "connected"
    assert "Состояние: HEALTHY" in rig.ask("/status")


def test_wrong_codes_burn_the_code(pairing):
    rig = pairing
    code = rig.bot.new_code()
    wrong = "999999" if code != "999999" else "888888"
    for _ in range(telegram_module.PAIR_TRIES):
        assert "Неверный код" in rig.ask(f"/start {wrong}")
    assert rig.bot.info()["code"] == ""  # код сгорел: перебор не пройдёт
    assert "Код не запрашивался или истёк" in rig.ask(f"/start {code}")
    assert rig.cfg.notify.telegram_chat_id == ""


def test_expired_code_is_refused(pairing):
    rig = pairing
    code = rig.bot.new_code()
    rig.bot.clock = lambda: time.time() + telegram_module.PAIR_TTL + 5
    rig.fake.say(f"/start {code}", age=-telegram_module.PAIR_TTL)  # сообщение «из будущего» свежее
    rig.poll()
    assert "Код не запрашивался или истёк" in rig.fake.replies()[-1]
    assert rig.cfg.notify.telegram_chat_id == ""


def test_pairing_only_in_a_private_chat(pairing):
    rig = pairing
    code = rig.bot.new_code()
    answer = rig.ask(f"/start {code}", chat=GROUP, kind="group")
    assert "только из личной переписки" in answer
    assert managed.load(managed.path_for(rig.config_path))[0]["telegram"]["chat_id"] == ""


def test_token_from_config_toml_cannot_be_paired(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, chat="")  # токен в config.toml, чата нет
    try:
        assert rig.bot.info()["mode"] == "no_chat" and not rig.cfg.managed.telegram
        rig.bot.new_code()
        assert rig.ask("/start 123456") == ""  # подключения нет — чат вписывают в config.toml
    finally:
        rig.fake.stop()


# --- связь с Telegram --------------------------------------------------------------------------


def test_rejected_token_is_named(rig):
    rig.fake.refuse = 1
    with pytest.raises(TelegramError, match="не принял токен"):
        rig.poll()


def test_reply_not_from_the_bot_api_is_an_error(rig):
    rig.fake.broken = True
    with pytest.raises(TelegramError, match="не по Bot API"):
        rig.poll()


def test_unreachable_telegram_is_an_error(rig):
    rig.fake.stop()
    with pytest.raises(Exception, match="не удалось получить"):  # FetchError без токена в тексте
        rig.poll()


def test_thread_answers_survives_errors_and_recovers(rig, monkeypatch):
    monkeypatch.setattr(telegram_module, "BACKOFF", (0.3,))
    rig.fake.refuse = 2  # первые два запроса — отказ
    rig.bot.start()
    try:
        # Ошибка видна, пока идут отказы (две паузы по 0,3 с); значение читается один
        # раз за круг: между двумя чтениями бот успел бы восстановиться.
        error, deadline = "", time.time() + 10
        while "не принял токен" not in error and time.time() < deadline:
            time.sleep(0.02)
            error = rig.bot.info()["error"]
        assert "не принял токен" in error and TOKEN not in error
        rig.fake.say("/status")
        deadline = time.time() + 10
        while not rig.fake.sent and time.time() < deadline:
            time.sleep(0.02)
        assert rig.fake.sent and "Состояние: HEALTHY" in rig.fake.sent[0]["text"]
        # Ошибка снимается, когда круг опроса закончен, — чуть позже самого ответа.
        deadline = time.time() + 10
        while rig.bot.info()["error"] and time.time() < deadline:
            time.sleep(0.02)
        assert rig.bot.info()["error"] == "" and rig.bot.info()["username"] == BOT_NAME
    finally:
        rig.bot.stop()


def test_stop_interrupts_the_long_poll(rig):
    """Остановка демона не ждёт long-poll getUpdates: Telegram, который молчит, не
    держит остановку (раньше join ждал потока 2 с), и поток бота выходит сам."""
    silent = socket.socket()
    silent.bind(("127.0.0.1", 0))
    silent.listen(8)  # соединения принимает ядро, ответа нет никогда
    try:
        url = f"http://127.0.0.1:{silent.getsockname()[1]}"
        rig.config_path.write_text(
            rig.config_path.read_text(encoding="utf-8").replace(rig.fake.url, url),
            encoding="utf-8",
        )
        rig.reload()
        rig.bot.username = BOT_NAME  # сразу к getUpdates
        rig.bot.long_poll = telegram_module.LONG_POLL
        rig.bot.start()
        thread = rig.bot._thread
        time.sleep(0.3)  # запрос отправлен, бот ждёт ответа
        assert thread is not None and thread.is_alive()
        started = time.monotonic()
        rig.bot.stop()
        assert time.monotonic() - started < 1.0
        assert not thread.is_alive() and rig.bot.error == ""
    finally:
        rig.bot.stop()
        silent.close()


def test_requests_go_through_xray_first_and_directly_when_it_fails(rig):
    """Сначала через http-in Xray, а если он не отвечает — напрямую; без работающего
    Xray прокси не пробуется вовсе."""
    rig.poll()  # getMe и getUpdates
    assert rig.routes == ["xray", "direct"] * 2
    rig.routes.clear()
    rig.xray_up = False
    assert "Состояние: HEALTHY" in rig.ask("/status")  # getUpdates и sendMessage
    assert rig.routes == ["direct"] * 2


def test_changing_the_token_forgets_the_old_bot(rig):
    rig.poll()
    assert rig.bot.username == BOT_NAME and rig.bot._offset == 0
    rig.fake.say("/status")
    rig.poll()
    assert rig.bot._offset > 100
    other = config.Config()
    other.notify.telegram_bot_token = "987654321:" + "B" * 35
    other.notify.telegram_chat_id = str(OWNER)
    rig.bot.configure(other, None, None)
    assert rig.bot.username == "" and rig.bot._offset == 0
    assert rig.bot.info()["mode"] == "connected"
    assert rig.bot.info()["error"] == ""


def test_info_never_contains_the_token_or_the_chat(rig):
    rig.poll()
    text = str(rig.bot.info())
    assert TOKEN not in text and str(OWNER) not in text
