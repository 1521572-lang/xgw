"""Запись трафика устройства в pcap (watch/record.py) и её кнопки в панели (ASSUMPTIONS п. 228).
Сокет AF_PACKET подменён: кадры отдаёт «сеть» из списка."""

import http.client
import json
import struct

import pytest
from test_panel import PHONE, Rig

from xgw.watch import record
from xgw.watch.record import Recorder, RecordError

FRAME = bytes.fromhex("aabbcc001122") + bytes.fromhex("020000000001") + b"\x08\x00" + b"x" * 50


class FakeSocket:
    def __init__(self, frames: list[bytes]) -> None:
        self.frames = list(frames)
        self.closed = False

    def settimeout(self, _value) -> None:
        pass

    def recv_into(self, buffer, size, _flags) -> int:
        if not self.frames:
            raise TimeoutError
        frame = self.frames.pop(0)
        buffer[:min(len(frame), size)] = frame[:size]
        return len(frame)

    def close(self) -> None:
        self.closed = True


class Clock:
    """Часы записи: каждый вызов — на step секунд позже."""

    def __init__(self, step: float = 1.0) -> None:
        self.now = 1_790_000_000.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


def _records(data: bytes) -> list[tuple[int, int, bytes]]:
    magic, major, minor, _zone, _sig, snaplen, link = struct.unpack("<IHHiIII", data[:24])
    assert (magic, major, minor, snaplen, link) == (0xA1B2C3D4, 2, 4, 65535, 1)
    found, offset = [], 24
    while offset < len(data):
        _sec, _usec, incl, orig = struct.unpack("<IIII", data[offset:offset + 16])
        found.append((incl, orig, data[offset + 16:offset + 16 + incl]))
        offset += 16 + incl
    return found


def _download(client, path: str, cookie: str = ""):
    """GET файла записи: тело — байты (Client из test_panel читает только текст)."""
    conn = http.client.HTTPConnection("127.0.0.1", client.port, timeout=10)
    headers = {"Host": f"127.0.0.1:{client.port}"}
    if cookie:
        headers["Cookie"] = cookie
    conn.request("GET", path, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response, data


def _finish(recorder: Recorder) -> None:
    thread = recorder._thread
    assert thread is not None
    thread.join(timeout=10)
    assert not thread.is_alive()


def test_mac_filter_is_tcpdump_ether_host():
    """Та же программа, что `tcpdump -dd ether host aa:bb:cc:00:11:22`."""
    assert record.mac_filter("aa:bb:cc:00:11:22") == [
        (0x20, 0, 0, 0x8), (0x15, 0, 2, 0xCC001122), (0x28, 0, 0, 0x6), (0x15, 4, 0, 0xAABB),
        (0x20, 0, 0, 0x2), (0x15, 0, 3, 0xCC001122), (0x28, 0, 0, 0x0), (0x15, 0, 1, 0xAABB),
        (0x6, 0, 0, 0x40000), (0x6, 0, 0, 0x0),
    ]


def test_recording_writes_a_pcap_until_the_time_is_up(tmp_path):
    sock = FakeSocket([FRAME, FRAME[:30] + b"y" * 70000])
    done: list[str] = []
    recorder = Recorder(tmp_path, opener=lambda interface, mac: sock, clock=Clock(5.0),
                        on_done=done.append)
    name = recorder.start("enp4s0", PHONE, "phone", seconds=60)
    _finish(recorder)
    path = recorder.path(name)
    assert path is not None and path.stat().st_mode & 0o777 == 0o600
    frames = _records(path.read_bytes())
    assert [(incl, orig) for incl, orig, _data in frames] == [(len(FRAME), len(FRAME)),
                                                              (65535, 70030)]  # обрезан до SNAPLEN
    assert frames[0][2] == FRAME
    assert sock.closed and recorder.state()["active"] is None
    meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["packets"] == 2 and meta["why"] == "время вышло" and meta["label"] == "phone"
    assert done and "«phone» готова: 2 пакетов" in done[0]
    listed = recorder.state()["files"]
    assert [item["name"] for item in listed] == [name] and listed[0]["packets"] == 2


def test_recording_stops_on_request_and_on_the_size_limit(tmp_path, monkeypatch):
    recorder = Recorder(tmp_path, opener=lambda interface, mac: FakeSocket([]),
                        clock=Clock(0.0))  # время стоит — остановит только кнопка
    name = recorder.start("enp4s0", PHONE, "phone", seconds=60)
    assert recorder.state()["active"]["name"] == name
    with pytest.raises(RecordError, match="уже идёт запись трафика «phone»"):
        recorder.start("enp4s0", PHONE, "phone", seconds=60)
    assert recorder.stop() is True
    meta = json.loads((tmp_path / name).with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["why"] == "остановлено" and meta["packets"] == 0
    assert recorder.stop() is False

    monkeypatch.setattr(record, "MAX_BYTES", 24 + 16 + len(FRAME) + 10)
    many = Recorder(tmp_path / "big", opener=lambda interface, mac: FakeSocket([FRAME] * 5),
                    clock=Clock(0.0))
    name = many.start("enp4s0", PHONE, "phone", seconds=60)
    _finish(many)
    meta = json.loads((tmp_path / "big" / name).with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["packets"] == 1 and "МБ" in meta["why"]


def test_only_the_last_records_are_kept_and_names_are_checked(tmp_path):
    clock = Clock(400.0)  # каждая запись — в свою секунду имени и сразу кончается
    recorder = Recorder(tmp_path, opener=lambda interface, mac: FakeSocket([FRAME]), clock=clock)
    names = []
    for _ in range(record.KEEP + 2):
        names.append(recorder.start("enp4s0", PHONE, "phone", seconds=60))
        _finish(recorder)
    assert sorted(path.name for path in tmp_path.glob("*.pcap")) == sorted(names[-record.KEEP:])
    assert len(list(tmp_path.glob("*.json"))) == record.KEEP
    for bad in ("../panel-token", names[-1].replace(".pcap", ".json"), "x.pcap", names[0]):
        assert recorder.path(bad) is None
    assert recorder.remove(names[-1]) is True and recorder.path(names[-1]) is None


def test_start_is_refused_with_a_reason(tmp_path):
    def denied(interface, mac):
        raise PermissionError(1, "Operation not permitted")

    with pytest.raises(RecordError, match="CAP_NET_RAW"):
        Recorder(tmp_path, opener=denied).start("enp4s0", PHONE, "phone", seconds=60)
    with pytest.raises(RecordError, match="от 10 до 300"):
        Recorder(tmp_path).start("enp4s0", PHONE, "phone", seconds=5)


# --- панель ---------------------------------------------------------------------------


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    instance = Rig(tmp_path, monkeypatch)
    instance.panel.recorder.opener = lambda interface, mac: FakeSocket([FRAME] * 3)
    instance.panel.recorder.clock = Clock(1.0)
    yield instance
    instance.panel.stop()


def test_panel_records_a_device_and_serves_the_file_only_after_login(rig):
    rig.lease()
    rig.client.login()
    result = rig.client.act("record/start", {"mac": PHONE.upper(), "seconds": 120})
    assert result["ok"] and "Записываю трафик «phone» — 2 мин" in result["text"]
    _finish(rig.panel.recorder)
    files = rig.client.state()["records"]["files"]
    assert len(files) == 1 and files[0]["label"] == "phone" and files[0]["packets"] == 3
    name = files[0]["name"]
    response, data = _download(rig.client, f"/records/{name}", rig.client.cookie)
    assert response.status == 200 and len(_records(data)) == 3
    assert response.getheader("Content-Type") == "application/vnd.tcpdump.pcap"
    assert f'filename="xgw-{name}"' in response.getheader("Content-Disposition")
    for bad in ("../panel-token", "nothing.pcap"):
        assert _download(rig.client, f"/records/{bad}", rig.client.cookie)[0].status == 404
    assert _download(rig.client, f"/records/{name}")[0].status == 401  # без входа
    events = [event["detail"] for event in rig.client.state()["events"]]
    assert any("запись трафика «phone» начата" in text for text in events)
    assert any("запись трафика «phone» готова" in text for text in events)
    assert rig.client.act("record/remove", {"name": name})["ok"]
    assert rig.client.state()["records"]["files"] == []


def test_panel_record_requests_are_checked(rig):
    rig.client.login()
    assert not rig.client.act("record/start", {"mac": "nope"})["ok"]
    assert not rig.client.act("record/start", {"mac": PHONE, "seconds": "60"})["ok"]
    assert not rig.client.act("record/remove", {"name": "../panel-token"})["ok"]
    assert rig.client.act("record/stop", {})["text"] == "Записи сейчас нет"


def test_recording_needs_free_disk_space_and_stops_when_it_runs_out(tmp_path):
    """ДОП-1: на диске меньше MIN_FREE + MAX_BYTES — запись не начинается; место кончается во
    время записи — она останавливается, файл остаётся."""
    sock = FakeSocket([])
    small = Recorder(tmp_path, opener=lambda interface, mac: sock,
                     free=lambda _path: record.MIN_FREE)
    with pytest.raises(RecordError, match="на диске мало места"):
        small.start("enp4s0", PHONE, "phone", seconds=60)
    assert sock.closed
    left = [record.MIN_FREE + record.MAX_BYTES, 0]
    clock = Clock(1.0)
    recorder = Recorder(tmp_path, opener=lambda interface, mac: FakeSocket([FRAME] * 50),
                        clock=clock, free=lambda _path: left.pop(0) if len(left) > 1 else left[0])
    name = recorder.start("enp4s0", PHONE, "phone", seconds=60)
    _finish(recorder)
    meta = json.loads((tmp_path / name).with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["why"] == "на диске кончается место" and record.MAX_SECONDS == 300


def test_download_goes_in_chunks_and_at_most_two_at_once(tmp_path, monkeypatch):
    """Пятый аудит: запись отдаётся кусками (не целиком в память), не больше двух скачиваний
    сразу, а медленный получатель не держит поток дольше SEND_DEADLINE."""
    import io

    path = tmp_path / "x.pcap"
    path.write_bytes(b"a" * 200_000)
    out = io.BytesIO()
    assert record.send_file(path, 150_000, out) is True
    assert out.getvalue() == b"a" * 150_000  # сколько обещано в Content-Length — не больше
    with (record.download_slot(), record.download_slot(), pytest.raises(record.Busy),
          record.download_slot()):
        pass  # третье место не даётся
    with record.download_slot():
        pass  # места освобождаются
    ticks = iter(range(0, 10_000, 400))
    monkeypatch.setattr(record, "SEND_DEADLINE", 1000.0)
    assert record.send_file(path, 200_000, io.BytesIO(), clock=lambda: next(ticks)) is False
