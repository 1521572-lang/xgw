# Единая приёмка бюджета, маршрутизации и воспроизведения

Редакция 19.11.2026. ThinkCentre, Ubuntu **24.04 LTS**, amd64.
Код **08d31ee93963bb00acb7a2275e7a554efcfb0f05**.
Установленная база **3630b44502b872ca3788e0824c6a9d0d8363b561**,
принятая [отчётом 19 ноября](../reports/2026-11-19_combined-open-blocks.md).
База 3d117b1 здесь больше не используется для установки.

Это одно действующее ТЗ вместо прежнего combined. Flash сама запускает команды,
работает с GUI/vision, восстанавливает шлюз и автоматически публикует один
обезличенный отчёт. При отсутствии терминала/sudo/GUI запрашивает доступ сама.
Код, тесты, критерии и помощники не изменяет. Опубликованные ниже команды,
включая готовый Python-блок проверки API, написаны Codex и исполняются без правок.

## Что принято и что остаётся

На предыдущем проходе пакета d818e80 прошли 242 основных, 10 API и 5 сетевых тестов. Установку остановило сравнение цепочек output у TUN и TPROXY. Тест теперь подставляет UID sing-box и проверяет оба правила TCP close на своих местах, сохраняя точное сравнение остальных правил. Повтори §2. После прохождения проверки продолжай с §3. [Отчёт о блокере](../reports/2026-11-19_admission-matrix.md)

Установка 8/8, контракт Flowseal, задания и их возврат приняты на 3630b44.
Standalone воспроизводил 720p и закрылся после SIGKILL без самовключения VPN.
В отчёте для «15+5» указаны 59/59 и 19/20 usable, но эти числа сами по себе
не подтверждают 900 и 300 секунд. Проверь исходные часы телеметрии новым
помощником; без них длинная фаза остаётся NOT_CONFIRMED.

A/B/B/A не выявил пользы удаления подписи при наблюдавшемся TLS-отказе.
**Матрицу нельзя откладывать до успеха базового профиля:** именно она проверяет,
поможет ли другой профиль при этом отказе. «Пригодная пара» означает корректные,
неистёкшие адреса/область/перехват, а не уже успешный HTTPS. Нельзя делать вывод
об остальных восьми профилях по отказу одного. Принятый код не обещает сетевой успех.

WAN IPv6 отсутствует: NOT_APPLICABLE_ON_THIS_HOST, не блокер. H07/H11/H12,
перенос кэша между IP и M3 не закрываются одним pass служебной пробы.

## 1. Завершить прежнее наблюдение и восстановить исходную политику

В предыдущих отчётах зафиксированы интервалы off и standalone. На момент
последнего отчёта наблюдение продолжалось около 18,2 ч.
Проверь завершение user-unit xgw-combined-monitor-1795041850 и состояние
xgw-combined-day-rollback.timer перед установкой. Пока монитор работает, можно
выполнить §2 в отдельном checkout. [Последний отчёт](../reports/2026-11-19_admission-matrix.md)

Начни от пользователя рабочего стола, в Bash:

```bash
set -euo pipefail
umask 077
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
test "$(dpkg --print-architecture)" = amd64
printf '%s\n' "$PRETTY_NAME"
uname -r
/usr/sbin/nft --version
REPO=$(git rev-parse --show-toplevel)
BR=integration/zapret2-batch1
CODE=08d31ee93963bb00acb7a2275e7a554efcfb0f05
OLD=3630b44502b872ca3788e0824c6a9d0d8363b561
GUI_BASE=7c20f59023ec39e5c5ce4606767ea915c3b91f64
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-admission.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
export PYTHONPATH="$D/source/src:$D/source"
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
TELEMETRY_PY=${XGW_TELEMETRY_PYTHON:-$TEST_PY}
PACKAGE=$(readlink -f /opt/xgw/lib/xgw)
CFG=$(readlink -f /etc/xgw/config.toml)
PANEL=$(readlink -f /etc/xgw/panel.json)
systemctl --user status xgw-combined-monitor-1795041850 --no-pager || true
sudo systemctl list-timers xgw-combined-day-rollback.timer
printf '%s\n' "$HOME"/xgw-combined.*/day.jsonl
```

PY/TEST_PY/TELEMETRY_PY — абсолютные пути существующих интерпретаторов; проверь
ExecStart. Не устанавливай зависимости в venv демона. Найди прежний day.jsonl
сама по ExecStart user-unit и приватному каталогу; присвой PREV_D его каталог.
Не проси владельца запускать скрипт или искать файл.

```bash
# PREV_D — установленный выше фактический каталог прежнего опыта.
test -f "$PREV_D/day.jsonl"
"$PY" -m xgw.desync.client analyze "$PREV_D/day.jsonl" >"$D/previous-day-summary.json"
```

Если elapsed <86400 и unit исправно работает, дождись конца, продолжая независимые
проверки. Файл не дописывать и не создавать второй off-монитор вместо первого.
Если прежний процесс остановился раньше, зафиксируй фактическую длительность и
NOT_COMPLETED; не выдавай её за сутки. При недоступности сохранённых данных
публикуй блокер этой фазы, не придумывай итог. Новый короткий прогон не заменяет сутки.

Проверь elapsed, policy_interval_seconds, gaps/api_errors и свежие VPN/обычный
сайт. В старом формате off/unknown означает, что подтверждён только режим Selected.
UTC_BOUNDARY_VIEW означает смену resets_at в API; UTC_LIVE_PROBES требует первого
настоящего списания/пробы нового дня. При off/off второе не наблюдалось.
M3_TRAFFIC=NOT_RUN при отсутствии трафика пула. Сними штатные pool stats и diag.

После завершения/фиксации прерывания старой фазы верни её исходные настройки
проверенным старым restore, затем погаси именно прежние предохранители:

```bash
PREV_BACKUP="/var/lib/xgw/handoff/combined-$OLD"
PREV_HELPER="/opt/xgw/handoff/combined-$OLD/code/docs/helpers/desync_batch1_install.py"
sudo /bin/bash "$PREV_BACKUP/restore.sh" "$PY" "$PREV_HELPER" "$PREV_BACKUP" \
  "$PANEL" accept --selective-jobs
sudo sha256sum -c "$PREV_BACKUP/config-before.sha256"
sudo systemctl stop xgw-combined-day-rollback.timer
sudo systemctl stop xgw-selective-jobs-rollback.timer
```

Проверь VPN и фактический код базы. Если старый таймер откатил слой, останови
установку и запиши SHA отличающихся файлов. Политика после восстановления может
быть standalone. Сохрани её в §3 до временного переключения в off/off.

## 2. Проверки кода на Ubuntu

Обязательные проверки охватывают бюджет, API, телеметрию, откат сетевых
правил, границы очереди Engine и завершение TCP. FAIL, ERROR или SKIP в
обязательном наборе блокирует установку.

```bash
"$TEST_PY" -m pytest -o addopts='' -q \
  tests/test_zapret2.py tests/test_zapret2_management.py tests/test_zapret2_panel.py \
  tests/test_desync_jobs.py tests/test_zapret2_management_linux.py \
  tests/test_youtube_telemetry.py tests/test_desync_schema.py tests/test_acceptance_gate.py \
  --junitxml="$D/core.xml" >"$D/core.log" 2>&1
"$TEST_PY" -m pytest -o addopts='' -q tests/test_panel.py -k zapret2 \
  --junitxml="$D/api.xml" >"$D/api.log" 2>&1
"$TEST_PY" -m pytest -o addopts='' -q \
  tests/test_nfqws2.py::EngineTests::test_accounting_controls_engine_rules_and_warnings \
  tests/test_nfqws2.py::EngineTests::test_accounting_loss_stops_worker_and_skips_engine_profiles \
  tests/test_nfqws2.py::EngineTests::test_nfqueue_is_bounded_fail_open_and_loop_free \
  tests/test_nft.py::test_tun_leaves_tproxy_for_lan_only_and_keeps_the_marking_chain \
  tests/test_nft.py::test_singbox_close_only_restores_header_only_ack_of_local_tun_flow \
  tests/test_nft.py::test_singbox_close_set_keeps_rule_integrity_while_connections_expire \
  --junitxml="$D/network-contracts.xml" >"$D/network-contracts.log" 2>&1
"$PY" - "$D/core.xml" "$D/api.xml" "$D/network-contracts.xml" <<'PY'
import sys
from pathlib import Path
from docs.helpers.acceptance_test_gate import read

for filename in sys.argv[1:]:
    result = read(Path(filename), Path.cwd())
    assert all(case["outcome"] == "passed" for case in result.values()), filename
    print(f"{Path(filename).name}: {len(result)} passed")
PY
bash -n docs/helpers/t11_management_restore.sh
```

Выдели исходы: остаток 0/256 КиБ/786431/786432, неизвестный бюджет, отказ API без
записи политики, отсутствие inbound/старта worker, остановка матрицы перед следующим
кандидатом при истощении, продолжение после timeout только с подтверждённым off.
Проверки воспроизведения должны отвергать 60 секунд с хорошим качеством как «15 минут»,
пустые сетевые байты, сломанные часы и отсутствие seek.

При отказах в расширенном наборе сравниваются общие тесты NEW и OLD. Четыре
новых теста уже обязательны в предыдущей команде, поэтому общая выборка их
исключает в обоих checkout.

```bash
BROAD=(tests/test_desync_worker.py tests/test_desync_standalone.py
       tests/test_desync_cache.py tests/test_desync_shadow.py tests/test_desync_event_socket.py
       tests/test_desync_tournament.py tests/test_desync_flowseal.py tests/test_desync_route_evidence.py
       tests/test_selective_probe_watch.py tests/test_nfqws2.py tests/test_nft.py
       tests/test_applier.py tests/test_generator.py tests/test_freepool.py
       tests/test_freepool_backend.py tests/test_freepool_stats.py tests/test_freepool_traffic.py)
ADDED=(
  --deselect=tests/test_nfqws2.py::EngineTests::test_accounting_controls_engine_rules_and_warnings
  --deselect=tests/test_nfqws2.py::EngineTests::test_accounting_loss_stops_worker_and_skips_engine_profiles
  --deselect=tests/test_nft.py::test_singbox_close_only_restores_header_only_ack_of_local_tun_flow
  --deselect=tests/test_nft.py::test_singbox_close_set_keeps_rule_integrity_while_connections_expire
)
run_broad() {
  local tree=$1 xml=$2 log=$3
  (
    cd "$tree" || exit 2
    env PYTHONPATH="$tree/src:$tree" "$TEST_PY" -m pytest -o addopts='' -q \
      "${BROAD[@]}" "${ADDED[@]}" --basetemp="$tree/.acceptance-pytest-tmp" --junitxml="$xml"
  ) >"$log" 2>&1
}
if run_broad "$D/source" "$D/new.xml" "$D/new.log"; then
  BROAD_RESULT=PASS
else
  NEW_RC=$?
  test "$NEW_RC" -eq 1
  git worktree add --detach "$D/baseline" "$OLD"
  if run_broad "$D/baseline" "$D/old.xml" "$D/old.log"; then OLD_RC=0; else OLD_RC=$?; fi
  test "$OLD_RC" -le 1
  "$PY" docs/helpers/acceptance_test_gate.py --current "$D/new.xml" --baseline "$D/old.xml" \
    --current-source "$D/source" --baseline-source "$D/baseline" >"$D/baseline-comparison.json"
  BROAD_RESULT=BASELINE_MATCH
fi
```

Совпавшие 14 прежних отказов не превращаются в PASS. Новый/изменившийся отказ,
различие состава или новая skipped-строка блокируют установку. Не расширяй
нормализацию и не исправляй тесты сама. Qt-база не меняется, прежние 11 PASS
сохраняются как предыдущий результат; живые UI проверяются ниже.

## 3. Обратимая установка 11 файлов

Пакет объединяет проверку бюджета, ограничение Engine по учёту conntrack,
правило TCP close для IPv4/TUN и анализ суточного журнала. Установщик перед
запуском демона обновляет сетевые правила через xgw-net.service. При ошибке
загрузки восстанавливает прежние файлы и правила. Начни после §1 с рабочим VPN.
Подтверди доступ к панели из пользовательской сессии. При необходимости сама
получи свежую ссылку командой `sudo xgw panel` в приватный файл и войди в браузере.

```bash
exec 9>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock"
flock -n 9
PAYLOAD="/opt/xgw/handoff/admission-$CODE"
BACKUP="/var/lib/xgw/handoff/admission-$CODE"
UNIT=xgw-combined-admission-rollback
OVERLAY=--combined-admission
HELPER="$PAYLOAD/code/docs/helpers/desync_batch1_install.py"
CORE=(src/xgw/zapret2.py src/xgw/watch/zapret2_control.py src/xgw/watch/panel.py
      src/xgw/watch/zapret2_management.py src/xgw/desync/jobs.py src/xgw/daemon.py
      src/xgw/desync/client.py src/xgw/generator/profiles.py src/xgw/net/nft.py
      src/xgw/net/sysctl.py src/xgw/nfqws2.py)
check_installed() {
  local tree=$1 file
  for file in "${CORE[@]}"; do
    sudo cmp "$tree/$file" "$PACKAGE/${file#src/xgw/}" || return
  done
}
sudo test ! -e "$PAYLOAD"
sudo test ! -e "$BACKUP"
sudo install -d -m 0755 "$PAYLOAD/code" "$PAYLOAD/base"
git archive "$OLD" "${CORE[@]}" | sudo tar --no-same-owner -x -C "$PAYLOAD/base"
git archive "$CODE" "${CORE[@]}" docs/helpers/desync_batch1_install.py \
  docs/helpers/t11_management_restore.sh | sudo tar --no-same-owner -x -C "$PAYLOAD/code"
sudo chmod -R go-w -- "$PAYLOAD"
sudo "$PY" "$HELPER" prepare "$OVERLAY" --payload "$PAYLOAD" --package "$PACKAGE" --backup "$BACKUP"
sudo cp --preserve=mode,ownership -- "$PANEL" "$BACKUP/panel.before"
sudo sha256sum "$CFG" "$PANEL" | sudo tee "$BACKUP/config-before.sha256" >/dev/null
sudo chmod 0600 "$BACKUP/config-before.sha256"
sudo install -m 0700 "$PAYLOAD/code/docs/helpers/t11_management_restore.sh" "$BACKUP/restore.sh"
sudo systemd-run --unit="$UNIT" --on-active=240m --timer-property=AccuracySec=1s \
  /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback "$OVERLAY"
sudo systemctl is-active "$UNIT.timer"
sudo touch "$BACKUP/network-test-started"
"$PY" - <<'PY'
import time
from xgw.desync.client import Client

client = Client()
def view():
    return client.request("/api/zapret2/overview")["zapret2"]

state = view()
assert state["engine_mode"] == "off", "engine must be off on the expected base"
if state["mode"] != "off":
    reply = client.request("/api/zapret2/mode", {
        "mode": "off", "expected": state["config_key"]})
    assert reply.get("ok") is True, reply.get("code")
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    state = view()
    if (state["mode"] == state["engine_mode"] == state["state"] == "off"
            and state["fresh"] and state["policy_matched"]):
        print("off/off confirmed")
        break
    time.sleep(2)
else:
    raise SystemExit("off/off not confirmed")
PY
sudo sha256sum "$CFG" "$PANEL" >"$D/off-before.sha256"
sudo flock "$BACKUP/restore.lock" "$PY" "$HELPER" apply "$OVERLAY" --backup "$BACKUP"
sudo sha256sum -c "$D/off-before.sha256"
check_installed "$PAYLOAD/code"
"$PY" -m xgw.desync.client status >"$D/initial.json"
```

После apply ожидается совпадение 11/11. При несовпадении baseline зафиксируй
отличающиеся пути. При любой ошибке после вооружения таймера выполни rollback
из §8. Сразу после apply проверь новый VPN-сеанс и правила следующей командой.
Результат сохраняет число правил, значения режима и состояние перехвата.

```bash
sudo "$PY" -IB - <<'PY' >"$D/network-after.json"
import json
import sys
sys.path.insert(0, "/opt/xgw/lib")
from xgw import config
from xgw.net import cmd, nft, sysctl
from xgw.net.capture import capture_for
from xgw.paths import Paths

paths = Paths.from_env()
cfg, _ = config.load(paths.config_file)
capture = capture_for(cfg, paths)
active = capture.loaded()
rules = capture.rules()
ruleset = json.loads(cmd.run(["/usr/sbin/nft", "-j", "list", "ruleset"]))
objects = ruleset["nftables"]
has_close = any(row.get("set", {}).get("name") == nft.SINGBOX_CLOSE_SET
                and row["set"].get("table") == nft.TABLE for row in objects)
has_engine = any(row.get("chain", {}).get("name") == "nfq_output"
                 and row["chain"].get("table") == nft.GUARD_TABLE for row in objects)
expected_close = rules.capture_local and rules.tun and rules.singbox_uid is not None
print(json.dumps({"capture": capture.mode(), "loaded": active, "setup_tcp_close": has_close,
                  "expected_tcp_close": expected_close, "engine_queue": has_engine,
                  "acct": sysctl.read(sysctl.CONNTRACK_ACCT)}))
assert capture.mode() == "on" and active is True
assert cfg.zapret2.mode == cfg.zapret2.engine == "off"
assert has_close == expected_close and not has_engine
PY
cat "$D/network-after.json"
```

Проверь свежие состояния обоих воркеров в systemd и отсутствие слушателя их
очереди по §3 предыдущего ТЗ. Если на рабочем хосте используется TPROXY, результат
по ветке IPv4/TUN берётся из проведённого лабораторного A/B. Приёмка не требует
смены способа перехвата или включения nf_conntrack_acct.

## 4. Бюджет перед запуском — главный дефект

В off/off настрой multisplit, шесть доменов YouTube, HTTPS-gate, страницу
https://www.youtube.com/t/terms и корректный CDN-адрес, check=180/retry=120,
временный лимит 512 МиБ. Пригодность адреса — формат/срок, не успешный TLS.

1. При достаточном бюджете одна обычная попытка должна дойти до проб. Сохрани
   исходный бюджет, результат и spent delta. Сетевой TLS-отказ допустим.
2. Верни off. Установи целый лимит МиБ так, чтобы остаток стал меньше 786432.
   Если новый день ещё пустой, одной нормальной попытки из п.1 достаточно, чтобы
   появился расход. БД/часами/счётчиками не манипулировать.
3. Сверь обе API и обе UI: одинаковый remaining, видимый бюджетный блокер,
   кнопка Selective недоступна. Standalone/off не заблокированы бюджетом.
4. Прямой POST ниже также должен отказать без сохранения mode и без подъёма
   worker. Перед блоком подтвердить остальные условия готовности. Если он всё же
   принял mode, команда сразу пытается выключить его и возвращает ошибку; далее §8.

```bash
"$PY" -c '
import json
from xgw.desync.client import Client
c = Client()
v = c.request("/api/zapret2/overview")["zapret2"]
r = c.request("/api/zapret2/mode", {"mode": "selective", "expected": v["config_key"]})
print(json.dumps(r, ensure_ascii=False))
if r.get("ok"):
    c.request("/api/zapret2/mode", {"mode": "off", "expected": r["config_key"]})
    raise SystemExit(2)
assert r.get("code") == "probe_budget"
'
"$PY" -m xgw.desync.client start --candidates multisplit --rounds 1 --seconds 180 \
  >"$D/low-budget-job.json" || test "$?" -eq 2
```

5. Для обоих вызовов сверить policy_key/mode, spent, MainPID и InvocationID,
   отсутствие нового probe-inbound/client-rule. Опрос 60 с, без pcap. Во втором
   вызове должен быть именно отказ, а не принятый queued. Сохрани его JSON.
6. Верни 512 МиБ без сброса spent. Веб и desktop обновляются; нормальная попытка
   снова разрешена. Неизвестный/повреждённый бюджет, точная граница и истощение
   посреди матрицы проверяются обязательными тестами без повреждения рабочей БД.

## 5. Полная матрица именно при отказе базового профиля

Из off/off запусти **9 профилей × 2 круга**, даже если multisplit или
hostfakesplit_md5 уже дали CDN TLS timeout. Не повторяй прежний A/B/B/A:
его отрицательный результат известен. Выбери корректный неистёкший signed URL
или рабочий по формату /generate_204; плохой HTTP у последнего — причина
вернуть свежий signed URL, а TLS timeout не запрещает перебор стратегий.

```bash
"$PY" -m xgw.desync.client start --seconds 3600
"$PY" -m xgw.desync.client monitor --output "$D/matrix.jsonl" --seconds 3600 --interval 15
"$PY" -m xgw.desync.client status >"$D/matrix-result.json"
```

При раннем завершении job монитор можно прервать Ctrl+C. Ожидается 18 строк,
второй круг в обратном порядке, complete/restore=pass. В строках есть профиль,
elapsed_ms, transport, причина и отдельные phase/kind/http/bytes/time страницы/CDN.
URL/IP остаются приватными. HTTP-успех не является успехом видео.

Timeout одного кандидата теперь даёт строку timeout/trial_timeout, затем
подтверждённый off и следующий профиль. Ошибка off, конфликт, отмена или нехватка
бюджета завершают весь job с возвратом. Не форсируй продолжение в этих случаях.
Сетевые отрицательные строки не дают основания пропустить остальные профили.

Сними 180-секундный ограниченный selective_probe_watch с --media-pairs --socket-stats
в одном неудачном и, если он появится, успешном окне. Не запускай бессрочный захват.
При смене IP/ревизии сравнение качества между такими окнами INCONCLUSIVE.

Нет кандидата с двумя HTTPS pass — pin/reset и Selective media = NOT_RUN,
но матрица всё равно имеет полноценный отрицательный результат на этой линии.
Есть два pass — проверь pin/reset в двух UI, затем включи этот профиль штатной
кнопкой и выполни §6 с параллельным обычным сайтом через VPN. Самим выставлять
active, открывать gate или менять маршруты запрещено.

Один короткий cancel и один restart во время задания — достаточная регрессия
уже принятых JOB01/03. После каждого restore=pass, off/off, новый VPN работает.

## 6. Измеренное видео и различие клиента/служебной пробы

Сначала проверь старые samples.jsonl, если они сохранились. Для длинного PASS
обязательны 900/300 пригодных секунд, clocks и свежие media bytes. Если старые
данные несовместимы/отсутствуют, запиши NOT_CONFIRMED и выполни готовый сборщик.
Не пиши конвертер и не подменяй telemetry по скриншотам или числу кадров.

VIDEO сама выбери из доступного публичного ролика >30 мин с 720p; присвой ID
из 11 символов. Для контроля используй принятый Standalone multisplit, затем
Selective только при штатном active. Одно правило/поколение, обычный Chrome TCP,
качество 720p, вкладка видима, без ручных пауз.

```bash
test "${#VIDEO}" -eq 11
"$TELEMETRY_PY" docs/helpers/youtube_telemetry.py --video "$VIDEO" --label long-watch \
  --out "$D/watch" --seconds 1020 --height 720 --channel chrome --disable-quic \
  >"$D/watch.log" 2>&1 &
PLAYER_PID=$!
```

Через vision сама обслужи consent/play и проверь качество. После завершения:

```bash
wait "$PLAYER_PID"
"$PY" docs/helpers/acceptance_playback_check.py --capture "$D/watch/samples.jsonl" \
  --video "$VIDEO" --minimum-seconds 900 >"$D/watch-verdict.json"
"$TELEMETRY_PY" docs/helpers/youtube_telemetry.py --video "$VIDEO" --label after-seek \
  --out "$D/seek" --seconds 420 --height 720 --channel chrome --disable-quic \
  >"$D/seek.log" 2>&1 &
PLAYER_PID=$!
```

В новом тестовом сеансе сама перемотай >400 с за пределы буфера. Не меняй режим
или профиль. После завершения:

```bash
wait "$PLAYER_PID"
"$PY" docs/helpers/acceptance_playback_check.py --capture "$D/seek/samples.jsonl" \
  --video "$VIDEO" --minimum-seconds 300 --require-seek >"$D/seek-verdict.json"
```

Помощник не засчитывает число samples вместо длительности: elapsed/wall,
eligible≥900/300, прогресс≥98%, 720p≥95%, gaps≤5 с, свежие media≥1 МиБ и
событие seek для второй фазы. Его route_verdict=UNKNOWN намеренно: маршрут
доказывается отдельно. FAIL помощника не скрывать; сначала прочитай причину/метрики.

В Selective параллельно обычный сайт обязан идти через исходный VPN. Для
MEDIA_PATH=CONFIRMED нужны accepted Xray/NFQUEUE-пары, байты плеера, marked socket
к тому же IP, прирост downlink/очереди сверх фона и неизменные rule/worker/config.
Используй [готовые collect/snapshot/delta команды](T12-SELECTIVE-MEDIA-PAIRS.md#1-подготовка-и-возврат),
только их измерительную часть, без старого установщика/таймера. При пробеле PARTIAL.
Standalone не подтверждает Selective. Если Chrome работает, а служебная TLS-проба
нет, запиши различие клиента/пути как гипотезу; не объявляй CDN недоступным всем.

При успешном Selective — один SIGKILL выбранного worker, снятие правила и **новый**
VPN-сеанс с CDN-байтами. Если active не получен, этот сценарий NOT_RUN.
Дополнительно UI04 повтори в свежей авторизованной вкладке; не ставь PASS по старому
отчёту. UI05 — короткая сортировка, UI06 — один переход на уже проверенный рабочий
VPN-сервер подписки с возвратом, пока таймер вооружён. Нет второго рабочего сервера —
BLOCKED_DEPENDENCY, а не PASS карты. Политику владельца восстанавливает §8.

## 7. Суточный Selective — только если он действительно заработал

Прежние сутки off/off не повторять. Их результат оформляется из §1.
Новые сутки Selective включай в этот же проход только если §6 подтвердил его
видео/обычный VPN/возврат. Сначала off/off и рабочий VPN, затем вооружи новый
предохранитель, после этого включи принятый профиль штатной кнопкой. Лимит
512 МиБ, check=180, retry=300, расход дня не сбрасывается.

```bash
sudo systemd-run --unit=xgw-admission-day-rollback --on-active=26h \
  --timer-property=AccuracySec=1s /bin/bash "$BACKUP/restore.sh" \
  "$PY" "$HELPER" "$BACKUP" "$PANEL" rollback "$OVERLAY"
sudo systemctl is-active xgw-admission-day-rollback.timer
sudo systemctl stop "$UNIT.timer"
DAY_UNIT="xgw-admission-monitor-$(date +%s)"
systemd-run --user --unit="$DAY_UNIT" --collect --property=RuntimeMaxSec=25h \
  --property=UMask=0077 /usr/bin/env PYTHONPATH="$PYTHONPATH" "$PY" \
  -m xgw.desync.client monitor --output "$D/selective-day.jsonl" --seconds 86400 --interval 60
```

После суток запусти client analyze для selective-day.jsonl, проверь реальные
интервалы active, свежие короткие видео в начале/после UTC и обычный VPN. Сборщик
сам не делает сетевые пробы. При fallback запиши причину и исход нового сеанса.
По завершении выполни §8 и публикуй один общий отчёт.

Если Selective не прошёл, DAY_SELECTIVE=NOT_RUN и новые сутки не назначать.
Пул для всего дома специально не включать. При отсутствии реальных разных IP
перенос H02 остаётся INCONCLUSIVE; H07/QUIC/obfs не включать по догадке.

## 8. Возврат и одна автоматическая публикация

При регрессии — rollback; при принятом коде — accept с восстановлением исходных
конфигов. Сначала cancel активного задания и off/off. При недоступном API сразу
вызови независимый restore. Таймер держать до проверки сети и хэшей.

```bash
RESULT_MODE=${RESULT_MODE:-rollback}
sudo /bin/bash "$BACKUP/restore.sh" "$PY" "$HELPER" "$BACKUP" "$PANEL" \
  "$RESULT_MODE" "$OVERLAY"
sudo sha256sum -c "$BACKUP/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
if sudo test -r /proc/net/netfilter/nfnetlink_queue; then
  sudo cat /proc/net/netfilter/nfnetlink_queue >"$D/queues-after-restore.txt"
fi
sudo test -f "$BACKUP/restore-completed"
if [ "$RESULT_MODE" = accept ]; then
  check_installed "$PAYLOAD/code"
else
  check_installed "$PAYLOAD/base"
fi
```

Перед штатным возвратом принятого пакета выставь RESULT_MODE=accept. Значение
по умолчанию rollback подходит для остановки после ошибки.
После возврата проверь новый VPN-сеанс, обычный сайт, хэши конфигов и фактический
режим. При исходном standalone ожидается разрешённый воркер этого режима, а при
исходном off/off оба воркера должны быть неактивны. При rollback дополнительно
сверь все файлы со слоем OLD и состояние перехвата.
Расход дня не сбрасывать. Закрой только тестовые браузеры/точно известные user-unit.
При ошибке restore останови опыты и запроси доступ; всё равно публикуй отчёт.

После подтверждения возврата погаси таймеры этого прогона:

```bash
sudo systemctl stop "$UNIT.timer"
sudo systemctl stop xgw-admission-day-rollback.timer 2>/dev/null || true
```

Файл docs/reports/YYYY-MM-DD_admission-matrix.md. В нём отдельно:
- предыдущие сутки: действительная длительность/UTC view vs live probes/VPN/M3;
- CODE/OLD/Ubuntu, CORE/API/BROAD и оставшиеся baseline-failures, INSTALL 11/11, рабочие правила и очередь;
- LOW_BUDGET: два API/два UI, отказ прямого POST и job, неизменные policy/spent/PID;
- все 18 строк матрицы, не только удачные; pin/reset/cancel/restart;
- long/seek: required/measured/wall/eligible/progress/720p/media bytes/seek, исход
  нового помощника; route отдельно; старый «15+5» подтвердился или нет;
- Selective+ordinary VPN, fresh fallback, GUI/session/map, итоговые файлы/режимы,
  хэши, PID, диск, таймеры и свежая VPN-передача.

Контроль TCP close и читаемость nftables уже приняты на 7ace100 в лаборатории
ThinkCentre. В этом проходе проверь установку, рабочий перехват и новую
передачу через VPN. [Отчёт A/B](../reports/2026-11-19T160130Z_tcp-close-ab-r2.md)

Flash публикует один обезличенный Markdown-отчёт в день проверки, в том числе
при блокере. Для публикации создай отдельный checkout от головы ветки.

```bash
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$D/publish" FETCH_HEAD
cd "$D/publish"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_admission-matrix.md"
```

Запиши результаты в `$REPORT` и выполни публикацию.

```bash
test -s "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: report ThinkCentre routing and admission acceptance"
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
SHA=$(git rev-parse HEAD)
git fetch origin "$BR"
git merge-base --is-ancestor "$SHA" FETCH_HEAD
printf 'https://github.com/1521572-lang/xgw/blob/%s/%s\n' "$SHA" "$REPORT"
```

