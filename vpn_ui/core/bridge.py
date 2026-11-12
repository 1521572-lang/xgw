"""Единственный контракт между окном и бэкендом.

Окно → бэкенд: сигналы намерений (`connect_requested` и другие).
Бэкенд → окно: методы `update_*` / `set_*`; они запоминают состояние и рассылают
панелям сигналы `*_changed`. Виджеты сами ничего не запускают и в сеть не ходят.
"""
from __future__ import annotations

from ..qt import QtCore, Signal, Slot
from .state import (
    AUTO_ID,
    FEATURES,
    PROTOCOLS,
    ConnectionSnapshot,
    ConnectionState,
    FeaturesState,
    LocationInfo,
    ServerNode,
    TrafficStats,
    UiSettings,
)


class VpnUiBridge(QtCore.QObject):
    # --- намерения пользователя: их слушает бэкенд ---------------------------------
    connect_requested = Signal(str)  # id сервера, профиля, шлюза или AUTO_ID
    disconnect_requested = Signal()
    feature_toggled = Signal(str, bool)  # kill_switch | split_tunneling | custom_dns | lan_bypass
    protocol_changed = Signal(str)  # xray | sing-box | wireguard | openvpn
    settings_updated = Signal(dict)

    # --- рассылка панелям: их слушают виджеты ---------------------------------------
    connection_changed = Signal(object)  # ConnectionSnapshot
    telemetry_changed = Signal(object)  # TrafficStats
    servers_changed = Signal(object)  # list[ServerNode]
    features_changed = Signal(object)  # FeaturesState
    location_changed = Signal(object)  # LocationInfo
    settings_changed = Signal(object)  # UiSettings
    notice_changed = Signal(str)  # строка в карточке левой панели, пустая — скрыть

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.connection = ConnectionSnapshot()
        self.stats = TrafficStats()
        self.servers: list[ServerNode] = []
        self.features = FeaturesState()
        self.location = LocationInfo()
        self.settings = UiSettings()
        self.notice = ""

    # --- бэкенд → окно ----------------------------------------------------------------
    @Slot(object)
    def update_connection_state(self, state: ConnectionState, server_id: str | None = None,
                                detail: str = "") -> None:
        """Новое состояние подключения; `server_id` — к чему идёт или держится подключение."""
        if not isinstance(state, ConnectionState):
            state = ConnectionState(state)
        target = self.connection.server_id if server_id is None else server_id
        self.connection = ConnectionSnapshot(state, target or AUTO_ID, detail)
        if state is not ConnectionState.CONNECTED:
            self.stats = TrafficStats(client_ip=self.stats.client_ip)
        self.connection_changed.emit(self.connection)

    def update_telemetry(self, down_bps: float, up_bps: float, total_down: int, total_up: int,
                         ping_ms: int, client_ip: str) -> None:
        """Скорости в бит/с, счётчики в байтах. Без `Slot`: счётчики не помещаются в int Qt."""
        self.stats = TrafficStats(float(down_bps), float(up_bps), int(total_down), int(total_up),
                                  int(ping_ms), str(client_ip))
        self.telemetry_changed.emit(self.stats)

    @Slot(list)
    def set_server_list(self, servers: list[ServerNode]) -> None:
        self.servers = list(servers)
        self.servers_changed.emit(self.servers)

    @Slot(object)
    def update_features(self, features: FeaturesState) -> None:
        self.features = features
        self.features_changed.emit(features)

    @Slot(object)
    def set_location(self, location: LocationInfo) -> None:
        self.location = location
        self.location_changed.emit(location)

    @Slot(object)
    def set_settings(self, settings: UiSettings) -> None:
        self.settings = settings
        self.settings_changed.emit(settings)

    @Slot(str)
    def set_notice(self, text: str) -> None:
        self.notice = text
        self.notice_changed.emit(text)

    # --- окно → бэкенд (вызывают виджеты) -------------------------------------------
    def request_connect(self, server_id: str = AUTO_ID) -> None:
        self.connect_requested.emit(server_id or AUTO_ID)

    def request_disconnect(self) -> None:
        self.disconnect_requested.emit()

    def request_feature(self, name: str, enabled: bool) -> None:
        if name not in FEATURES:
            raise KeyError(name)
        self.feature_toggled.emit(name, bool(enabled))

    def request_protocol(self, protocol: str) -> None:
        if protocol not in PROTOCOLS:
            raise KeyError(protocol)
        self.settings.protocol = protocol
        self.protocol_changed.emit(protocol)
        self.settings_changed.emit(self.settings)

    def request_settings(self, **changes: object) -> None:
        for key, value in changes.items():
            if hasattr(self.settings, key) and key != "extra":
                setattr(self.settings, key, value)
            else:
                self.settings.extra[key] = value
        self.settings_updated.emit(self.settings.as_dict())
        self.settings_changed.emit(self.settings)

    # --- справки для панелей ------------------------------------------------------------
    def node(self, server_id: str) -> ServerNode | None:
        return next((node for node in self.servers if node.id == server_id), None)
