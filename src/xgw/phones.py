"""Телефоны, привязанные к шлюзу (А1 `ANDROID_APP_PLAN.md`): приложение XGW для Android
управляет шлюзом через Tailscale Funnel.

Привязка — одноразовый код из QR в панели: приложение отправляет его в `POST /api/pair` и
получает свой ключ (32 случайных байта). Ключ телефон сразу кладёт в Android Keystore как
ключ HMAC-SHA256 — прочитать его оттуда нельзя, только подписывать. Дальше каждый запрос
подписан: телефон, метод, путь, время, случайное число, хеш тела (`signed_text`). Шлюз
проверяет подпись, время (±SKEW) и что случайное число не повторялось.

Хранится в /var/lib/xgw/phones.json (0600): имя, ключ, когда привязан, когда был последний
запрос. Пишут его только потоки демона (панель и API приложения) — блокировка в процессе.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .paths import Paths, atomic_write_json

PAIR_TTL = 600.0  # сколько живёт код из QR, секунд
SKEW = 60.0  # насколько время в запросе может расходиться с часами шлюза
MAX_PHONES = 10
MAX_NAME = 40
SEEN_EVERY = 60.0  # «последний запрос» записывается на диск не чаще
# Принятые случайные числа запросов — и в файле в /run/xgw (память, не диск): после
# перезапуска демона тот же подписанный запрос в пределах SKEW принят бы снова (четвёртый аудит
# 0.2.0, ASSUMPTIONS п. 253).
NONCES_FILE = "phone-nonces.json"
_ID_RE = re.compile(r"[0-9a-f]{12}")
_NONCE_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")
_CODE_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")
_NAME_DROP = re.compile(r"[\x00-\x1f\x7f<>\"'`]")


class PhoneBusy(Exception):
    """Подпись верна, но телефон спрашивает чаще предела: отметка запроса не записана."""


class NonceStoreError(Exception):
    """Подпись верна, но отметка принятого запроса не записана в /run/xgw: после перезапуска
    демона тот же запрос прошёл бы снова. phone — кто спрашивал."""

    def __init__(self, phone: Phone, reason: str) -> None:
        super().__init__(reason)
        self.phone = phone


class PhoneError(Exception):
    """Запрос не принят; текст — для журнала шлюза, телефону уходит общий ответ."""


def store_file(paths: Paths) -> Path:
    return paths.var / "phones.json"


def clean_name(name: object) -> str:
    """Имя телефона для панели: без управляющих символов и разметки, не длиннее MAX_NAME."""
    text = _NAME_DROP.sub("", name if isinstance(name, str) else "").strip()
    return text[:MAX_NAME] or "Телефон"


def signed_text(phone: str, method: str, path: str, stamp: str, nonce: str, body: bytes) -> bytes:
    """Что подписывает телефон: строки через перевод строки, тело — его SHA-256."""
    digest = hashlib.sha256(body).hexdigest()
    return "\n".join((phone, method.upper(), path, stamp, nonce, digest)).encode("utf-8")


def sign(key: bytes, phone: str, method: str, path: str, stamp: str, nonce: str,
         body: bytes) -> str:
    """Подпись запроса — то же, что делает приложение ключом из Keystore."""
    message = signed_text(phone, method, path, stamp, nonce, body)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Phone:
    id: str
    name: str
    paired: float
    seen: float | None


class Phones:
    def __init__(self, paths: Paths, clock: Callable[[], float] = time.time) -> None:
        self.paths = paths
        self.clock = clock
        self._lock = threading.Lock()
        self._pair: dict | None = None  # {"code", "until"} — код из QR, один
        self._paired_last: str = ""  # id телефона, привязанного по последнему коду
        self._nonces: dict[str, float] = {}  # «телефон:случайное число» → когда пришло
        self._nonces_read = False
        self._seen_saved: dict[str, float] = {}

    # --- файл ---------------------------------------------------------------------

    def _load(self) -> dict[str, dict]:
        try:
            raw = json.loads(store_file(self.paths).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        phones = raw.get("phones") if isinstance(raw, dict) else None
        result: dict[str, dict] = {}
        for phone_id, item in (phones.items() if isinstance(phones, dict) else ()):
            if not (isinstance(phone_id, str) and _ID_RE.fullmatch(phone_id)
                    and isinstance(item, dict) and isinstance(item.get("key"), str)):
                continue
            try:
                key = base64.b64decode(item["key"], validate=True)
            except ValueError:
                continue
            if len(key) != 32:
                continue
            result[phone_id] = {
                "key": item["key"], "name": clean_name(item.get("name")),
                "paired": float(item.get("paired") or 0),
                "seen": float(item["seen"]) if isinstance(item.get("seen"), (int, float))
                else None,
            }
        return result

    def _save(self, phones: dict[str, dict]) -> None:
        atomic_write_json(store_file(self.paths), {"phones": phones}, mode=0o600)

    def _read_nonces(self) -> None:
        """Числа, принятые до перезапуска (один раз за жизнь объекта; файла нет — их нет)."""
        if self._nonces_read:
            return
        self._nonces_read = True
        try:
            raw = json.loads((self.paths.run / NONCES_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            for marker, when in raw.items():
                if isinstance(marker, str) and isinstance(when, (int, float)):
                    self._nonces.setdefault(marker, float(when))

    # --- для панели ---------------------------------------------------------------

    def listing(self) -> list[Phone]:
        with self._lock:
            phones = self._load()
        return sorted(
            (Phone(phone_id, item["name"], item["paired"], item["seen"])
             for phone_id, item in phones.items()),
            key=lambda phone: phone.paired,
        )

    def new_code(self) -> str:
        """Код для QR: один на шлюз — новый заменяет прежний."""
        code = secrets.token_urlsafe(24)
        with self._lock:
            self._pair = {"code": code, "until": self.clock() + PAIR_TTL}
            self._paired_last = ""
        return code

    def pairing(self) -> dict:
        """Состояние QR для панели: code и until — пока код жив; paired — телефон, который
        им привязался (QR гаснет сам)."""
        with self._lock:
            pair, paired = self._pair, self._paired_last
            if pair is not None and pair["until"] <= self.clock():
                self._pair = pair = None
        return {
            "code": pair["code"] if pair else "", "until": pair["until"] if pair else None,
            "paired": paired,
        }

    def cancel(self) -> None:
        with self._lock:
            self._pair = None

    def rename(self, phone_id: str, name: str) -> bool:
        with self._lock:
            phones = self._load()
            if phone_id not in phones:
                return False
            phones[phone_id]["name"] = clean_name(name)
            self._save(phones)
            return True

    def revoke(self, phone_id: str) -> bool:
        """Отвязать: запросы с этим ключом отклоняются сразу же."""
        with self._lock:
            phones = self._load()
            if phones.pop(phone_id, None) is None:
                return False
            self._save(phones)
            self._seen_saved.pop(phone_id, None)
            return True

    # --- для API приложения -------------------------------------------------------

    def pair(self, code: object, name: object) -> tuple[str, bytes]:
        """Код из QR → (id телефона, ключ). Код гасится при успехе, по сроку PAIR_TTL и
        отменой в панели. Неверные коды его не гасят (пятый аудит, A5): код — 32 случайных
        символа (192 бита), подобрать его нельзя, а чужие запросы через Funnel гасили бы QR на
        экране заказчика; частые неудачи закрывает блокировка API (appapi.FAILS_MAX)."""
        if not isinstance(code, str) or not _CODE_RE.fullmatch(code):
            raise PhoneError("код привязки не того вида")
        with self._lock:
            pair = self._pair
            if pair is None or pair["until"] <= self.clock():
                self._pair = None
                raise PhoneError("код привязки не запрашивался или истёк")
            if not hmac.compare_digest(code.encode("ascii"), pair["code"].encode("ascii")):
                raise PhoneError("неверный код привязки")
            self._pair = None
            phones = self._load()
            if len(phones) >= MAX_PHONES:
                raise PhoneError(f"телефонов уже {MAX_PHONES} — отвяжите лишние в панели")
            phone_id = secrets.token_hex(6)
            key = secrets.token_bytes(32)
            phones[phone_id] = {
                "key": base64.b64encode(key).decode("ascii"), "name": clean_name(name),
                "paired": self.clock(), "seen": None,
            }
            self._save(phones)
            self._paired_last = phone_id
        return phone_id, key

    def verify(
        self, headers, method: str, path: str, body: bytes,
        admit: Callable[[str], bool] | None = None,
    ) -> Phone:
        """Подпись запроса (заголовки X-XGW-Phone, -Time, -Nonce, -Signature); иначе
        PhoneError."""
        phone_id = str(headers.get("X-XGW-Phone") or "")
        stamp = str(headers.get("X-XGW-Time") or "")
        nonce = str(headers.get("X-XGW-Nonce") or "")
        signature = str(headers.get("X-XGW-Signature") or "")
        if not (_ID_RE.fullmatch(phone_id) and _NONCE_RE.fullmatch(nonce)
                and re.fullmatch(r"\d{9,12}", stamp) and re.fullmatch(r"[0-9a-f]{64}", signature)):
            raise PhoneError("нет подписи или она не того вида")
        now = self.clock()
        if abs(now - int(stamp)) > SKEW:
            raise PhoneError("время в запросе расходится с часами шлюза больше чем на минуту")
        with self._lock:
            phones = self._load()
            item = phones.get(phone_id)
            if item is None:
                raise PhoneError("телефон не привязан или отвязан")
            key = base64.b64decode(item["key"])
            expected = sign(key, phone_id, method, path, stamp, nonce, body)
            if not hmac.compare_digest(expected, signature):
                raise PhoneError("подпись не сходится")
            self._read_nonces()
            for seen_nonce, when in list(self._nonces.items()):
                if now - when > 2 * SKEW:
                    del self._nonces[seen_nonce]
            marker = f"{phone_id}:{nonce}"
            if marker in self._nonces:
                raise PhoneError("повтор запроса")
            if admit is not None and not admit(phone_id):
                raise PhoneBusy("слишком часто")
            self._nonces[marker] = now
            stored = ""
            try:
                atomic_write_json(self.paths.run / NONCES_FILE, self._nonces, mode=0o600)
            except OSError as exc:
                stored = str(exc) or type(exc).__name__
            if now - self._seen_saved.get(phone_id, 0.0) >= SEEN_EVERY:
                item["seen"] = now
                with contextlib.suppress(OSError):
                    self._save(phones)
                self._seen_saved[phone_id] = now
            phone = Phone(phone_id, item["name"], item["paired"], item["seen"])
            if stored:
                raise NonceStoreError(phone, stored)
            return phone
