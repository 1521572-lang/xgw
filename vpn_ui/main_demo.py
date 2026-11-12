"""Запуск окна с имитацией бэкенда: всё можно прокликать без сети и без прав.

    python3 vpn_ui/main_demo.py --demo [--theme light] [--native-titlebar] [--scale 1.25]

Настоящий бэкенд подключается так же, как MockBackendController: слушает сигналы
намерений моста и вызывает его методы `update_*` / `set_*`.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

if __package__ in (None, ""):  # запуск файлом: пакет ищется от родительской папки
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vpn_ui.core.bridge import VpnUiBridge
from vpn_ui.core.state import (
    AUTO_ID,
    GROUP_GATEWAYS,
    GROUP_PROFILES,
    ConnectionState,
    FeaturesState,
    LocationInfo,
    ServerNode,
    best_node,
)
from vpn_ui.qt import BINDING, QtCore, QtWidgets

# Адреса — из диапазонов для документации (RFC 5737), настоящих здесь нет.
DEMO_LOCATION = LocationInfo("203.0.113.24", "Россия", "Домашний провайдер", "RU")
DEMO_VPN_IP = "198.51.100.17"
FAILING_ID = "profile-broken"

_COUNTRIES = (
    ("AU", "Австралия", ("Сидней",), 248), ("AT", "Австрия", ("Вена",), 61),
    ("GB", "Великобритания", ("Лондон", "Манчестер"), 58), ("DE", "Германия",
                                                           ("Франкфурт", "Берлин"), 44),
    ("NL", "Нидерланды", ("Амстердам", "Роттердам"), 39), ("PL", "Польша", ("Варшава",), 35),
    ("FI", "Финляндия", ("Хельсинки",), 27), ("FR", "Франция", ("Париж",), 52),
    ("SE", "Швеция", ("Стокгольм",), 33), ("CH", "Швейцария", ("Цюрих",), 49),
    ("US", "США", ("Нью-Йорк", "Лос-Анджелес"), 121), ("JP", "Япония", ("Токио",), 196),
    ("TR", "Турция", ("Стамбул",), 67), ("KZ", "Казахстан", ("Алматы",), 74),
)


def demo_servers() -> list[ServerNode]:
    nodes: list[ServerNode] = []
    protocols = ("xray", "sing-box", "wireguard")
    for index, (code, country, cities, ping) in enumerate(_COUNTRIES):
        for number, city in enumerate(cities, start=1):
            features = {"fast"} if ping < 50 else set()
            if index % 3 == 0:
                features.add("p2p")
            if index % 4 == 1:
                features.add("stream")
            nodes.append(ServerNode(
                id=f"{code.lower()}-{number}", name=f"{code}#{number}", country_code=code,
                country_name=country, city=city, protocol=protocols[(index + number) % 3],
                ping_ms=ping + 6 * (number - 1), load=20 + (index * 7 + number * 11) % 60,
                features=frozenset(features)))
    nodes += [
        ServerNode("profile-stream", "Стриминг", protocol="xray", ping_ms=44,
                   group=GROUP_PROFILES),
        ServerNode("profile-work", "Рабочий профиль", protocol="sing-box", ping_ms=58,
                   group=GROUP_PROFILES),
        ServerNode(FAILING_ID, "Недоступный сервер (проверка ошибки)", protocol="openvpn",
                   group=GROUP_PROFILES),
        ServerNode("gateway-home", "Домашний шлюз", protocol="xray", ping_ms=3,
                   group=GROUP_GATEWAYS),
        ServerNode("gateway-office", "Офисный шлюз", protocol="wireguard", ping_ms=18,
                   group=GROUP_GATEWAYS),
    ]
    return nodes


class MockBackendController(QtCore.QObject):
    """Имитация бэкенда: 1,5 с «подключается», затем раз в секунду шлёт телеметрию."""

    CONNECT_DELAY_MS = 1500

    def __init__(self, bridge: VpnUiBridge, seed: int | None = None,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.random = random.Random(seed)
        self.features = FeaturesState(kill_switch=True)
        self.target = AUTO_ID
        self.down = self.up = 0.0
        self.total_down = self.total_up = 0
        self.connecting = QtCore.QTimer(self)
        self.connecting.setSingleShot(True)
        self.connecting.setInterval(self.CONNECT_DELAY_MS)
        self.connecting.timeout.connect(self._established)
        self.ticker = QtCore.QTimer(self)
        self.ticker.setInterval(1000)
        self.ticker.timeout.connect(self.tick)

        bridge.connect_requested.connect(self.connect_to)
        bridge.disconnect_requested.connect(self.drop)
        bridge.feature_toggled.connect(self.toggle_feature)
        bridge.protocol_changed.connect(lambda name: print(f"[demo] протокол: {name}"))
        bridge.settings_updated.connect(lambda data: print(f"[demo] настройки: {data}"))

        bridge.set_server_list(demo_servers())
        bridge.update_features(self.features)
        bridge.set_location(DEMO_LOCATION)
        bridge.set_notice("Подписка: осталось 35,5 ГБ из 100 ГБ до 1 декабря")
        bridge.update_connection_state(ConnectionState.DISCONNECTED, AUTO_ID)

    # --- намерения окна --------------------------------------------------------------
    def connect_to(self, server_id: str) -> None:
        self.ticker.stop()
        self.target = server_id
        self.bridge.update_connection_state(ConnectionState.CONNECTING, server_id)
        self.connecting.start()

    def drop(self) -> None:  # не `disconnect`: это имя занято у QObject
        self.connecting.stop()
        self.ticker.stop()
        self.bridge.update_connection_state(ConnectionState.DISCONNECTED, self.target)

    def toggle_feature(self, name: str, enabled: bool) -> None:
        self.features = self.features.with_feature(name, enabled)
        self.bridge.update_features(self.features)

    # --- ход «подключения» -----------------------------------------------------------
    def _established(self) -> None:
        if self.target == FAILING_ID:
            self.bridge.update_connection_state(
                ConnectionState.ERROR, self.target,
                "Сервер не ответил за 10 секунд. Выберите другой сервер или повторите.")
            return
        if self.target == AUTO_ID:
            best = best_node([node for node in self.bridge.servers if node.country_code])
            self.target = best.id if best is not None else AUTO_ID
        self.down, self.up = 18e6, 2.4e6
        self.total_down = self.total_up = 0
        self.bridge.update_connection_state(ConnectionState.CONNECTED, self.target)
        self.tick()
        self.ticker.start()

    def tick(self) -> None:
        """Скорость блуждает вокруг прежнего значения, иногда даёт всплеск."""
        burst = 2.5 if self.random.random() < 0.08 else 1.0
        self.down = min(95e6, max(0.4e6, self.down * self.random.uniform(0.72, 1.32) * burst))
        self.up = min(20e6, max(0.1e6, self.up * self.random.uniform(0.7, 1.35)))
        self.total_down += int(self.down / 8)
        self.total_up += int(self.up / 8)
        node = self.bridge.node(self.target)
        base = node.ping_ms if node is not None and node.ping_ms is not None else 40
        self.bridge.update_telemetry(self.down, self.up, self.total_down, self.total_up,
                                     base + self.random.randint(-3, 6), DEMO_VPN_IP)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Окно VPN-клиента с имитацией бэкенда")
    parser.add_argument("--demo", action="store_true", help="включить имитацию бэкенда")
    parser.add_argument("--theme", choices=("dark", "light"), default="dark")
    parser.add_argument("--native-titlebar", action="store_true",
                        help="системная рамка окна вместо своей шапки")
    parser.add_argument("--scale", type=float, default=0.0,
                        help="масштаб интерфейса (например 1.25); по умолчанию — системный")
    args = parser.parse_args(argv)
    if args.scale > 0:
        os.environ["QT_SCALE_FACTOR"] = str(args.scale)

    from vpn_ui.views.main_window import MainWindow, prepare_application

    app = QtWidgets.QApplication(sys.argv[:1])
    prepare_application(app)
    bridge = VpnUiBridge()
    bridge.settings.theme = args.theme
    window = MainWindow(bridge, use_custom_titlebar=not args.native_titlebar)
    if args.demo:
        window.backend = MockBackendController(bridge, parent=window)
    else:
        print("Бэкенд не подключён: окно пустое. Для имитации добавьте --demo.")
    print(f"[demo] привязка Qt: {BINDING}")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
