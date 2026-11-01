# Отчёт: XGW 0.2.0 — wave3, guard и отдельный пользователь sing-box

Это шаблон, не отчёт о прохождении. Сохранить заполненную копию локально в
`$HOME/xgw-w3/TEST-REPORT-REAL-MACHINE-0.2.0-wave3-YYYY-MM-DD.md`.
Начальные статусы NOT_RUN заменять только по фактическому сохранённому результату.

## Идентичность и границы

| Поле | Фактическое значение |
|---|---|
| Начало/конец, часовой пояс | NOT_RUN |
| Исполнитель/модель | NOT_RUN |
| ОС/systemd; тип машины | NOT_RUN |
| Исходный HEAD до обновления | NOT_RUN |
| Commit реализации | NOT_RUN (ожидается fd65fc4b18fa8ea658737e9612544bdf63536b4c) |
| HEAD/tree установки | NOT_RUN; source-preflight.txt |
| Runtime diff после commit реализации пуст | NOT_RUN |
| Helper SHA256 | NOT_RUN; ожидается ac3e6d94cb90c66759474204f1a8b7bfbd6d2008dde094d63a5cf2c2389b8b04 |
| Локальный Linux VM/netns gate: документ/команды/дата/результат | NOT_RUN |
| Xray / sing-box до → после | NOT_RUN |
| FreePool до → после | NOT_RUN |
| Ручной выбор до → после | NOT_RUN (только разрешённый тег, без имени/URL) |
| Установка: время, exit code, evidence | NOT_RUN |

Идентичность установленного кода — commit реализации и фактические HEAD/tree установки.
Доставка через Git, отдельный ZIP/patch не применяется. Обновление документов само по себе
не считается изменением runtime, но конкретные хеши всё равно записываются.
Полный ruleset flush, открытый capture, новая FSM, DAE, all-core netns/capless Xray, G1 и
временные FreePool-пробы в эту волну не входят.

## Согласие и остановки

| Пункт | Ответ/ссылка на существующее согласие; время | Что выполнялось |
|---|---|---|
| 1 — установка и возможный обрыв | NOT_RUN | NOT_RUN |
| 2 — isolation и три scoped fault | NOT_RUN | NOT_RUN |
| 3 — 10 минут наблюдения | NOT_RUN | NOT_RUN |

Остановки/recovery: NOT_RUN. Если выполнялись — точный шаг, причина, время `xgw net up`,
итоговое безопасное состояние; без сырых журналов/имён. Молчание не является согласием.

## Кейсы и доказательства

Статусы: PASS — выполнено и соответствует указанному узкому ожиданию; FAIL — подтверждённое
несоответствие; INCONCLUSIVE — выполнено, но гонка/неполная атрибуция/неоднозначность;
NOT_RUN — не выполнялось (указать причину). LOCAL_GUARD_EVIDENCE — категория ограниченного
свидетельства, её нельзя переименовывать в E4 PASS.

| Шаг | Статус | Измеренное / причина | Evidence |
|---|---|---|---|
| 1.0 baseline/чистый клон/таймер | NOT_RUN | — | — |
| 1.2 fingerprint | NOT_RUN | — | — |
| 1.3 исходная функциональная база | NOT_RUN | — | before.txt |
| 2.1 freepool/commit/runtime diff/helper fingerprint | NOT_RUN | — | source-preflight.txt |
| 2.2 установка / actual exit code | NOT_RUN | — | install-rc.txt; install.txt локально |
| 2.3 guard/loaded/эталон/службы/ядра | NOT_RUN | — | after-install.txt; log-install.txt |
| 2.3 фактические UID/GID и capability-наборы SB | NOT_RUN | — | after-install.txt |
| 2.3 permissions / нет routing_mark permanent SB | NOT_RUN | — | after-install.txt |
| 3.1 шесть isolation attempts | NOT_RUN | — | r-31.txt |
| 3.2 scoped flush output | NOT_RUN | — | r-32.txt |
| 3.3 scoped delete ipxgw | NOT_RUN | — | r-33.txt |
| 3.4 exact RPDB pref100 | NOT_RUN | —; при hostTUN не применяется | r-34.txt |
| 4 десять минут | NOT_RUN | — | guard-start/end.txt; log-watch.txt |
| 5 финальное состояние / URI-pattern count | NOT_RUN | — | final.txt; secrets.txt |
| E4 actual WAN-packet evidence на реальной машине | NOT_RUN | WAN sentinel отсутствует; RST/counter недостаточно | — |

## Изоляция постоянного sing-box

| Измерение | Факт |
|---|---|
| MainPID UID/наличие группы xray | NOT_RUN |
| CapEff / CapPrm / CapAmb / CapBnd | NOT_RUN / NOT_RUN / NOT_RUN / NOT_RUN |
| Xray config и каталог owner:group/mode | NOT_RUN |
| SB config и каталог owner:group/mode | NOT_RUN |
| routing_mark count (рекурсивно) | NOT_RUN |
| sing-box → Xray config | NOT_RUN |
| sing-box → Xray UNIX API | NOT_RUN |
| sing-box → запись состояния XGW | NOT_RUN |
| sing-box → nft list tables | NOT_RUN |
| sing-box → ip rule add; cleanup, если неожиданно удалось | NOT_RUN |
| Xray → SB config | NOT_RUN |

runuser показывает обычный UID, а не весь контекст службы. Фактические четыре capability-набора
и группы MainPID проверяются отдельно. Отсутствующий файл/пользователь/API, занятый pref49 и
ошибка инструмента не подтверждают permission isolation.

## Scoped fault: факты без расширения выводов

| Сценарий | До: TCP успешен | Fault-present до/после пробы | Ответ | Guard generation / delta total / final hostTCP | Структурное восстановление, с | После: TCP / loaded | Категория |
|---|---|---|---|---|---|---|---|
| output | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| ipxgw | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| RPDBpref100 | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

RST + положительный final-host-TCP counter delta в одном поколении guard при наблюдённом
повреждении — лишь LOCAL_GUARD_EVIDENCE. Посторонний трафик может повлиять на общий счётчик.
Восстановление до/во время пробы, смена/неизвестность поколения, reset счётчиков и отсутствие
успешной базы — INCONCLUSIVE/NOT_RUN. Соединение при fault-present — повод разбирать путь;
без packet evidence не утверждать утечку. HostTUN использует pref90: тест pref100 с hostprobe
не получает PASS и не заменяется другим тестом без задания/согласия.

## Наблюдение и эксплуатация

| Метрика | До → после / факт |
|---|---|
| Guard total / final outputTCP / other / transit / loopback | NOT_RUN |
| Reload/reset за окно; сопоставимы ли счётчики | NOT_RUN |
| Новые permission/fatal/Traceback | NOT_RUN |
| Sing-box N/A/B, fresh-scanned, отвечает | NOT_RUN |
| HEALTHY / Capture.loaded / baseline mismatch | NOT_RUN |
| Tailscale / time относительно исходной базы | NOT_RUN |
| Количество совпадений только перечисленных URI-patterns | NOT_RUN |

Рост reject без атрибуции потоку — наблюдение, не доказательство ложного блокирования.
Уменьшение alive удалённого узла само по себе не доказывает regression permissions; sbstat —
данные статуса XGW, не независимый payload test. При reload/reset дельты не сравнивать.
Нулевой URI-pattern count не означает, что любые секреты в журнале отсутствуют.

## Покрытие пяти плоскостей и незакрытые ворота

| Плоскость | Проверено | Не проверено / ограничение |
|---|---|---|
| Network egress | NOT_RUN | E4 actual WAN packets; hostIPv4TCP не покрывает LAN/Docker/tailnet/UDP/IPv6 |
| Lifecycle/recovery | NOT_RUN | Полный ruleset flush и новая FSM вне scope |
| Privilege boundary | NOT_RUN | Постоянный SB; временные FreePool-процессы вне scope |
| Install/migration | NOT_RUN | Только фактическая машина и записанные Git-хеши; не универсальная совместимость |
| Operations/privacy | NOT_RUN | Контр-наблюдение не заменяет attribution; журналы не публикуются целиком |

## Подтверждённые дефекты

Пока NOT_RUN. Для каждого: шаг, prereqs, ожидание, измерение, сохранённый безопасный вывод,
восстановление, воспроизводимость и ограничение вывода. Ошибку помощника отделять от source bug.

## Наблюдения / предположения

Пока NOT_RUN. Гипотезы помечать словом «предположение». Непроверенное не называть PASS/FAIL.

## Итог и передача

Фактический итог: NOT_RUN. Непокрытый E4: NOT_RUN — без WAN sentinel/packet artifact на этой
машине. Итог ограничить выполненными кейсами; local readiness не закрывает E4.

Отчёт сохранён локально: NOT_RUN. Отправка обезличенного текста на review: NOT_RUN.
Разрешение на commit/push: NOT_GIVEN. До отдельного явного разрешения не публиковать код,
report или evidence; локальный отчёт не требует commit/push.
