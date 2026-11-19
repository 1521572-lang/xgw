# Внеочередная проверка спорных выводов аудита XGW

**Исполнитель — Flash на ThinkCentre с Ubuntu 24.04 LTS amd64. Начать при получении задания.** Ориентир 10–20 минут. Тихий интервал суточного наблюдения подходит. На рабочем шлюзе нужны чтение и локальные вычисления; режим, воркеры, таймеры, внешний трафик и установленные файлы приложения для этой проверки не менять. Ядро работает с временной парой veth в двух анонимных сетевых пространствах. Сбор пакетов на диске не требуется.

Основания — [инженерный разбор](AUDIT-XGW-2026-11-19.md) и [последний отчёт Ubuntu](../reports/2026-11-19_combined-open-blocks.md). Отдельная [основная приёмка](COMBINED-ADMISSION-2026-11-19.md) сохраняет собственные CODE, таймеры, установку, 18 кандидатов, видео и публикацию. Это ТЗ можно завершить и опубликовать до окончания суток. При текущей смене пакета или рестарте из основной приёмки дождись стабильной фазы для замера до/после. Отложи CPU-нагрузку до конца измерения видео, если оно уже началось.

Flash сама запрашивает доступ к терминалу/sudo при необходимости, выполняет команды в Bash и пишет только свой отчёт. Код написан Codex. Ошибка в помощнике, неполный контроль или отсутствующее право фиксируются с именем фазы и краткой причиной. Независимые фазы продолжить. Не придумывать замену теста, не исправлять код на машине. У этого задания нет шага установки новой версии XGW.

## 1. Окружение, проверенная копия приборов и исходная точка

Начни из любого checkout репозитория XGW под пользователем рабочего стола. Все следующие блоки в одном Bash. Для ошибок предусмотри запись статуса и продолжение независимых пунктов. Остановка на ошибке обязательна при подготовке доверенных файлов или изоляции.

```bash
set -euo pipefail
umask 077
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
test "$(dpkg --print-architecture)" = amd64
printf '%s\n' "$PRETTY_NAME"
uname -r
REPO=$(git rev-parse --show-toplevel)
BR=integration/zapret2-batch1
TOOLS=754d2e48ca90fc4bcab24277c7992d8afdf7f0a7
OLD=3630b44502b872ca3788e0824c6a9d0d8363b561
NEW=46c69fde43ff64f9952bf628b404ba8720fa62e7
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$TOOLS" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-audit.XXXXXXXX")
git -C "$REPO" worktree add --detach "$D/source" "$TOOLS"
cd "$D/source"
PY=/usr/bin/python3
TPY=${XGW_TEST_PYTHON:-$PY}
PKG=$(readlink -f /opt/xgw/lib/xgw)
sudo -v
ROOTDIR=$(sudo mktemp -d /run/xgw-audit.XXXXXXXX)
for h in audit_host_observe.py audit_kernel_lab.py; do
  sudo install -m 0500 -o root -g root "docs/helpers/$h" "$ROOTDIR/$h"
  git show "$TOOLS:docs/helpers/$h" | sudo cmp - "$ROOTDIR/$h"
done

snapshot() {
  sudo "$PY" -IB "$ROOTDIR/audit_host_observe.py" snapshot
}
config_sums() {
  sudo sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
timers() {
  systemctl list-timers --all --no-legend --no-pager 'xgw-*rollback*'
  systemctl --user list-units --all --no-legend --no-pager 'xgw-*monitor*' || echo USER_BUS_UNKNOWN
}
snapshot >"$D/before.json" || echo SNAPSHOT_UNAVAILABLE
config_sums >"$D/cfg.before"
timers >"$D/timers.before"
for f in zapret2.py net/nft.py net/iprule.py net/capture.py watch/panel.py watch/status_page.py; do
  installed=$(sudo sha256sum "$PKG/$f" | cut -d' ' -f1)
  matches=
  for rev in "$OLD" "$NEW"; do
    ref=$(git show "$rev:src/xgw/$f" | sha256sum | cut -d' ' -f1)
    if [[ $installed == "$ref" ]]; then matches+=" ${rev:0:7}"; fi
  done
  printf '%s %s\n' "$f" "${matches:-OTHER}"
done | tee "$D/source-match.txt"
```

Отчёт должен различать совпадение конкретных модулей и установленную версию. Совпадение с двумя SHA означает одинаковые байты. `OTHER` — смешанная или другая поставка, результаты пометить этой базой, файлы не заменять. Если снимок осознанно выполняется на отличающейся базе, укажи это по строкам. Если sudo недоступен после запроса доступа, используй созданный пользовательский checkout для Python-сверки каталога в §4, тестов §5 и публикации §6. Команды с sudo и сравнение приватных файлов в таком отчёте пометь BLOCKED_DEPENDENCY.

## 2. Реальный шлюз, A1/A2/A3

**A1 — владельцы HTTP и полномочия.** Открой приватный `before.json`. Для обоих портов запиши слушает ли он и совпадает ли владелец слушающего сокета с MainPID XGW. У активной службы запиши EUID и CapEff, укажи отдельно bounding set. Строка `daemon_owns=null` при выключенной LAN-странице — `NOT_ACTIVE`. Если `ss` видит listener, но сведения о PID недоступны, укажи `UNKNOWN_OWNER`. Так же укажи LoadState, активность и видимые caps обоих временных воркеров. Исчезнувший unit после остановки не описывает права живого процесса. Пароль/токен, cookie, полные команды процессов и URL панели не нужны.

**A2 — маршрутизация и ранние правила.** Во всех четырёх строках FIB сравни класс устройства и таблицу. Это локальный поиск маршрута по адресу с меткой до обработки конкретного сокета nft. В списке `before_100_including_own` могут быть собственные pref 90/95. По приватному выводу ниже сопоставь их с фактическими таблицами/селектором; в отчёте только приоритет, свой/чужой/неизвестный, применимость к этому запросу. При неявно выбранной WAN-карте класс `other` потребует локального сравнения устройства с default. Если обычный и составной mark выбирают разные пути, это различие FIB в указанных условиях; наблюдение потери связи требует пакетной фазы A4.

```bash
ip -4 -j rule show >"$D/rules-private.json"
ip -4 -j route show default >"$D/default-private.json"
for key in nf_conntrack_acct nf_conntrack_tcp_be_liberal; do
  if test -r "/proc/sys/net/netfilter/$key"; then
    printf '%s=%s\n' "$key" "$(cat "/proc/sys/net/netfilter/$key")"
  else
    printf '%s=UNKNOWN\n' "$key"
  fi
done
```

**A3 — шаги watchdog и контекст TUN.** Снять 180 секунд в текущем режиме, с согласованным временем начала/конца (UTC) и номером поколения процесса. Если в этом же проходе штатно доступно окно служебной пробы основной приёмки, выполнить идентичное чтение в нём. Иначе `probe_window=NOT_OBSERVED`, основной отчёт может добавить пару позже. Журнал ограничен предыдущими сутками и 200 подходящими сообщениями; посчитать отдельные записи ошибки и восстановления, один и тот же текст от CLI и systemd не считать двумя случаями. Исходный журнал приватный.

```bash
date -u +%FT%TZ
sudo "$PY" -IB "$ROOTDIR/audit_host_observe.py" watchdog --seconds 180 | tee "$D/watchdog.json" || echo WATCHDOG_UNKNOWN
date -u +%FT%TZ
sudo journalctl -u xgw-xray.service -u xgw.service --since '24 hours ago' --no-pager \
  --grep='маршруты в него на месте|правила сети не загружены|Control process exited|шаг watchdog занял' \
  -n 200 -o short-monotonic >"$D/journal-private.txt" || echo JOURNAL_UNKNOWN
```

Указать distinct_completed_steps, max/p95, число отсутствующих выборок и максимальный возраст записи. p95 при малом числе шагов — описательная статистика этого окна. Для вывода о задержке обработки `wake` нужны начало события и время его обработки на том же поколении. Без них `wake_latency=NOT_MEASURED`. Для TUN при наличии события сопоставить конкретный запуск unit, ошибку post-start и момент восстановления. Иначе `service_race=INCONCLUSIVE`. Задание не вызывает перезапуски ради статистики.

## 3. A4/A5/A6 — ядро ThinkCentre, установленный XGW и локальный TCP-приёмник

Прибор импортирует `/opt/xgw/lib/xgw`. Создаёт veth, одно тестовое устройство для маршрутизации и свой набор nft только внутри новых namespaces. На синтетическом порту 443 обменивается одним байтом, на 7443 дополнительно даёт клиенту закрыть сокет первым. На разделяемом с машиной ядре это проверяет поведение правил и TCP. Видеоплеер, реальный sing-box и обработчик nfqws2 в этом опыте не запускаются.

```bash
NET_INODE=$(stat -Lc '%i' /proc/self/ns/net)
lab_rc=0
sudo timeout -k 5s 120s unshare --net --mount --pid --fork --kill-child=KILL --mount-proc \
  "$PY" -IB "$ROOTDIR/audit_kernel_lab.py" lab "$NET_INODE" \
  >"$D/kernel.jsonl" 2>"$D/kernel-private.err" || lab_rc=$?
printf 'lab_rc=%d\n' "$lab_rc"
cat "$D/kernel.jsonl"
```

- **A4, метки и guard.** В шести строках `fib` при стандартной политике лаборатории mark 1 должен выбрать `audit-tun`, 2 и синтетический `0x20000001` — `audit0`. В строках TCP `echo_rc=0` значит клиент получил байт от получателя, `1` — соединение отклонено/не завершилось, `2` — ошибка прибора. Для каждой строки перенести expected/actual и дельту счётчиков. Контроли `bypass_control=0`, `unmarked_other_uid=1` обязательны. У Selected копия при закрытом допуске должна быть остановлена; при открытом допуске её эхо проходит, обычная метка без слушателя очереди останавливается. У Engine своя копия и bypass с пустой очередью должны проходить, посторонний UID остаётся закрыт. Если расходится основная строка при правильных контролях — повторить весь блок один раз в новом namespace. При неуспешном контроле вывод о механизме `INCONCLUSIVE`. Доставка защищённого контрольного потока на тестовый WAN получает отдельный приоритет независимо от остальных строк. Синтетическая метка проверяет маршрут копии; она не доказывает, что процесс породил такой пакет в интернете.
- **A5, закрытие сокета по UID.** Сравнить `close_control` и `close_xgw` по 12 попыток в одинаковой топологии. Указать client_ok, echo, client_fin, final_ack, errors и пакеты `all−uid` перед маркировкой. Строгое подтверждение здорового контрольного опыта — 12/12 эхо, FIN и завершений на получателе, ноль ошибок. Повторяемая потеря поздних ACK при полностью прошедшем контроле и исправном обмене данными — свидетельство дефекта лабораторного пути. Уточнить отдельно, наблюдались ли пакеты без совпавшего UID. По этим счётчикам нельзя присвоить пакету конкретный `skb->sk`. 12/12 в обоих окнах — `NOT_REPRODUCED_IN_THIS_CASE`; другие ядра, реальные RST и ретрансляции отдельно. Дефект только в A5 не переводит A4 в FAIL.
- **A6, TUN.** Для `tun_absent` нужны created/usable/routes=true, для `tun_down` created=false, usable/routes=true. Здесь выполняются настоящие функции `tun.ensure` и `iprule.ensure_tun`. Это проверяет создание/возврат устройства и маршрута. Дополнить состоянием `service_race` из A3. Недоступность `/dev/net/tun` блокирует только эту фазу. При неполном JSONL учитывать только фактически выведенные строки.
- При `unshare: Operation not permitted` или невозможности открыть veth/TUN запросить нужный доступ. Если окружение остаётся ограничено — `BLOCKED_DEPENDENCY`. Допустим один повтор после предоставления доступа. Все мутирующие команды данного раздела находятся внутри прибора, идентификаторы рабочих служб и nft основного namespace ему не передаются.

**Контроль выражения `ct packets` из Engine.** Выполнить отдельно от A4. Две группы по 8 малых UDP-датаграмм в свежем изолированном namespace. Здесь исследуется только выражение счётчика, для него используется loopback. У реального Engine дополнительно есть исключение loopback, фильтры сокета и очередь. Значение sysctl рабочего шлюза снято в A2.

```bash
acct_rc=0
sudo timeout -k 2s 25s unshare --net bash -s -- "$NET_INODE" >"$D/acct.txt" 2>"$D/acct-private.err" <<'LAB' || acct_rc=$?
set -euo pipefail
test "$(stat -Lc '%i' /proc/self/ns/net)" != "$1"
test "$(ip -o link show | wc -l)" -eq 1
ip link set lo up
nft -f - <<'NFT'
table ip audit_acct {
 chain out {
  type filter hook output priority 90; policy accept;
  udp dport 24000 ct direction original counter comment "all_zero"
  udp dport 24000 ct direction original ct packets <= 4 counter comment "first_zero"
  udp dport 24001 ct direction original counter comment "all_one"
  udp dport 24001 ct direction original ct packets <= 4 counter comment "first_one"
 }
}
NFT
for acct in 0 1; do
  sysctl -q -w "net.netfilter.nf_conntrack_acct=$acct"
  test "$(sysctl -n net.netfilter.nf_conntrack_acct)" = "$acct"
  /usr/bin/python3 -I - "$acct" <<'PY'
import socket, sys
with socket.socket(type=socket.SOCK_DGRAM) as rx, socket.socket(type=socket.SOCK_DGRAM) as tx:
    addr = ("127.0.0.1", 24000 + int(sys.argv[1]))
    rx.bind(addr)
    rx.settimeout(1)
    for _ in range(8):
        tx.sendto(b"x", addr)
        assert rx.recv(8) == b"x"
PY
done
nft -n list chain ip audit_acct out
LAB
printf 'acct_rc=%d\n' "$acct_rc"
cat "$D/acct.txt"
```

Указать все четыре счётчика и код выхода. Контроль валиден при `all_zero=all_one=8`. Группа 1 проверяет отсечение после первых четырёх пакетов конкретной UDP-сессии. Группа 0 показывает фактическое поведение ядра без учёта. Расхождение означает зависимость от sysctl, его нужно сопоставить с A2 и реальной политикой Engine перед изменением XGW. При отличии результата A5 от контроля один раз повторить A4–A6 в новом namespace, сохранить обе серии отдельно.

## 4. A7 — семантика установленного zapret2 и учёт охвата Flowseal

Проверить pin (v1.0.7, commit `038c97e…`). При несовпадении записать версию и результат как сравнение другой сборки, результаты не переносить на pinned. Lua-выражение передаётся отдельным аргументом, `--intercept=0`. Блок работает только с константами. Проверяются числовые позиции, отрицательный контроль и два входа TLSMod.

```bash
NF=/opt/xgw/zapret2/1.0.7/nfqws2
if test -x "$NF"; then
  "$NF" --version >"$D/nfq-version.txt" 2>&1
  LUA='local s="ABCDE"; local p=resolve_pos(s,"unknown","2"); local z=resolve_pos(s,"unknown","2",true); print("AUDIT_POS",resolve_pos(s,"unknown","1"),p,z,#s:sub(1,p-1),resolve_pos(s,"unknown","99")==nil); local m="rnd,dupsid,sni=www.google.com"; local a=tls_mod(string.rep(string.char(0),4),m,fake_default_tls); local b=tls_mod(fake_default_tls,m,fake_default_tls); print("AUDIT_TLS",type(a),type(b),type(b)=="string" and #b or 0)'
  lua_rc=0
  sudo timeout -k 2s 15s unshare --net "$NF" --qnum=201 --intercept=0 \
    "--lua-init=$LUA" >"$D/lua.txt" 2>&1 || lua_rc=$?
  printf 'lua_rc=%d\n' "$lua_rc"
  grep -E '^AUDIT_(POS|TLS)[[:space:]]' "$D/lua.txt" || true
else
  echo 'A7 binary missing'
fi
"$PY" - <<'PY'
import collections, json, pathlib
d = pathlib.Path("docs/helpers")
source = json.loads((d/"flowseal-youtube-source.json").read_text())
translated = json.loads((d/"flowseal-translation.json").read_text())["configurations"]
cut = collections.Counter()
http_ipid = []
for cfg in source["configurations"]:
    name = cfg["file"].removesuffix(".bat")
    plan = translated[name]
    included = [r for r in plan["profiles"] if r["status"] == "INCLUDED"]
    for p in cfg["all_profiles_in_source_order"]:
        opt = dict(p["options"])
        if "dpi-desync-cutoff" in opt:
            cut.update({status: 1 for status in
                        {r["status"] for r in plan["profiles"] if r["profile"] == p["profile"]}})
        for r, block in zip(included, plan["blocks"], strict=True):
            if (r["profile"] == p["profile"] and r["kind"].endswith("-HTTP")
                    and opt.get("ip-id") == "zero"):
                http_ipid.append((name, p["profile"], any("ip_id=zero" in a for a in block)))
print("CUTOFF", dict(cut), "HTTP_IP_ID", http_ipid)
PY
```

Ожидания `AUDIT_POS 2 3 2 2 true` и `AUDIT_TLS nil string N` при N>4. Вывести реально полученные значения. Сообщение о некорректной структуре четырёх байт ожидаемо при работающем положительном контроле. Отсутствие строки, timeout или ошибка инициализации — отдельный исход. `CUTOFF` ожидается 45 EXCLUDED_COVERAGE и 0 INCLUDED. Для `HTTP_IP_ID` пустой список означает отсутствие применимых расширенных HTTP-строк. Число стадий или успешная инициализация не измеряют эффективность на YouTube.

## 5. A8 — действующие контракты входа, Xray, маршрутов

Используй существующий тестовый Python с pytest от пользователя рабочего стола. Для проверки HTTP в тестах используются собственные временные токены и локальные серверы. По одному отчёту JUnit, с точными nodeid и отдельным статусом каждой проверки. Пакеты на шлюз для этой фазы не устанавливать.

```bash
cd "$D/source"
case_rc=0
PYTHONPATH="$PWD/src:$PWD" "$TPY" -m pytest -o addopts='' -q \
  tests/test_notify_page.py::test_server_requires_the_token \
  tests/test_notify_page.py::test_server_is_read_only \
  tests/test_panel.py::test_token_moves_into_a_cookie_and_out_of_the_address \
  tests/test_panel.py::test_one_time_login_code_works_once_and_only_for_a_minute \
  tests/test_cores.py::test_unsuitable_release_is_rejected_before_anything_is_replaced \
  tests/test_cores.py::test_new_core_that_fails_its_checks_is_replaced_by_the_old_one \
  tests/test_cores.py::test_diag_accepts_the_version_accepted_by_the_gateway \
  tests/test_net.py::test_rules_before_xgw_are_reported_and_left_alone \
  tests/test_net.py::test_ensure_keeps_a_foreign_rule_with_other_selectors \
  tests/test_net.py::test_tun_and_its_route_come_back_after_xray_starts_again \
  tests/test_nft.py::test_dedicated_singbox_uid_has_bypass_and_loopback_refusal \
  tests/test_desync_flowseal.py::test_reviewed_profiles_reference_pinned_files_and_keep_http_tls_separate \
  --junitxml="$D/contracts.xml" >"$D/contracts-private.log" 2>&1 || case_rc=$?
printf 'contracts_rc=%d\n' "$case_rc"
```

Записать pass/fail/skip/error и обезличенное первое расхождение. Прохождение теста постоянной ссылки подтверждает присутствие текущего механизма. Степень риска оценивать отдельно от факта приёма запроса. Тест отката использует фикстуру, рабочий бинарник шлюза остаётся на месте.

## 6. Завершение и обязательная автопубликация

```bash
snapshot >"$D/after.json" || echo SNAPSHOT_UNAVAILABLE
config_sums >"$D/cfg.after"
timers >"$D/timers.after"
cmp -s "$D/cfg.before" "$D/cfg.after" && echo CONFIG_IDENTICAL || echo CONFIG_CHANGED
sudo rm -- "$ROOTDIR/audit_host_observe.py" "$ROOTDIR/audit_kernel_lab.py"
sudo rmdir -- "$ROOTDIR"
```

Сравни `before.json`/`after.json` по службам, поколениям и конфигурации. Сверь имена и состояние исходных таймеров/монитора с учётом естественного течения времени. Для незапланированной смены поколения, изменения конфигов или исчезнувшего таймера записать время и возможное совпадение с основной приёмкой, причину пометить как неизвестную до подтверждения. Воспроизведение, uptime сутки, смена UTC и live IPv6 в этом задании не проверяются.

Один отчёт `docs/reports/YYYY-MM-DD_audit-recon.md`. Начни с версии Ubuntu/ядра, SHA приборов, соответствия установленным файлам и времени. Для A1–A8 укажи источник данных (рабочая машина/изолированное ядро/бинарник/фикстура), числитель и знаменатель, фактический контроль, исход и ограничение вывода. Заверши состоянием шлюза. Сохрани отчёт даже при блокере; приватные артефакты остаются вне Git.

Публикация в отдельном checkout исключает вмешательство в работу основной приёмки. При одновременной публикации основного отчёта использовать fetch/rebase и обычный push. Если файл этого задания на дату уже существует, добавь UTC-время к имени нового отчёта, сохрани прежний.

```bash
git -C "$REPO" fetch origin "$BR"
PUB="$D/publish"
git -C "$REPO" worktree add --detach "$PUB" FETCH_HEAD
cd "$PUB"
REPORT="docs/reports/$(date -u +%F)_audit-recon.md"
if test -e "$REPORT"; then REPORT="docs/reports/$(date -u +%FT%H%M%SZ)_audit-recon.md"; fi
```

Запиши свой отчёт в `$PUB/$REPORT`. Выполни сама:

```bash
test -s "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: report ThinkCentre gateway audit reconnaissance"
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
REPORT_SHA=$(git rev-parse HEAD)
git fetch origin "$BR"
git merge-base --is-ancestor "$REPORT_SHA" FETCH_HEAD
printf 'report=%s commit=%s\n' "$REPORT" "$REPORT_SHA"
```

Передай ссылку на опубликованный отчёт и SHA. Для подтверждённой потери защищённого трафика выдели режим и обе контрольные строки в первой строке результата. Для остальных исходов порядок решений описан в [плане разработки](DESYNC-ROADMAP.md).
