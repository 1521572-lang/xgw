"""Запись трафика устройства сети в файл pcap — кнопка «Записать трафик» в строке устройства
панели (ASSUMPTIONS п. 228).

Кадры устройства ловит сокет AF_PACKET на интерфейсе LAN: фильтр ядра (classic BPF, как
`tcpdump ether host <MAC>`) пропускает в Python только кадры с MAC устройства — в обе
стороны, до Xray и до шифрования туннелем. Внешних программ не нужно (tcpdump на шлюзе может
не быть), демону — право CAP_NET_RAW (xgw.service).

Файл — `/var/lib/xgw/records/<mac>-<время>.pcap`, 0600, открывается в Wireshark. Запись
одна за раз, не дольше MAX_SECONDS и не больше MAX_BYTES; хранятся последние KEEP файлов.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import socket
import struct
import threading
import time
from collections.abc import Callable
from pathlib import Path

DEFAULT_SECONDS = 120
MAX_SECONDS = 600
MAX_BYTES = 100 * 1024 * 1024
KEEP = 3
SNAPLEN = 65535

ETH_P_ALL = 0x0003
SO_ATTACH_FILTER = 26
LINKTYPE_ETHERNET = 1
_NAME = re.compile(r"^[0-9a-f]{12}-\d{8}-\d{6}\.pcap$")

# classic BPF: ld/ldh — загрузка слова или полуслова кадра, jeq — сравнение, ret — сколько
# байт кадра отдать (0 — отбросить).
_LD_W, _LD_H, _JEQ, _RET = 0x20, 0x28, 0x15, 0x06


class RecordError(Exception):
    """Запись не началась; текст — для панели."""


def mac_filter(mac: str) -> list[tuple[int, int, int, int]]:
    """Программа BPF «кадр от этого MAC или к нему» — то же, что `tcpdump -dd ether host`."""
    raw = bytes.fromhex(mac.replace(":", ""))
    head, tail = struct.unpack("!H", raw[:2])[0], struct.unpack("!I", raw[2:])[0]
    return [
        (_LD_W, 0, 0, 8),       # 0: источник, байты 2–5
        (_JEQ, 0, 2, tail),     # 1: совпали — к 2, нет — к 4
        (_LD_H, 0, 0, 6),       # 2: источник, байты 0–1
        (_JEQ, 4, 0, head),     # 3: совпали — к 8 (отдать)
        (_LD_W, 0, 0, 2),       # 4: получатель, байты 2–5
        (_JEQ, 0, 3, tail),     # 5: нет — к 9 (отбросить)
        (_LD_H, 0, 0, 0),       # 6: получатель, байты 0–1
        (_JEQ, 0, 1, head),     # 7: нет — к 9
        (_RET, 0, 0, 0x40000),  # 8: кадр целиком
        (_RET, 0, 0, 0),        # 9: мимо
    ]


def _attach(sock: socket.socket, program: list[tuple[int, int, int, int]]) -> None:
    """SO_ATTACH_FILTER: struct sock_fprog {unsigned short len; struct sock_filter *filter}."""
    code = b"".join(struct.pack("HBBI", *insn) for insn in program)
    buffer = ctypes.create_string_buffer(code)
    fprog = struct.pack("HL", len(program), ctypes.addressof(buffer))
    sock.setsockopt(socket.SOL_SOCKET, SO_ATTACH_FILTER, fprog)


def open_socket(interface: str, mac: str) -> socket.socket:
    """Сокет кадров интерфейса с фильтром по MAC (нужно CAP_NET_RAW)."""
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    try:
        _attach(sock, mac_filter(mac))
        sock.bind((interface, 0))
    except OSError:
        sock.close()
        raise
    return sock


def pcap_header() -> bytes:
    return struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, SNAPLEN, LINKTYPE_ETHERNET)


def pcap_record(stamp: float, data: bytes, length: int) -> bytes:
    seconds = int(stamp)
    return struct.pack("<IIII", seconds, int((stamp - seconds) * 1e6), len(data), length) + data


class Recorder:
    """Запись трафика одного устройства за раз; состояние — для панели."""

    def __init__(
        self,
        directory: Path,
        *,
        opener: Callable[[str, str], socket.socket] = open_socket,
        clock: Callable[[], float] = time.time,
        on_done: Callable[[str], None] | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.opener = opener
        self.clock = clock
        self.on_done = on_done
        self._lock = threading.Lock()
        self._active: dict | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, interface: str, mac: str, label: str, seconds: int = DEFAULT_SECONDS) -> str:
        """Начать запись; вернуть имя файла. RecordError — почему нельзя."""
        if not 10 <= seconds <= MAX_SECONDS:
            raise RecordError(f"длительность записи — от 10 до {MAX_SECONDS} секунд")
        with self._lock:
            if self._active is not None:
                busy = self._active["label"]
                raise RecordError(
                    f"уже идёт запись трафика «{busy}» — дождитесь конца или остановите")
            try:
                sock = self.opener(interface, mac)
            except PermissionError as exc:
                raise RecordError(
                    "у службы XGW нет права на запись трафика (CAP_NET_RAW): переустановите "
                    "XGW — sudo sh packaging/install.sh"
                ) from exc
            except OSError as exc:
                raise RecordError(f"интерфейс {interface} недоступен для записи: {exc}") from exc
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            started = self.clock()
            stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(started))
            name = f"{mac.replace(':', '')}-{stamp}.pcap"
            self._active = {
                "name": name, "mac": mac, "label": label, "started": started,
                "seconds": seconds, "bytes": 0, "packets": 0,
            }
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, args=(sock, dict(self._active)), name="xgw-record", daemon=True,
            )
            self._thread.start()
        return name

    def stop(self) -> bool:
        """Остановить идущую запись (файл остаётся). False — записи не было."""
        with self._lock:
            thread = self._thread if self._active is not None else None
        if thread is None:
            return False
        self._stop.set()
        thread.join(timeout=5)
        return True

    def _run(self, sock: socket.socket, job: dict) -> None:
        path = self.directory / job["name"]
        part = path.with_suffix(".part")
        buffer = bytearray(SNAPLEN)
        deadline = job["started"] + job["seconds"]
        why, packets = "время вышло", 0
        try:
            sock.settimeout(0.5)
            fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as out:
                header = pcap_header()
                out.write(header)
                written = len(header)
                while self.clock() < deadline:
                    if self._stop.is_set():
                        why = "остановлено"
                        break
                    try:
                        length = sock.recv_into(buffer, SNAPLEN, socket.MSG_TRUNC)
                    except TimeoutError:
                        continue
                    record = pcap_record(self.clock(), bytes(buffer[:min(length, SNAPLEN)]), length)
                    if written + len(record) > MAX_BYTES:
                        why = f"файл дошёл до {MAX_BYTES // (1024 * 1024)} МБ"
                        break
                    out.write(record)
                    written += len(record)
                    packets += 1
                    with self._lock:
                        if self._active is not None:
                            self._active.update(bytes=written, packets=packets)
            os.replace(part, path)
            meta = {**job, "bytes": written, "packets": packets, "ended": self.clock(), "why": why}
            path.with_suffix(".json").write_text(
                json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            self._prune()
            text = (f"запись трафика «{job['label']}» готова: {packets} пакетов, "
                    f"{_size(written)} ({why})")
        except OSError as exc:
            part.unlink(missing_ok=True)
            text = f"запись трафика «{job['label']}» не удалась: {exc}"
        finally:
            sock.close()
            with self._lock:
                self._active = None
        if self.on_done is not None:
            self.on_done(text)

    def _prune(self) -> None:
        files = sorted(self.directory.glob("*.pcap"), key=lambda item: item.stat().st_mtime)
        for old in files[:-KEEP]:
            old.unlink(missing_ok=True)
            old.with_suffix(".json").unlink(missing_ok=True)

    def path(self, name: str) -> Path | None:
        """Готовый файл записи по имени из панели; None — нет такого или имя чужое."""
        if not _NAME.match(name or ""):
            return None
        path = self.directory / name
        return path if path.is_file() else None

    def remove(self, name: str) -> bool:
        path = self.path(name)
        if path is None:
            return False
        path.unlink(missing_ok=True)
        path.with_suffix(".json").unlink(missing_ok=True)
        return True

    def state(self) -> dict:
        with self._lock:
            active = dict(self._active) if self._active is not None else None
        files = []
        for path in sorted(self.directory.glob("*.pcap"), key=lambda item: item.stat().st_mtime,
                           reverse=True) if self.directory.is_dir() else []:
            try:
                meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            files.append({
                "name": path.name, "mac": meta.get("mac", ""), "label": meta.get("label", ""),
                "bytes": path.stat().st_size, "packets": meta.get("packets", 0),
                "ended": meta.get("ended", path.stat().st_mtime), "why": meta.get("why", ""),
            })
        return {"active": active, "files": files}


def _size(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} МБ".replace(".", ",")
    return f"{max(1, value // 1024)} КБ"
