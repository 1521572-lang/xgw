# Ubuntu 24.04 — список серверов и карта — YYYY-MM-DD

- RESULT: PASS / PARTIAL / FAIL / BLOCKED
- BASE / CODE / GUI_BASE / HOTFIX:
- ОС / ядро / Python / Qt / nft / nfqws2 / curl:
- Исполнитель сам выполнил команды и vision:
- Установленный backend / GUI path; INSTALLED или PREVIEW:
- GeoIP source SHA, число стран; без адресов серверов:

| Проверка | PASS / FAIL / NOT_RUN | Подтверждение |
|---|---|---|
| Portable и Linux regression | | |
| Qt tests без skip / Ruff | | |
| Baseline / backup / независимый timer | | |
| LIVE_NAME_COUNTRY (3 строки, API и IP-страна) | | |
| LIVE_HEADERS (3 заголовка × 2 направления) | | |
| LIVE_MAP (наблюдение анимации несколько секунд) | | |
| FIXTURE_MAP_TRANSITION / stale / off / standalone | | |
| LIVE_LAYOUT / hover / выбор / прокрутка / обе темы | | |
| ZAPRET_REGRESSION | | |
| Нет POST выбора/смены маршрутов от просмотра | | |
| Настройки / Xray PID / сеть неизменны | | |
| Установленные SHA после отмены timer | | |
| Откат при необходимости | | |

Причины отсутствующих стран фиксировать без приватных IP/доменов. Не подменять страну
именем подписки. PASS на фикстурах не заменяет живую проверку установленного приложения.

## Осталось на машине

- Код и GUI, сохранённая база, хэши:
- Службы, worker, маршруты и настройки:
- Timer/service, backup:
- Нерешённые проблемы и хотфиксы:
- YouTube: NOT_RUN по скоупу этого прохода.
- Публикация: отчёт следующим коммитом; собственный SHA заранее не требуется.
