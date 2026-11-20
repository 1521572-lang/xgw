# ThinkCentre — аудит ТЗ MEDIA-PROOF-2026-11-20 — 2026-11-20

- RESULT: **АУДИТ ЗАВЕРШЁН; ТЗ СООТВЕТСТВУЕТ КОДУ, НО ЗАПУСК В ТЕКУЩЕЙ
  СЕССИИ BLOCKED_ENV**. Команды, флаги, API и предпосылка об установленной
  базе сходятся: 67 тестов зелёные, 12/12 cmp. Как есть ТЗ не запускается:
  в сессии нет sudo, на машине нет `rg`, не задан `VIDEO`; три места под
  `set -e` обрывают сценарий до публикации, а в §5 не остановлен
  90-минутный таймер. До запуска нужны правки TZ-01…TZ-10.
- BASE: установленный `/opt/xgw/lib/xgw` = `3a00777…` в 5 файлах поверх
  `08d31ee…` в 7 файлах — 12/12 cmp OK.
- CODE: `1e0c29099eb1c8186c7c7ffb2f4931adfc988596`; `src/xgw` в нём побайтно
  равен `3a00777` (diff 0 строк). TZ: `3f9be87` в `integration/zapret2-batch1`;
  `CODE` — предок TZ.
- ОС: Ubuntu 24.04.5 LTS, ядро 7.0.0-43-generic, amd64; Python 3.12.3,
  mpv 0.37.0, yt-dlp 2026.10.26, curl 8.5.0.
- Машина: off/off, `fresh=true`, `policy_matched=true`, воркеры inactive,
  панель `127.0.0.1:8781/8782`, `nf_conntrack_acct=0`.
- Аудит read-only: `src/`, `packaging/`, `tests/` не менялись; sudo-команды
  не выполнялись (среда их блокирует).

## Проверки, которые сошлись

| Проверка | Результат |
| --- | --- |
| `CODE` — предок TZ `3f9be87` | да; `src/xgw` между `CODE` и TZ не менялся |
| Установленная база | 5/5 = `BASE`, 7/7 = `PREV`; `src/xgw` `CODE` == `BASE` |
| Импорты под `PYTHONPATH=$TOOLS/src:$TOOLS` | `route_evidence`, `selective_probe_watch`, `selective_wan_control` импортируются |
| Тесты §1 | **67 passed** (`test_selective_probe_watch`, `test_desync_route_evidence`, `test_youtube_telemetry`) |
| `route_evidence` | CLI `snapshot` / `delta`; вызовы TZ валидны |
| `selective_probe_watch` | `--seconds 1…180`, `--queue`, `--media-pairs`, `--marked-sockets`; вызовы TZ валидны |
| `headless_playback` | `probe`, `play --seconds 120 --peers --samples`, `--seek-forward 480`; вызовы TZ валидны |
| `selective_media_evidence` | `--player/--gateway/--marked`; порог 32 КиБ на сторону; rc=2 на битых/пустых логах |
| `/api/zapret2/settings` | payload `fake_md5`, YouTube-домены, `youtube_transport_probe=True`, 180/120/512, два `probe_urls` проходит валидацию схемы |
| Подписанный CDN-URL | `valid_youtube_transport(...)` = True для `/videoplayback` из `format-vpn.json` |
| `t11_management_restore.sh` | порядок `py unused backup panel accept` совпадает |
| Отсутствующие transient units | `systemctl show` для `xgw-zapret2/xgw-nfqws2` возвращает rc 0; в off это нормально (`zapret2.py:463`, `systemd-run`) |

## Блокеры

| ID | Где | Проблема | Правка |
| --- | --- | --- | --- |
| TZ-01 | §1, строка 95 | `VIDEO` нигде не присвоен. Под `set -u` `test "${#VIDEO}"` падает с `unbound variable`. Тот же ролик: `8plwv25NYRo` (720p, format 398, duration 36610) | `VIDEO=8plwv25NYRo` до §1 или `: "${VIDEO:?}"` |
| TZ-02 | §1, строки 75 и 77 | `rg -F`; `rg` на машине нет (`command -v rg` пуст). Под `set -e` блок падает | `grep -F` (шаблоны фиксированные) или установить `ripgrep` |
| TZ-03 | весь ТЗ | В сессии нет sudo: `NoNewPrivs=1`, `CapEff=0`; `sudo` отвечает «The "no new privileges" flag is set». §1–§5 требуют root | запускать из обычного терминала с sudo |

## Риски сценария

| ID | Где | Проблема | Правка |
| --- | --- | --- | --- |
| TZ-04 | §3, строки 129–131 | `resolve` и `headless_playback ... probe` не обёрнуты; probe возвращает 2 при неудаче, `set -e` обрывает ТЗ до текста «Если прямой контроль не прошёл…» (строка 124) | `if resolve "$FORMAT" && probe >"$D/direct-check.json"; then … else echo DIRECT_CHECK_FAILED; fi` |
| TZ-05 | §3, строка 214 | `selective_media_evidence` возвращает 2 на битых/пустых логах; `set -e` обрывает до §4/§5 и публикации | `… >"$D/$label-evidence.json" \|\| echo EVIDENCE_PARTIAL` |
| TZ-06 | §5, строки 302–313 | Текст требует «погаси свой таймер», но в блоке нет `systemctl stop "$UNIT.timer"`. Таймер на 90 минут останется и позже снова запустит `restore.sh` (stop `xgw.service`, restore `panel.json`, `xgw apply --now`) уже после теста | добавить `sudo systemctl stop "$UNIT.timer"` и проверить inactive |
| TZ-07 | §5, строки 309–312 | `systemctl is-active xgw.service` возвращает 3, если служба не active; `client status` возвращает 2 при ошибке API; `sha256sum -c` — при расхождении. `set -e` обрывает до публикации, хотя строка 316 требует отчёт «при любом исходе» | собирать коды и продолжать: `… \|\| echo …`; публикацию не блокировать |
| TZ-08 | §4, строки 257–258 | `card()` не ловит `ValueError`/`OSError` от API. Кратковременный сбой панели во время fallback уронит весь Python-скрипт | `try/except` вокруг `card()`, продолжать до дедлайна |
| TZ-09 | §2, строка 110 | `sudo mktemp -d /var/lib/xgw/handoff/...` предполагает существующий каталог; проверить под sudo не удалось (`ls` — permission denied) | `sudo install -d -m 0755 /var/lib/xgw/handoff` перед `mktemp` |
| TZ-10 | §2, строка 150 | Текст требует пустого `blockers.selective` (строки 137–138), но assert проверяет только `fresh/policy_matched/off` | `assert not v["blockers"].get("selective")` |

## Не дефекты

- `xgw-zapret2.service` и `xgw-nfqws2.service` отсутствуют в `systemctl list-unit-files` при off — это нормально: воркер создаётся через `systemd-run` (`src/xgw/zapret2.py:463`). `systemctl show` отсутствующего юнита возвращает 0 (`ActiveState=inactive`, `MainPID=0`), поэтому §5 не падает на этом.
- `--seconds 2` в §1 и `--seconds 180` в §3 — в допустимом диапазоне 1…180.
- `route_evidence` в §4 вызывается через `sudo -n` с `PYTHONPATH` из `$TOOLS`; модуль в архиве есть.

## Минимальные правки до запуска

1. `VIDEO=8plwv25NYRo` перед §1 (или `: "${VIDEO:?}"`).
2. `rg -F` → `grep -F` в §1.
3. Обернуть `resolve`/`probe` §3 в `if … then … else … fi` и сохранить `direct-check.json`.
4. Добавить `|| echo EVIDENCE_PARTIAL` к `selective_media_evidence`.
5. В §5: `sudo systemctl stop "$UNIT.timer"`; проверить `! sudo systemctl is-active --quiet "$UNIT.timer"`.
6. В §5 не прерывать публикацию на `is-active`/`client status`/`sha256sum`; сохранить коды.
7. В §4 обернуть `card()` в `try/except`.
8. В §2: `sudo install -d -m 0755 /var/lib/xgw/handoff`.
9. В §2: `assert not v["blockers"].get("selective")`.

## Вердикт

По коду ТЗ корректно: команды, флаги, API и предпосылка об установленной базе
совпадают, тесты зелёные, `CODE` — предок TZ. Но **как есть на этой машине
оно не запускается**: нет sudo в сессии, нет `rg`, не задан `VIDEO`, и есть
три места, где `set -e` обрывает выполнение до публикации. Плюс не остановлен
таймер в §5 — это опаснее всего для рабочего шлюза. После правок 1–9 ТЗ можно
запускать из терминала с sudo; текущий агентский сеанс для этого не подходит.

## Состояние машины после аудита

- Изменений нет: `src/`, `packaging/`, `tests/` не менялись; установленный
  пакет не трогали.
- Машина: off/off, fresh/matched, воркеры inactive, панель слушает 8781/8782.
- Таймеры и временные юниты аудитом не создавались.
