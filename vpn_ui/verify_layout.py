"""Авторендер четырёх состояний окна и сверка вёрстки с эталонными размерами.

    python3 vpn_ui/verify_layout.py [--out DIR] [--scale 1.25] [--theme dark]

Без дисплея работает через QT_QPA_PLATFORM=offscreen. Код возврата 0 — все проверки
прошли. Эталон снят при масштабе 125 %, поэтому снимки по умолчанию делаются в нём же
(1252×813 точек), а размеры сверяются в логических единицах.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RENDERS = ("state_01_disconnected", "state_02_connecting", "state_03_connected_with_traffic",
           "state_04_settings_open")
BAD_MESSAGE = ("qpainter", "stylesheet", "could not parse", "unknown property", "qss",
               "qlayout", "qfont")

# Размеры из снимка живого окна (uia_layout_dump.json), делённые на 1,25: (x, y, w, h).
# None — координата не сверяется (зависит от данных, а не от вёрстки).
TARGETS = {
    "window": (None, None, 1002, 650),
    "title_bar": (0, 0, None, 38),
    "sidebar": (8, 38, 280, 604),
    "search_box": (21, 51, 254, 36),
    "nav_countries": (17, 103, None, 34),
    "country_row": (17, None, 252, 48),
    "widget_bar": (884, 38, 110, None),
    "widget_tile": (890, 46, 97, 66),
    "card_badge": (None, 42, 54, 36),
    "connect_button": (461, 138, 250, 39),
    "status_row": (306, 556, None, 20),
    "detail_row": (296, 588, 227, 54),
}
TOLERANCE = 8  # допуск задачи — 5–10 точек


def _expect(name: str, actual: tuple[int, int, int, int]) -> dict:
    target = TARGETS[name]
    deltas = [None if wanted is None else got - wanted
              for wanted, got in zip(target, actual, strict=True)]
    ok = all(delta is None or abs(delta) <= TOLERANCE for delta in deltas)
    return {"name": name, "target": target, "actual": actual, "delta": deltas, "ok": ok}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Рендер состояний окна и проверка вёрстки")
    parser.add_argument("--out", default="_verification_renders")
    parser.add_argument("--scale", type=float, default=1.25)
    parser.add_argument("--theme", choices=("dark", "light"), default="dark")
    args = parser.parse_args(argv)
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
            or sys.platform in ("win32", "darwin")):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)

    from vpn_ui.core.bridge import VpnUiBridge
    from vpn_ui.core.state import ConnectionState
    from vpn_ui.main_demo import DEMO_VPN_IP, MockBackendController
    from vpn_ui.qt import BINDING, QtCore, QtWidgets
    from vpn_ui.views.main_window import MainWindow, prepare_application
    from vpn_ui.views.settings_drawer_view import SettingsDrawerView
    from vpn_ui.views.sidebar_view import ServerRow

    messages: list[str] = []

    def handler(_kind: object, _context: object, text: str) -> None:
        messages.append(str(text))

    QtCore.qInstallMessageHandler(handler)
    app = QtWidgets.QApplication(sys.argv[:1])
    prepare_application(app)
    bridge = VpnUiBridge()
    bridge.settings.theme = args.theme
    window = MainWindow(bridge, use_custom_titlebar=True)
    backend = MockBackendController(bridge, seed=7, parent=window)
    window.show()

    def settle(milliseconds: int = 0) -> None:
        """Дать окну отработать события и анимации."""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(max(1, milliseconds), loop.quit)
        loop.exec()
        app.processEvents()

    def box(widget: QtWidgets.QWidget) -> tuple[int, int, int, int]:
        origin = widget.mapTo(window, QtCore.QPoint(0, 0))
        return (origin.x(), origin.y(), widget.width(), widget.height())

    def text_problems() -> list[str]:
        """Подписи, которым не хватает высоты или ширины."""
        found = []
        for label in window.findChildren(QtWidgets.QLabel):
            if not label.isVisible() or not label.text():
                continue
            metrics = label.fontMetrics()
            room = label.contentsRect()
            wrapped = label.wordWrap()
            needed = label.heightForWidth(label.width()) if wrapped else metrics.height()
            name = label.objectName() or "QLabel"
            if label.height() + 1 < needed:
                found.append(f"{name}: высота {label.height()} < {needed} «{label.text()[:30]}»")
            if not wrapped and not label.property("elide") \
                    and metrics.horizontalAdvance(label.text()) > room.width() + 1:
                found.append(f"{name}: ширина {room.width()} мала для «{label.text()[:30]}»")
        return found

    def overlaps() -> list[str]:
        """Элементы управления одного слоя, которые налезают друг на друга."""
        kinds = (QtWidgets.QLabel, QtWidgets.QAbstractButton, QtWidgets.QLineEdit,
                 QtWidgets.QComboBox)
        items = []
        for widget in window.findChildren(QtWidgets.QWidget):
            if not isinstance(widget, kinds) or not widget.isVisible():
                continue
            if isinstance(widget, QtWidgets.QLabel) and not widget.text() \
                    and widget.pixmap().isNull():
                continue
            seen = widget.visibleRegion().boundingRect()
            if seen.width() < 3 or seen.height() < 3:
                continue
            rect = QtCore.QRect(widget.mapTo(window, seen.topLeft()), seen.size())
            layer = any(isinstance(parent, SettingsDrawerView)
                        for parent in _ancestors(widget))
            items.append((widget, rect.adjusted(1, 1, -1, -1), layer))
        found = []
        for index, (first, first_rect, first_layer) in enumerate(items):
            for second, second_rect, second_layer in items[index + 1:]:
                if first_layer != second_layer or first.isAncestorOf(second) \
                        or second.isAncestorOf(first):
                    continue
                common = first_rect.intersected(second_rect)
                if common.width() > 2 and common.height() > 2:
                    found.append(f"{_title(first)} × {_title(second)}: {common.width()}×"
                                 f"{common.height()}")
        return found

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"binding": BINDING, "scale": args.scale, "theme": args.theme,
                    "platform": app.platformName(), "renders": {}, "geometry": [],
                    "text": {}, "overlap": {}}

    def capture(name: str) -> None:
        settle(60)
        image = window.grab()
        image.save(str(out / f"{name}.png"))
        report["renders"][name] = [image.width(), image.height()]
        report["text"][name] = text_problems()
        report["overlap"][name] = overlaps()

    # 1. Отключено — на этом состоянии сверяется геометрия с эталоном.
    settle(150)
    capture(RENDERS[0])
    country = next(row for row in window.sidebar.rows if row.kind == "country")
    measured = {
        "window": (0, 0, window.width(), window.height()),
        "title_bar": box(window.titlebar),
        "sidebar": box(window.sidebar),
        "search_box": box(window.sidebar.search),
        "nav_countries": box(window.sidebar.nav_buttons["countries"]),
        "country_row": box(country),
        "widget_bar": box(window.widgets),
        "widget_tile": box(window.widgets.tiles["kill_switch"]),
        "card_badge": box(window.card.badge),
        "connect_button": box(window.card.connect_button),
        "status_row": box(window.details.badge),
        "detail_row": box(window.details.rows["ip"]),
    }
    report["geometry"] = [_expect(name, actual) for name, actual in measured.items()]
    assert isinstance(country, ServerRow)

    # 2. Подключение: кольцо ожидания, белое свечение, кнопка «Отмена».
    bridge.update_connection_state(ConnectionState.CONNECTING, "nl-1")
    settle(400)
    capture(RENDERS[1])

    # 3. Подключено: минута телеметрии от имитации бэкенда.
    backend.target = "nl-1"
    backend.down, backend.up = 18e6, 2.4e6
    bridge.update_connection_state(ConnectionState.CONNECTED, "nl-1")
    for _ in range(45):
        backend.tick()
    settle(500)
    capture(RENDERS[2])
    report["telemetry_ip_is_demo"] = bridge.stats.client_ip == DEMO_VPN_IP

    # 4. Открыты настройки.
    window.open_settings(animate=False)
    settle(150)
    capture(RENDERS[3])

    bad = [text for text in messages if any(mark in text.lower() for mark in BAD_MESSAGE)]
    report["qt_messages"] = messages
    checks = {
        "renders": len(report["renders"]) == 4,
        "geometry": all(item["ok"] for item in report["geometry"]),
        "text": not any(report["text"].values()),
        "overlap": not any(report["overlap"].values()),
        "qt_messages": not bad,
    }
    report["checks"] = checks
    (out / "report.json").write_bytes(
        (json.dumps(report, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))

    print(f"binding={BINDING} platform={report['platform']} scale={args.scale}")
    for item in report["geometry"]:
        print(f"{'OK  ' if item['ok'] else 'FAIL'} {item['name']:<15} цель={item['target']} "
              f"факт={item['actual']}")
    for section in ("text", "overlap"):
        for name, problems in report[section].items():
            for problem in problems:
                print(f"FAIL {section} {name}: {problem}")
    for text in bad:
        print(f"FAIL qt: {text}")
    for name, ok in checks.items():
        print(f"RESULT {name}={'PASS' if ok else 'FAIL'}")
    total = all(checks.values())
    print(f"VERIFY_LAYOUT={'PASS' if total else 'FAIL'} renders={out.resolve()}")
    window.close()
    return 0 if total else 1


def _ancestors(widget):
    parent = widget.parentWidget()
    while parent is not None:
        yield parent
        parent = parent.parentWidget()


def _title(widget) -> str:
    text = widget.text() if hasattr(widget, "text") and callable(widget.text) else ""
    name = widget.objectName() or type(widget).__name__
    return f"{name}«{str(text)[:18]}»" if text else name


if __name__ == "__main__":
    raise SystemExit(main())
