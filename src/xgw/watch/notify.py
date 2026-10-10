"""События и уведомления демона.

Каждое событие пишется в журнал и в SQLite (его видно в `xgw status`).
Уведомление наружу — одно на тип события не чаще min_interval_min. Каналы
доставки (рабочий стол, Telegram) подключаются на этапе 4 как получатели
`sinks`; до тех пор уведомление — это запись в журнале уровня WARNING.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path

from .. import log, masking
from ..store import Store

Sink = Callable[[str, str], None]  # (тип события, текст)


class Notifier:
    def __init__(
        self,
        db_file: Path,
        min_interval_min: int,
        *,
        sinks: Sequence[Sink] = (),
        logger=None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.db_file = db_file
        self.min_interval = max(0, min_interval_min) * 60.0
        self.sinks = list(sinks)
        self.log = logger or log.get_logger("notify")
        self.clock = clock
        self._last_sent: dict[str, float] = {}

    def event(self, kind: str, text: str, *, notify: bool = False) -> bool:
        """Записывает событие; при notify=True ещё и уведомляет. Возвращает True,
        если уведомление ушло (а не было придержано ограничителем частоты)."""
        text = masking.mask_text(text)
        send = notify and self._allowed(kind)
        (self.log.warning if send else self.log.info)("%s: %s", kind, text)
        try:
            store = Store(self.db_file)
            try:
                store.add_event(kind, text)
            finally:
                store.close()
        except Exception as exc:  # событие не должно ронять демон
            self.log.error("событие %s не записано: %s", kind, exc)
        if not send:
            return False
        for sink in self.sinks:
            try:
                sink(kind, text)
            except Exception as exc:
                self.log.error("уведомление %s не доставлено: %s", kind, exc)
        return True

    def _allowed(self, kind: str) -> bool:
        now = self.clock()
        last = self._last_sent.get(kind)
        if last is not None and now - last < self.min_interval:
            return False
        self._last_sent[kind] = now
        return True
