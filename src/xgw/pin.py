"""Ручной выбор сервера — как в клиентах VPN: весь трафик через выбранный сервер, пока
человек не вернёт автовыбор (`xgw unpin`, кнопка «Автовыбор» в панели, /unpin в боте).

Запись `pin` в базе (meta), JSON:

- `tag` — тег сервера в ядре: участник (`proxy-…`) или запасной (`spare-…`). Xray
  закрепляет балансировщик (`xray api bo`) и на outbound вне его selector (проверено на
  26.10.10, ASSUMPTIONS п. 191), но на тег, которого нет в конфиге, — тоже, и тогда трафик
  не идёт вовсе (HTTP 503). Роль в теге меняется (запасной стал участником: `spare-nl-8763`
  → `proxy-nl-8763`), а страна и начало отпечатка — нет: по ним сервер и ищется (`resolve`);
- `name` — имя сервера для текстов;
- `until` — когда выбор снимется сам (time.time()); `null` — бессрочно (так выбирает
  панель); у записей до 0.1.10 срок есть всегда;
- `since` — когда выбран;
- `down` — с какого момента выбранный не отвечает: трафик тогда ведёт автовыбор, а выбор
  ждёт, пока сервер снова ответит; `null` или нет — отвечает.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from .generator.builder import NodeInfo

META = "pin"
FOREVER = "forever"  # срок «бессрочно» в действии pin (панель, `xgw pin --ttl forever`)


def parse(raw: str | None) -> dict | None:
    """Запись из базы; None — выбора нет или запись не разобрать."""
    try:
        pin = json.loads(raw or "null")
    except json.JSONDecodeError:
        return None
    if not isinstance(pin, dict) or not isinstance(pin.get("tag"), str) or not pin["tag"]:
        return None
    if pin.get("until") is not None and not isinstance(pin["until"], (int, float)):
        return None
    return pin


def active(pin: dict | None, now: float) -> bool:
    """Выбор действует: есть и срок не вышел (бессрочный — всегда)."""
    return pin is not None and (pin.get("until") is None or float(pin["until"]) > now)


def read(raw: str | None, now: float) -> dict | None:
    """Действующий выбор или None."""
    pin = parse(raw)
    return pin if active(pin, now) else None


def same_server(tag: str, other: str) -> bool:
    """Один ли это сервер: тег без роли (`nl-8763` в `spare-nl-8763`) совпадает."""
    return tag.partition("-")[2] == other.partition("-")[2] != ""


def resolve(pin: dict, nodes: Iterable[NodeInfo]) -> NodeInfo | None:
    """Выбранный сервер среди участников и запасных рабочего конфига; None — его больше
    нет (убран из подписки, отключён)."""
    return next(
        (info for info in nodes
         if info.role in ("proxy", "spare") and same_server(info.tag, pin["tag"])),
        None,
    )


def dumps(pin: dict) -> str:
    return json.dumps(pin, ensure_ascii=False)
