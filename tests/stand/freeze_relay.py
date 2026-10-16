"""«Замораживающее» реле — модель ТСПУ перед VPN-сервером.

TCP-реле между шлюзом и сервером. Режим читается из файла и меняется на лету:

  pass             пересылать всё
  freeze_after=N   после N байт от сервера к клиенту (в одном соединении) перестать
                   пересылать в обе стороны; соединение НЕ закрывается — именно
                   так «замораживает» провайдер: рукопожатие и первые килобайты
                   проходят, дальше тишина
  drop             принять соединение и сразу сбросить
  blackhole        принять и молчать, ничего не пересылая

К режиму можно дописать «;latency=МС» — задержку первого ответа в каждом
соединении. Она делает один сервер заведомо медленнее другого, и выбор
балансировщика leastPing на стенде становится однозначным.

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


class Mode:
    """Текущий режим: перечитывается из файла раз в 100 мс."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = "pass"
        self.limit = 0
        self.latency = 0.0  # секунд перед первым ответом в соединении
        self._load()
        threading.Thread(target=self._watch, daemon=True).start()

    def _load(self) -> None:
        try:
            text = self.path.read_text(encoding="ascii").strip()
        except OSError:
            return
        latency = 0.0
        for token in text.split(";"):
            name, _, value = token.strip().partition("=")
            if name == "latency" and value.isdigit():
                latency = int(value) / 1000.0
            elif name == "freeze_after" and value.isdigit():
                self.name, self.limit = name, int(value)
            elif name in ("pass", "drop", "blackhole"):
                self.name, self.limit = name, 0
        self.latency = latency

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

    def run(self) -> None:
        if self.mode.name == "drop":
            # SO_LINGER с нулём — закрытие сбросом (RST), как делает блокировка.
            self.client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            self.client.close()
            return
        if self.mode.name == "blackhole":
            self._drain(self.client)
            return
        try:
            upstream = socket.create_connection(self.upstream_address, timeout=5)
        except OSError:
            self.client.close()
            return
        upstream.settimeout(None)
        threading.Thread(target=self._up, args=(upstream,), daemon=True).start()
        self._down(upstream)

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
                if self.mode.name == "freeze_after":
                    allowed = self.mode.limit - self.downstream_bytes
                    if allowed < len(data):
                        self.frozen = True
                        data = data[: max(0, allowed)]
                elif self.mode.name in ("drop", "blackhole"):
                    self.frozen = True  # режим сменили на ходу — соединение замирает
                    continue
                if data:
                    self.client.sendall(data)
                    self.downstream_bytes += len(data)
        except OSError:
            pass
        if not self.frozen:  # «замороженное» соединение держим открытым
            _close(upstream, self.client)


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
