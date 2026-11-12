# vpn_ui — окно VPN-клиента на Qt6

Самостоятельный пакет: вёрстка, тема и мост для своего бэкенда. Сетевых вызовов в нём нет.
Вид и размеры повторяют открытый клиент Proton VPN, имя и логотип
Proton не используются.

## Запуск

```bash
python3 vpn_ui/main_demo.py --demo                 # окно с имитацией бэкенда
python3 vpn_ui/main_demo.py --demo --theme light   # светлая тема
python3 vpn_ui/main_demo.py --demo --native-titlebar   # системная рамка окна
python3 vpn_ui/verify_layout.py                    # снимки 4 состояний и сверка вёрстки
```

Нужен Python 3.12 и Qt6 с модулем QtSvg. Основная привязка — PySide6; если её нет,
`vpn_ui/qt.py` берёт PyQt6 (код написан в общем подмножестве обеих).

## Как подключить свой бэкенд

Всё общение идёт через `core/bridge.py` → `VpnUiBridge`:

| Окно → бэкенд (сигналы) | Когда |
|---|---|
| `connect_requested(str)` | выбран сервер, профиль, шлюз или `"auto"` (самый быстрый) |
| `disconnect_requested()` | «Отключить» или «Отмена» |
| `feature_toggled(str, bool)` | `kill_switch`, `split_tunneling`, `custom_dns`, `lan_bypass` |
| `protocol_changed(str)` | `xray`, `sing-box`, `wireguard`, `openvpn` |
| `settings_updated(dict)` | тема, маршрутизация, интерфейс, адрес DNS, автоподключение |

| Бэкенд → окно (методы) | Что меняет |
|---|---|
| `update_connection_state(state, server_id=None, detail="")` | свечение, карточку, статус |
| `update_telemetry(down_bps, up_bps, total_down, total_up, ping_ms, client_ip)` | метрики, график |
| `set_server_list(list[ServerNode])` | левую панель и отметки на карте |
| `update_features(FeaturesState)` | плитки справа и переключатели настроек |
| `set_location(LocationInfo)` | нижнюю полосу без VPN и точку на карте |
| `set_notice(str)` | карточку-сообщение над списком серверов |

Окно само состояние не выдумывает: нажатие плитки шлёт `feature_toggled`, а картинка
меняется, когда бэкенд ответит `update_features`. Пример — `MockBackendController`
в `main_demo.py`.

## Устройство

- `core/` — состояния (dataclass) и мост; `theme/` — токены, генератор QSS, загрузчик SVG;
- `components/` — виджеты на QPainter: переключатель, строка статуса, плитка, график, шапка;
- `views/` — левая панель, карта, карточка подключения, настройки, главное окно.

Размеры — в логических единицах XAML (`theme/tokens.py`). Эталонный снимок снят при
масштабе 125 %, поэтому его пиксели делятся на 1,25: окно 1002×650, левая панель 280,
правая 110, шапка 38, кнопка подключения 250×39. Пороги ширины: уже 885 — левая панель
сворачивается в значки, уже 1000 — правая панель без подписей.

## Ассеты и лицензия

`assets/` (иконки, флаги, иллюстрации, карта мира) взяты из репозитория
`github.com/ProtonVPN/win-app`, лицензия GPL-3.0 — см. `assets/NOTICE.md`.
Распространять пакет вместе с этими файлами можно только на условиях GPL-3.0.
