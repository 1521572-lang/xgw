# ThinkCentre · повторная проверка TCP close на Ubuntu 24.04 LTS

В первом проходе A/B обе серии OLD воспроизвели 12/12 LAST_ACK. Обе NEW остановились на чтении цепочки через штатный nftables 1.0.9, до замера TCP с новыми правилами. В повторном проходе счётчики читаются из таблицы прибора. Совместимость текстового и JSON-вывода проверяется отдельно после замеров TCP. Для сравнения сохранились те же базовые правила OLD, число соединений и порядок OLD/NEW/NEW/OLD. [Отчёт первого прохода](../reports/2026-11-19T191500Z_tcp-close-ab.md)

Целевая машина ThinkCentre работает под Ubuntu 24.04 LTS amd64. В предыдущем проходе были Ubuntu 24.04.5 и пакет nftables 1.0.9. Используй штатный `/usr/sbin/nft` и запиши версию. Flash самостоятельно выполняет команды в Bash. При отсутствии терминала, sudo или доступа к журналу Flash запрашивает доступ. Ориентир 15–30 минут. Этот проход использует изолированные пространства имён и может идти во время [основной приёмки](COMBINED-ADMISSION-2026-11-19.md). При блокере одной фазы выполни доступные независимые проверки и опубликуй общий отчёт.

## 1. Подготовить исходники

```bash
set -euo pipefail
umask 077
. /etc/os-release
test "$ID/$VERSION_ID/$(dpkg --print-architecture)" = ubuntu/24.04/amd64
printf '%s\n' "$PRETTY_NAME"
uname -r
/usr/sbin/nft --version
BR=integration/zapret2-batch1
OLD=df937840ad59e55a7e72e519cbd83fdd3c9c3568
CODE=7ace100a6a900eadffb33d295f78e7036cbd3d0c
REPO=$(git rev-parse --show-toplevel)
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
git -C "$REPO" merge-base --is-ancestor "$OLD" "$CODE"
D=$(mktemp -d "$HOME/xgw-close-ab.XXXXXXXX")
git -C "$REPO" worktree add --detach "$D/source" "$CODE"
cd "$D/source"
PY=/usr/bin/python3
TPY=${XGW_TEST_PYTHON:-$PY}
DAY_UNIT=xgw-combined-monitor-1795041850
systemctl --user show "$DAY_UNIT" -p ActiveState -p MainPID >"$D/monitor.before" || true
systemctl list-timers --all --no-pager 'xgw-*rollback*' >"$D/timers.before"
```

## 2. Контракты и журнал

Проверки выполнять от обычного пользователя с существующим тестовым Python. Для pytest выстави TPY из ранее принятого окружения, если системный Python не содержит pytest. Параметризованные проверки охватывают TPROXY и IPv6 на уровне построения правил. WAN IPv6 на этой машине отсутствует.

```bash
rc=0
PYTHONPATH="$D/source/src:$D/source" "$TPY" -m pytest -q -o addopts='' \
  tests/test_nft.py::test_singbox_close_only_restores_header_only_ack_of_local_tun_flow \
  tests/test_nft.py::test_singbox_close_set_keeps_rule_integrity_while_connections_expire \
  tests/test_nft.py::test_dedicated_singbox_uid_has_bypass_and_loopback_refusal \
  tests/test_nft.py::test_guard_never_approves_flows_and_only_scopes_managed_ingress \
  tests/test_nft.py::test_host_guard_uses_actual_egress_after_reroute_without_proxy_mark_permission \
  tests/test_nft.py::test_capture_approves_only_explicit_direct_paths \
  tests/test_desync_jobs.py::test_monitor_whitelist_excludes_private_payload \
  tests/test_desync_jobs.py::test_monitor_analysis_preserves_gaps_and_does_not_claim_playback \
  tests/test_desync_jobs.py::test_monitor_separates_policy_from_state_and_reads_legacy_journals \
  --junitxml="$D/contracts.xml" >"$D/contracts.log" 2>&1 || rc=$?
printf 'pytest=%s\n' "$rc"
tail -n 3 "$D/contracts.log"
```

Определи конкретный журнал прежнего монитора по его аргументу --output. Если unit уже собран systemd, используй путь из материалов его запуска. При неоднозначности не выбирай файл по одному лишь времени изменения. Следующий блок ищет путь работающего процесса и принимает точный ранее установленный путь через переменную DAY_LOG. Команда анализирует приватную копию. При гонке чтения повтори копирование один раз. Смена режима и пробелы остаются в данных.

```bash
pid=$(systemctl --user show "$DAY_UNIT" -p MainPID --value 2>/dev/null || true)
if [[ -z ${DAY_LOG:-} && "$pid" =~ ^[1-9][0-9]*$ && -r /proc/$pid/cmdline ]]; then
  DAY_LOG=$("$PY" - "$pid" <<'PY'
import os, pathlib, sys
args = pathlib.Path("/proc", sys.argv[1], "cmdline").read_bytes().split(b"\0")
if b"xgw.desync.client" in args and b"monitor" in args and b"--output" in args:
    print(os.fsdecode(args[args.index(b"--output") + 1]))
PY
)
fi
if [[ -n ${DAY_LOG:-} && -r "$DAY_LOG" ]]; then
  for attempt in 1 2; do
    cp -- "$DAY_LOG" "$D/day-snapshot.jsonl"
    if PYTHONPATH="$D/source/src" "$PY" -m xgw.desync.client analyze \
         "$D/day-snapshot.jsonl" >"$D/day-summary.json"; then
      cat "$D/day-summary.json"
      break
    fi
    echo "snapshot_attempt=$attempt incomplete_or_invalid"
  done
else
  echo DAY_LOG_UNAVAILABLE
fi
```

Запиши elapsed_seconds, policy_interval_seconds, confirmed_interval_seconds, пробелы, ошибки API, смену границы UTC и активность unit. Состояние карточки и пара настроек имеют разные поля. В старых строках отсутствует engine_mode, поэтому off/unknown подтверждает только настройку Selected. Время между разными ревизиями или недостоверными снимками остаётся unconfirmed. Монитор в работе до 86400 секунд даёт RUNNING/PARTIAL. Завершённый раньше срока монитор даёт NOT_COMPLETED. Строгое подтверждение off/off требует сведений об обоих режимах; сведения о владельце очереди берутся из отдельного наблюдения. Пробы видео и нагрузки этот файл не содержит.

## 3. Выполнить две пары на том же ядре

Правило действует при локальном IPv4-перехвате в TUN. FIN от UID sing-box добавляет в типизированный набор два адреса и два порта, а в conntrack установленного соединения — бит `0x04000000`. Предел составляет 4096 записей, срок каждой записи 2 минуты. Для прямой отправки позднего ACK нужны и запись, и бит данного соединения. Цепочка сравнивает обычную длину IPv4 и длину TCP-заголовка с общей длиной пакета. Сравнения охватывают все длины заголовка TCP от 20 до 60 байт. Передача данных и IP-фрагменты остаются в обычной обработке. [Семантика динамических наборов nftables](https://netfilter.org/projects/nftables/manpage.html)

Все четыре запуска используют одинаковый прибор из CODE. Источник правил в подкаталоге old — OLD, в new — CODE. Исходники извлекаются от root из точных Git-объектов в приватный каталог /run. В каждом запуске прибор создаёт заново сеть с veth, тестовый TUN-маршрут, локального TCP-получателя и свой набор nft. Экземпляр установленного /opt/xgw/sing-box/sing-box получает синтетический HTTP CONNECT, работает под UID 65534 без capabilities и обращается по IPv4 только к тестовому получателю. Конфиг содержит один локальный вход и один direct outbound. Дамп трафика не создаётся.

```bash
sudo -v
R=$(sudo mktemp -d /run/xgw-close-ab.XXXXXXXX)
for side in old new; do
  rev=$CODE
  if [[ "$side" == old ]]; then rev=$OLD; fi
  sudo install -d -m 0700 "$R/$side"
  git archive "$rev" src/xgw | sudo tar --no-same-owner -xf - -C "$R/$side"
  git show "$CODE:docs/helpers/audit_kernel_lab.py" | sudo tee "$R/$side/lab.py" >/dev/null
  sudo chmod 0500 "$R/$side/lab.py"
  git show "$CODE:docs/helpers/audit_kernel_lab.py" | sudo cmp - "$R/$side/lab.py"
done
before_after() {
  sudo sha256sum /etc/xgw/config.toml /etc/xgw/panel.json /opt/xgw/lib/xgw/net/nft.py
  sysctl -n net.netfilter.nf_conntrack_acct
}
before_after >"$D/host.before"
if sudo test -x /opt/xgw/sing-box/sing-box; then
  /opt/xgw/sing-box/sing-box version | head -n 1 || true
fi
NET_INODE=$(stat -Lc '%i' /proc/self/ns/net)
n=0
for side in old new new old; do
  n=$((n+1))
  log="$D/$n-$side"
  rc=0
  sudo env PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    timeout -k 5s 150s unshare --net --mount --pid --fork --kill-child=KILL --mount-proc \
    "$PY" -IB "$R/$side/lab.py" close-ab "$NET_INODE" \
    >"$log.jsonl" 2>"$log.err" || rc=$?
  printf 'run=%s side=%s probe_rc=%s\n' "$n" "$side" "$rc"
  score_rc=0
  "$PY" -IB docs/helpers/audit_kernel_lab.py "assess-$side" "$log.jsonl" \
    >"$log.score" 2>"$log.score.err" || score_rc=$?
  printf 'assess=%d\n' "$score_rc"
  cat "$log.score"
done
before_after >"$D/host.after"
cmp "$D/host.before" "$D/host.after" || echo HOST_CHANGED
systemctl --user show "$DAY_UNIT" -p ActiveState -p MainPID >"$D/monitor.after" || true
systemctl list-timers --all --no-pager 'xgw-*rollback*' >"$D/timers.after"
```

Если изоляция или TUN запрещены, запроси доступ. Рабочий namespace для этих команд использовать нельзя. В отчёте укажи точную фазу и ошибку. Сбой запуска sing-box имеет собственный результат BLOCKED. Он не отменяет валидные наблюдения для синтетического сокета. При probe_rc≠0 просмотри приватный stderr, сохрани полученные строки и укажи незавершённые фазы. Оставшиеся независимые серии выполняются по плану.

| Проверка | Что перенести из результатов каждой серии |
|---|---|
| Совместимость вывода | Отдельно укажи `synthetic_pass` и `listing_pass`. Для второго требуются все пять результатов чтения `ok`, `manifest_ok=true` и `stable=true`. Сравниваются текстовые снимки без элементов и полный снимок с временными записями. Проверка JSON включает цепочку output и весь ruleset, которым пользуется диагностика. Если чтение падает, перенеси код завершения соответствующей команды и сохрани уже измеренный результат TCP. |
| Контроль без правил | 12/12 эхо, FIN и закрытий за 800 мс. Для защищённого другого UID до и после опыта требуются echo_rc=1 и ноль пакетов в protected_wan_packets. Проверить доставку обоих разрешённых вариантов Engine и контроли Selected. Доставка стороннего UID на WAN блокирует приёмку. |
| Синтетический UID | Обе OLD воспроизводят 12 LAST_ACK. На обеих NEW — 12/12 TCP_CLOSE, 0 LAST_ACK и 0 ошибок, заполненный marked_bypass_ack. Привести actual client_ok, echo, FIN, final_ack, last_ack_at_deadline, marked_proxy, marked_bypass_ack, after_guard_wan, after_guard_tun. При расхождении здоровых серий — MIXED. Потеря здорового контроля даёт INCONCLUSIVE. |
| Установленный бинарник | Для close_singbox показать те же числа и installed_binary отдельно по 4 строкам. LAST_ACK на обеих OLD и CLOSED на обеих NEW подтверждают эффект для этого бинарника в лаборатории. CLOSED во всех четырёх означает отсутствие воспроизведения у бинарника в данном сценарии. MIXED_OR_FAILED и BLOCKED сохраняют свою причину. Этот сценарий не определяет поведение активных домашних соединений. |
| Рабочий хост | Сравнить хэши и sysctl до/после и наличие исходного таймера и монитора. Естественное завершение таймера или монитора фиксировать по времени. В подходящем штатном окне проверить off/off по командам ниже. При standalone записать NOT_OBSERVED. |

Сними текущее состояние один раз. Если это штатное окно off/off, сними ещё два наблюдения. В отчёт перенеси только совпадение политики, свежесть, состояния служб, наличие резервации, owner_verified, размер допуска и изменение счётчиков. Для OFF_CONSISTENT требуются стабильная ревизия, свежее подтверждение с обеих сторон, отсутствие работающих воркеров и закрытый допуск. При расхождении укажи, какое свидетельство изменилось или отсутствует.

```bash
git show "$CODE:docs/helpers/audit_host_observe.py" | sudo tee "$R/observe.py" >/dev/null
sudo chmod 0500 "$R/observe.py"
git show "$CODE:docs/helpers/audit_host_observe.py" | sudo cmp - "$R/observe.py"
snapshot() { sudo timeout 30s "$PY" -IB "$R/observe.py" desync; }
if snapshot >"$D/off-1.json" 2>"$D/off-1.err"; then
  if "$PY" -c 'import json,sys; x=json.load(open(sys.argv[1])); sys.exit((x["mode"],x["engine"]) != ("off","off"))' "$D/off-1.json"; then
    for n in 2 3; do
      sleep 20
      snapshot >"$D/off-$n.json" 2>"$D/off-$n.err" || echo OFF_SAMPLE_UNAVAILABLE
    done
  else
    echo OFF_NOT_OBSERVED
  fi
else
  echo OFF_SAMPLE_UNAVAILABLE
fi
```

## 4. Автоматически опубликовать один отчёт

Flash сама оформляет Markdown: версия установленной базы, табличные результаты OLD/NEW/NEW/OLD, отдельные выводы по синтетическому TCP и реальному бинарнику, статус суточного наблюдения и основной приёмки. Полные конфиги, исходный day.jsonl, адреса подписки, cookie, PID, ключи политики и идентификаторы устройств остаются на машине. Временный корневой каталог принадлежит этому проходу и исчезнет при перезагрузке. После окончания собственной серии его можно убрать по проверенному пути из R. Опубликуй даже частичный отчёт при блокере.

```bash
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$D/publish" FETCH_HEAD
cd "$D/publish"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_tcp-close-ab-r2.md"
```

Запиши отчёт в "$REPORT" и запусти сама:

```bash
test -s "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: report ThinkCentre TCP close comparison and observed gateway modes"
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
