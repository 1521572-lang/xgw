"""«Замораживающее» реле — модель ТСПУ перед VPN-сервером.

TCP-реле между шлюзом и сервером. Режим читается из файла и меняется на лету:

  pass             пересылать всё
  freeze_after=N   после N байт от сервера к клиенту (в одном соединении) перестать
                   пересылать в обе стороны; соединение НЕ закрывается — именно
                   так «замораживает» провайдер: рукопожатие и первые килобайты
                   проходят, дальше тишина
  drop             принять соединение и сразу сбросить
  blackhole        принять и молчать, ничего не пересылая
  sni=ИМЯ          DPI: прочитать первую запись TLS от клиента и, если в ней целиком
                   ClientHello с этим именем сайта (SNI), сбросить соединение. Как DPI без
                   сборки записей TLS: ClientHello, разрезанный на несколько записей
                   (дробление в Xray, freedom.fragment), он не узнаёт и пропускает

  sni_freeze=ИМЯ   то же узнавание ClientHello, но вместо сброса — «заморозка»: соединение
                   с таким ClientHello пропускается, а после FREEZE_AT байт от сервера к
                   клиенту замирает (так ТСПУ и «замораживает»). ClientHello, разрезанный на
                   записи, не узнаётся — и соединение идёт без заморозки

  sni_freeze_strict=ИМЯ
                   «ТСПУ», который знает приёмы обхода: как sni_freeze, но узнаёт ещё и
                   ClientHello, разрезанный на мелкие записи (две первые записи TLS короче
                   MIN_RECORD байт) — так режет Xray (freedom.fragment: ~13 записей по
                   100–200 байт). Дробление sing-box (fragment + record_fragment) он не
                   узнаёт: записей всегда две, а первая случайной длины (от ~120 до ~1800
                   байт) и вторая — не мелкая. Измерено на Xray 26.10.10 и sing-box 1.14.3
                   (60 соединений на вариант)

К режиму можно дописать «;latency=МС» — задержку первого ответа в каждом
соединении. Она делает один сервер заведомо медленнее другого, и выбор
балансировщика leastPing на стенде становится однозначным. «;rate=КБ/с» — полосу
от сервера к клиенту в каждом соединении: так один сервер медленнее другого для
замера скорости (0 — без ограничения).

Счётчик байтов — на каждое соединение отдельно, поэтому короткая проверка
(HEAD, пинг) «заморозку» не замечает.

Число принятых соединений реле пишет в файл «<mode-file>.count»: по нему стенд видит,
ходит ли кто-нибудь через этот сервер (например, пробует ли его observatory ядра).

Запуск: python freeze_relay.py --listen 127.0.0.1:9001 --upstream 127.0.0.1:9101 --mode-file f
"""

from __future__ import annotations

import argparse
import contextlib
import socket
import struct
import threading
import time
from pathlib import Path

FREEZE_AT = 16384  # sni_freeze: после стольких байт от сервера соединение замирает
MIN_RECORD = 200  # sni_freeze_strict: две первые записи ClientHello короче этого — дробление Xray


class Mode:
    """Текущий режим: перечитывается из файла раз в 100 мс."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = "pass"
        self.limit = 0
        self.latency = 0.0  # секунд перед первым ответом в соединении
        self.rate = 0  # байт/с от сервера к клиенту в соединении; 0 — без ограничения
        self.sni = ""  # режим sni: имя сайта, по которому «DPI» сбрасывает соединение
        self._load()
        threading.Thread(target=self._watch, daemon=True).start()

    def _load(self) -> None:
        try:
            text = self.path.read_text(encoding="ascii").strip()
        except OSError:
            return
        latency, rate = 0.0, 0
        for token in text.split(";"):
            name, _, value = token.strip().partition("=")
            if name == "latency" and value.isdigit():
                latency = int(value) / 1000.0
            elif name == "rate" and value.isdigit():
                rate = int(value) * 1000
            elif name == "freeze_after" and value.isdigit():
                self.name, self.limit = name, int(value)
            elif name in ("pass", "drop", "blackhole"):
                self.name, self.limit = name, 0
            elif name in ("sni", "sni_freeze", "sni_freeze_strict") and value:
                self.name, self.limit, self.sni = name, 0, value
        self.latency = latency
        self.rate = rate

    def _watch(self) -> None:
        while True:
            time.sleep(0.1)
            self._load()


class Connection:
    def __init__(self, client: socket.socket, upstream: tuple[str, int], mode: Mode) -> None:
        self.client = client
        self.upstream_address = upstream
        self.mode = mode
        self.downstream_bytes = 0  # сколько уже ушло от сервера к клиенту
        self.frozen = False
        self.freeze_at = 0

    def run(self) -> None:
        if self.mode.name == "drop":
            # SO_LINGER с нулём — закрытие сбросом (RST), как делает блокировка.
            self.client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            self.client.close()
            return
        if self.mode.name == "blackhole":
            self._drain(self.client)
            return
        first = b""
        self.freeze_at = 0  # sni_freeze: распознанному соединению — предел байт от сервера
        if self.mode.name in ("sni", "sni_freeze", "sni_freeze_strict"):
            first = self._first_record(strict=self.mode.name == "sni_freeze_strict")
            known = first is not None and (
                _hello_name(first) == self.mode.sni
                or (self.mode.name == "sni_freeze_strict" and _tiny_hello(first))
            )
            if first is None or (known and self.mode.name == "sni"):
                self.client.setsockopt(
                    socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                )
                self.client.close()
                return
            if known:
                self.freeze_at = FREEZE_AT
        try:
            upstream = socket.create_connection(self.upstream_address, timeout=5)
        except OSError:
            self.client.close()
            return
        upstream.settimeout(None)
        if first:
            upstream.sendall(first)
        threading.Thread(target=self._up, args=(upstream,), daemon=True).start()
        self._down(upstream)

    def _first_record(self, strict: bool = False) -> bytes | None:
        """Первая запись TLS от клиента целиком (заголовок и тело); не TLS — то, что
        пришло; None — клиент закрыл соединение раньше. Строгий режим: если ClientHello
        начат мелкой записью, дочитывается и вторая — по двум записям видно, режет ли его Xray
        (обе мелкие) или sing-box (вторая большая)."""
        self.client.settimeout(10)
        data = b""
        try:
            while len(data) < 5 or (
                data[0] == 0x16 and len(data) < 5 + int.from_bytes(data[3:5], "big")
            ):
                chunk = self.client.recv(65536)
                if not chunk:
                    return None
                data += chunk
                if data[0] != 0x16:
                    break
            while strict and _starts_small_hello(data) and not _has_records(data, 2):
                chunk = self.client.recv(65536)
                if not chunk:
                    return None
                data += chunk
        except OSError:
            return None
        self.client.settimeout(None)
        return data

    def _drain(self, sock: socket.socket) -> None:
        """Читает и выбрасывает: соединение открыто, но данные никуда не идут."""
        with contextlib.suppress(OSError):
            while sock.recv(65536):
                pass
        _close(sock)

    def _up(self, upstream: socket.socket) -> None:
        """Клиент → сервер."""
        try:
            while data := self.client.recv(65536):
                if not self.frozen:
                    upstream.sendall(data)
        except OSError:
            pass
        _close(upstream, self.client)

    def _down(self, upstream: socket.socket) -> None:
        """Сервер → клиент со счётчиком байтов."""
        try:
            while data := upstream.recv(65536):
                if self.frozen:
                    continue
                if not self.downstream_bytes and self.mode.latency:
                    time.sleep(self.mode.latency)
                limit = self.mode.limit if self.mode.name == "freeze_after" else self.freeze_at
                if limit:
                    allowed = limit - self.downstream_bytes
                    if allowed < len(data):
                        self.frozen = True
                        data = data[: max(0, allowed)]
                elif self.mode.name in ("drop", "blackhole"):
                    self.frozen = True  # режим сменили на ходу — соединение замирает
                    continue
                if data:
                    self.client.sendall(data)
                    self.downstream_bytes += len(data)
                    if self.mode.rate:
                        time.sleep(len(data) / self.mode.rate)
        except OSError:
            pass
        if not self.frozen:  # «замороженное» соединение держим открытым
            _close(upstream, self.client)


def _starts_small_hello(data: bytes) -> bool:
    """Первая запись TLS начинает ClientHello, короче MIN_RECORD и не вмещает его целиком:
    ClientHello разрезан, продолжение — в следующей записи."""
    if len(data) < 9 or data[0] != 0x16 or data[5] != 1:
        return False
    record = int.from_bytes(data[3:5], "big")
    return record < MIN_RECORD and 4 + int.from_bytes(data[6:9], "big") > record


def _has_records(data: bytes, count: int) -> bool:
    """В data есть count записей TLS целиком."""
    position = 0
    for _ in range(count):
        if position + 5 > len(data):
            return False
        position += 5 + int.from_bytes(data[position + 3:position + 5], "big")
        if position > len(data):
            return False
    return True


def _tiny_hello(data: bytes) -> bool:
    """ClientHello разрезан на мелкие записи: обе первые короче MIN_RECORD (Xray режет на
    записи по 100–200 байт). У sing-box записей две, и вторая большая."""
    if not _starts_small_hello(data):
        return False
    first = int.from_bytes(data[3:5], "big")
    return _has_records(data, 2) and int.from_bytes(data[8 + first:10 + first], "big") < MIN_RECORD


def _hello_name(data: bytes) -> str:
    """Имя сайта (SNI) из ClientHello, если он целиком в первой записи TLS; иначе пусто."""
    if len(data) < 9 or data[0] != 0x16 or data[5] != 1:
        return ""
    body = data[5:5 + int.from_bytes(data[3:5], "big")]
    if 4 + int.from_bytes(body[1:4], "big") > len(body):
        return ""  # ClientHello продолжается в следующей записи
    try:
        p = 4 + 2 + 32
        p += 1 + body[p]  # session id
        p += 2 + int.from_bytes(body[p:p + 2], "big")  # шифры
        p += 1 + body[p]  # сжатие
        end = p + 2 + int.from_bytes(body[p:p + 2], "big")
        p += 2
        while p + 4 <= end:
            kind = int.from_bytes(body[p:p + 2], "big")
            size = int.from_bytes(body[p + 2:p + 4], "big")
            if kind == 0:  # server_name: список, тип 0 — имя хоста
                length = int.from_bytes(body[p + 7:p + 9], "big")
                return body[p + 9:p + 9 + length].decode("ascii", "replace")
            p += 4 + size
    except IndexError:
        return ""
    return ""


def _close(*socks: socket.socket) -> None:
    """Закрывает соединения так, чтобы другая сторона увидела конец потока.

    Одного close() мало: в Linux сокет, на котором соседний поток ждёт в recv(),
    остаётся открытым до выхода из этого вызова, и FIN не уходит. shutdown()
    будит ждущий поток и отправляет FIN сразу.
    """
    for sock in socks:
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            sock.close()


def _address(text: str) -> tuple[str, int]:
    host, _, port = text.rpartition(":")
    return host, int(port)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", required=True, help="адрес:порт, куда ходит шлюз")
    parser.add_argument("--upstream", required=True, help="адрес:порт настоящего сервера")
    parser.add_argument("--mode-file", required=True, help="файл с текущим режимом")
    args = parser.parse_args()

    mode = Mode(Path(args.mode_file))
    upstream = _address(args.upstream)
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(_address(args.listen))
    server.listen(64)
    counter = Path(args.mode_file + ".count")
    accepted = 0
    counter.write_text("0", encoding="ascii")
    print("READY", flush=True)
    while True:
        client, _peer = server.accept()
        accepted += 1
        counter.write_text(str(accepted), encoding="ascii")
        threading.Thread(target=Connection(client, upstream, mode).run, daemon=True).start()


if __name__ == "__main__":
    main()
