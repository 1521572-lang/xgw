# T12 — сохранение настроек Selective и повтор TLS-пробы CDN

**Машина** — ThinkCentre, Ubuntu 24.04. Проверяемый код — `3d3e0f551a805c7f8ecfd63e276bdf19f1c005ef`.
[Предыдущий отчёт](../reports/2026-11-17_desync-t12-selective-recheck.md) подтвердил
успешную перепроверку с `/t/terms`, затем fallback при таймауте TLS до CDN и ещё один
такой отказ после замены CDN-адреса. Отдельно воспроизведена ошибка сохранения старого
списка доменов при выключенном режиме. Причина TLS-таймаутов пока неизвестна.

Flash выполняет только техническую приёмку: сама запускает команды, работает с
обычным Chrome и vision, восстанавливает шлюз и публикует отчёт. При отсутствии
доступа к терминалу, sudo или браузеру запроси доступ. Исходники, установщик и
тесты не меняй. Не запускай tcpdump и не собирай пакеты в этом раунде. Полные
подписанные URL, cookies, IP клиентов и необработанные снимки храни только локально.

## 1. Подготовка и установка с возвратом

Выполняй команды в одном терминале. Начинай с чистого checkout и рабочего шлюза
в `off/off`. Проверь, что панель отвечает и отдельный контрольный сайт открывается
через штатный VPN, запиши исходный VPN-выход локально. Открой отдельный Chrome с
выключенным QUIC, как в [T12, §2–3](T12-SELECTIVE-ROUTE-EVIDENCE.md). Если слои не
совпадают или VPN уже не работает, не устанавливай. Подготовь свежий CDN-адрес
из DevTools этого Chrome непосредственно перед сохранением пары URL.

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=3d3e0f551a805c7f8ecfd63e276bdf19f1c005ef
INFO=601238ef053447e1287be918864f8c839e1a3cf4
MGMT=f3de0052a4a41a549980a3264d8084887bf4c9b4
TLS=01379afe2445f49d8406295bfaeb03ed831470ec
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-selective-cdn-retry.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src:$D/source"
python3 -m pytest -q tests/test_zapret2.py tests/test_zapret2_panel.py \
  tests/test_zapret2_management.py tests/test_zapret2_management_linux.py \
  tests/test_desync_schema.py tests/test_desync_route_evidence.py
node --check src/xgw/ui/zapret2.js
bash -n docs/helpers/t11_management_restore.sh
systemctl show xgw.service xgw-xray.service -p ActiveState -p MainPID
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

Для `pytest` разрешён ранее настроенный dev-venv. При падении теста или работающем
воркере зафиксируй блокер и остановись до установки. Никаких правок в среде
в обход установщика. Таймер действует 90 минут. Оставь последние 10 на возврат.

```bash
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
PY=/usr/bin/python3
PAYLOAD="/opt/xgw/handoff/selective-cdn-retry-$CODE"
BACKUP="/var/lib/xgw/handoff/selective-cdn-retry-$CODE"
UNIT=xgw-selective-cdn-retry-rollback
OVERLAY=--selective-cdn-retry
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
INFO_FILES=(src/xgw/zapret2.py src/xgw/watch/zapret2_control.py \
  src/xgw/ui/zapret2.html src/xgw/ui/zapret2.js)
MGMT_FILES=(src/xgw/desync/schema.py src/xgw/watch/zapret2_management.py)
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$CODE" "${INFO_FILES[@]}" "${MGMT_FILES[@]}" \
  docs/helpers/desync_batch1_install.py docs/helpers/t11_management_restore.sh |
  sudo tar --no-same-owner -x -C "$PAYLOAD/code"
git archive "$INFO" "${INFO_FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$MGMT" "${MGMT_FILES[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$TLS" src/xgw/watch/checks.py | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
sudo chmod -R go-w -- "$PAYLOAD"
sudo cmp "$PAYLOAD/base/src/xgw/watch/checks.py" "$PACKAGE/watch/checks.py"
sudo "$PY" "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" \
  --package "$PACKAGE" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
printf '%s\n' "$BACKUP" "$HELPER" "$PANEL" "$UNIT" "$OVERLAY" >"$D/restore-location.txt"
sudo systemd-run --unit="$UNIT" --on-active=90m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback "$OVERLAY"
sudo systemctl is-active "$UNIT.timer"
sudo "$PY" "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl list-timers "$UNIT.timer" --no-pager
verify_manifest() {
  sudo "$PY" - "$BACKUP" "$1" <<'PY'
import hashlib, json, sys
from pathlib import Path

rows = json.loads((Path(sys.argv[1]) / 'manifest.json').read_text())
assert len(rows) == 6
for row in rows:
    path = Path(row['target'])
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == row[sys.argv[2] + '_sha'], path
    print(path.name, actual)
PY
}
verify_manifest new
```

Несовпадение `cmp` или prepare — `BLOCKED_BASE`, укажи файл и оставь рабочую
установку. Ошибка после начала apply — возврат в §4. После успешной установки
проверь панель и VPN до первой правки формы.

## 2. Форма в off и запуск кнопкой

1. Перезагрузи вкладку `/zapret2`. Через браузер и vision проверь форму на обычной
   ширине и 390 px. Кнопка «Заменить список на домены YouTube» появляется при включении
   HTTPS-опции. Убедись по Network, что кнопка меняет только черновик, без POST.
2. С включённой опцией оставь прежние 10 доменов или добавь `domain:example.org`
   к допустимому набору. Заполни оба адреса через подстановку `/t/terms` и свежий CDN.
   «Сохранить» должно дать `invalid` с подсказкой о доменах. В `/api/zapret2/overview`
   `config_key` не меняется, а `sudo sha256sum -c "$BACKUP/config-before.sha256"`
   проходит. Черновик остаётся открыт, выбранный режим остаётся off.
3. Нажми подстановку доменов. Сверь шесть строк в черновике с `youtube_domains` из API.
   Сохрани `multisplit`, интервал 120 с, HTTPS-опцию и ту же пару. Должны быть `saved`,
   новая ревизия, off/off, `youtube_probe_page_kind=terms`, `probe_count=2`,
   пустые `transport_probes`; воркер ещё не стартовал. Убедись, что в GET и ответах
   POST нет подписанной ссылки, а в форме она больше не отображается. Повторно открой
   настройки и убедись, что сохранены именно подставленные домены.
4. Проверь таймер, выполни `sudo touch "$BACKUP/network-test-started"`. Зафиксируй
   исходные маршруты и счётчики через [инструкцию T12, §3](T12-SELECTIVE-ROUTE-EVIDENCE.md#3-дельты-и-подтверждение-маршрута).
   Дождись закрытия формы и свежей карточки. Нажми «Домены через zapret2» и подтверди.
   В отчёте укажи, прошёл ли **реальный клик**, ответ POST и режим. Если кнопка
   заблокирована, сохрани `blockers.selective` и видимый текст, проверь после одного
   обновления. Не обходи дефект ручной подменой API или конфигов.

## 3. Измерение повторной пробы и маршрута

Проверь старт и минимум две перепроверки при той же ревизии. Отмечай UTC, `config_key`
(первые 8 знаков), `policy_matched`, `state`, `reason`, PID обоих воркеров, клиентское
правило и обе строки `evidence.transport_probes`. Сними JSON после каждой завершённой
пробы до очередной записи; при смене состояния сохрани прежнюю и новую записи. Нужны
`started_at`, `page_kind`, `phase`, `kind`, `http`, байты, `elapsed_ms` и наличие
`first_tls_timeout_ms`. Время CDN в `elapsed_ms` включает обе попытки, если был повтор.
Сверь с видимой строкой пробы CDN. Примени следующие критерии:

| Наблюдение | Что зафиксировать |
| --- | --- |
| Первая CDN-проба проходит | `first_tls_timeout_ms` отсутствует; активный режим. |
| TLS-таймаут, повтор проходит | `first_tls_timeout_ms` присутствует, `elapsed_ms` не меньше него, финальный `ok=true`, HTTP 200/204. Режим active при совпадающей ревизии. |
| TLS-таймаут, повтор отклонён сетью | Метка первого таймаута и результат второй попытки; `youtube_cdn_probe_failed`, закрытие прямого пути и новый клиентский сеанс через VPN. |
| Ошибка страницы, HTTP CDN или отмена | Автоповтора CDN после такой ошибки быть не должно. При `worker_down` укажи причину отдельно; не выводи его из смены PID после fallback. |
| TLS-таймаут не встретился | `RETRY_LIVE=NOT_OBSERVED`. Успех обычных проб не доказывает эффект повтора. |

Проверка повтора ограничена штатными условиями. Не изменяй nftables, DNS, sysctl,
профиль, таймауты и не убивай воркер для провокации отказа. Если CDN дал окончательный
отказ, допустим один новый сеанс после off со свежим CDN и той же страницей условий.
При другом отказе или повторном окончательном отказе заверши сетевую фазу.

Начни видео сразу после первого `active`. Сними хотя бы **одну короткую пару**
с устойчивым правилом Xray, новой передачей `googlevideo.com` по CDP и ростом
счётчика NFQUEUE до первой перепроверки. Для дельт, параллельного VPN-контроля и
720p применяй [T12, §3](T12-SELECTIVE-ROUTE-EVIDENCE.md#3-дельты-и-подтверждение-маршрута).
Затем попробуй ≥150 с 720p. Пары через смену конфигурации или эпохи не засчитывай.
Если две перепроверки прошли и до возврата ≥35 минут, проведи 15 минут просмотра,
перемотку на ≥6 минут и ещё 5 минут при 720p. Раздели непрерывное воспроизведение,
буфер и сетевую передачу. Сохрани показания CDP/плеера и проверь экран через vision.
При падении режима укажи, сколько было подтверждённого просмотра до fallback и
заработал ли новый сеанс через VPN. Стабильность и путь медиа оценивай отдельно.

## 4. Возврат и публикация

Выключи Selective кнопкой. Проверь актуальный off/off, неактивные воркеры, снятие
клиентского правила, новый сеанс через VPN и доступность панели. Если форма,
локальные проверки и возврат исправны, а сетевые результаты соответствуют таблице,
выбери `accept`; при регрессии выбери `rollback`. Два корректно зафиксированных
TLS-отказа подряд дают отрицательный результат по устойчивости, но сами по себе
не доказывают регрессию слоя. Отдельно отметь причину и решение об установке.

```bash
RESULT=accept  # замени на rollback при регрессии
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" "$RESULT" "$OVERLAY"
sudo sha256sum -c "$BACKUP/config-before.sha256"
if [[ "$RESULT" == accept ]]; then verify_manifest new; else verify_manifest old; fi
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
```

Проверь VPN, панель и off/off после возврата. Только затем останови таймер
`sudo systemctl stop "$UNIT.timer"`. Если он уже сработал, проверь манифест old
и отметку `restore-completed`, не выбирай accept задним числом. Закрой тестовый
Chrome. При потере терминала пути сохранены в `restore-location.txt`,
`PY=/usr/bin/python3`; при сбое возврата запроси доступ для диагностики.

Автоматически опубликуй **только обезличенный отчёт** даже при блокере, без запроса
подтверждения. Укажи SHA, PASS/FAIL/BLOCKED/NOT_RUN по шагам, исход клика и сохранения,
таблицу проб, `RETRY_LIVE` (`RECOVERED`, `FAILED`, `NOT_OBSERVED` или `NOT_RUN`),
`MEDIA_PATH`, время пригодного 720p, выводы по стабильности, конечное состояние,
манифест и решение о возврате. Публично никаких исходных адресов и логов.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "flash/t12-selective-cdn-retry-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t12-selective-cdn-retry.md"
# Заполни REPORT по фактам, включая блокеры.
git add "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: verify Selective CDN retry on ThinkCentre"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке выполни fetch/rebase и обычный push. Сообщи ссылку на отчёт и состояние машины.
