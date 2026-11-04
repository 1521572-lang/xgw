# Отчёт: XGW 0.2.0 — wave3b, установка и связь

Это шаблон; незаполненные результаты NOT_RUN. Дата/время и часовой пояс: NOT_RUN.
Исполнитель/модель: NOT_RUN. Устройство/ОС/systemd: NOT_RUN.
Исходный HEAD: NOT_RUN. Кодf4a27b7f0893e78f44481087d9fd64e2fd01654f; фактический HEAD/tree: NOT_RUN.
Fingerprint frozen safety.py / исходного helper: NOT_RUN.

## Согласие и исходная база

Ответы по страховке/off-установке/enable/повторной on-установке: NOT_RUN.
Начальный режим VPN/pool, ядра/ручной выбор, фактическая связь владельца: NOT_RUN.
Секреты, адреса, MAC, имена устройств и сырые журналы не включать.

## Результаты

| Шаг | PASS/FAIL/INCONCLUSIVE/NOT_RUN | Факт / evidence |
|---|---|---|
| Код/helper/чистая freepool | NOT_RUN | — |
| Предварительный автономный возврат при off | NOT_RUN | — |
| Время от запуска safety до RESTORED_OFF / recovery_seconds | NOT_RUN | — |
| Связь модели и владельца после автономного опыта | NOT_RUN | — |
| Установка из off: job rc / фактический режим | NOT_RUN | — |
| Enable под независимой страховкой | NOT_RUN | — |
| Новые соединения и связь через30с | NOT_RUN | — |
| Переустановка из on: job rc / фактический режим | NOT_RUN | — |
| Guard / SB UID+caps / Capture.loaded / mismatch | NOT_RUN | — |
| Disarm либо автономный возврат после потери lease | NOT_RUN | — |
| Итоговый режим и связь владельца | NOT_RUN | — |

## Связь и атрибуция

| Момент | WAN carrier/operstate | LAN carrier/operstate | Новый plain TCP | Новый marked TCP | Сеанс владельца | Состояние safety/job |
|---|---|---|---|---|---|---|
| До | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| После off-install | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| После enable | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| После on-install | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Итог | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

Различать physical link-down, отказ маршрута/перехвата, недоступность тестовой цели и обрыв
старой direct-сессии. Без соответствующего evidence причинность не установлена.

## Дефекты и ограничения

D1 (сохранение on/установка): NOT_RUN. D2 (потеря связи): NOT_RUN.
Срабатывание safety: NOT_RUN; причина — отсутствие pulse/ошибка/потеря связи/не установлено.
Прекращение теста по lease не равно установленному дефекту VPN.
Полный E4/WAN, scoped faults, UDP/IPv6/LAN payload,10минутная нагрузка: NOT_RUN.
Сырые snapshot/off.nft/job.log остаются root0700 на машине и не публикуются.
