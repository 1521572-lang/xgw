# ThinkCentre · ограничение очереди Engine, завершение TCP и состояние off

Цель этого дополнения к [основной приёмке](COMBINED-ADMISSION-2026-11-19.md) — разрешить три вопроса из [первого отчёта](../reports/2026-11-19_audit-recon.md). В нём при выключенном учёте conntrack старое правило очереди совпало 8 раз из 8. Клиент получил эхо и отправил FIN во всех 12 соединениях, но под правилами XGW принимающий сокет ни разу не достиг TCP_CLOSE за 800 мс. При заявленном off/off один из воркеров был активен.

Исполнитель Flash сам запускает опубликованные команды на Ubuntu 24.04 LTS amd64, при необходимости запрашивает терминал и sudo. На разработку, редактирование приборов и исправление тестов задание не распространяется. Ориентир 10–20 минут. Подготовка, чтение состояния и работа в отдельных пространствах имён допускаются во время суточного наблюдения. Выбери период без смены рабочего режима из основной приёмки. Смена режима во время серии делает только эту серию несопоставимой. Установку, перезапуск служб, изменение sysctl хоста и таймеров этот проход не требует.

## 1. Подготовка

Запускай блоки по порядку в одном Bash. Начни в существующем checkout XGW. Обычный пользователь ведёт Git и запускает pytest. Root используется для чтения состояния и лабораторных пространств имён. Приватные результаты остаются в каталоге с правами 0700. Каждую независимую фазу можно закончить, даже если другая получила BLOCKED. Если нужен доступ, запроси его сама и повтори только соответствующую фазу. Никому не передавай команду для ручного запуска.

```bash
set -euo pipefail
umask 077
. /etc/os-release
test "$ID/$VERSION_ID/$(dpkg --print-architecture)" = ubuntu/24.04/amd64
printf '%s\n' "$PRETTY_NAME"
uname -r
nft --version
BR=integration/zapret2-batch1
CODE=df937840ad59e55a7e72e519cbd83fdd3c9c3568
REPO=$(git rev-parse --show-toplevel)
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-audit-followup.XXXXXXXX")
git -C "$REPO" worktree add --detach "$D/source" "$CODE"
cd "$D/source"
PY=/usr/bin/python3
TPY=${XGW_TEST_PYTHON:-$PY}
```

Для фаз 3 и 4 выполни подготовку ниже. При отсутствии sudo переходи к фазам 2 и 5. Образец приложения для запуска от root извлекается непосредственно из закреплённого Git-объекта. В /opt/xgw ничего не устанавливается.

```bash
sudo -v
R=$(sudo mktemp -d /run/xgw-audit-followup.XXXXXXXX)
git archive "$CODE" src/xgw | sudo tar --no-same-owner -xf - -C "$R"
for h in audit_host_observe.py audit_kernel_lab.py; do
  git show "$CODE:docs/helpers/$h" | sudo tee "$R/$h" >/dev/null
  sudo chmod 0500 "$R/$h"
  git show "$CODE:docs/helpers/$h" | sudo cmp - "$R/$h"
done
observe() { sudo timeout 30s "$PY" -IB "$R/audit_host_observe.py" desync; }
baseline() {
  sysctl -n net.netfilter.nf_conntrack_acct
  sudo sha256sum /etc/xgw/{config.toml,panel.json}
}
baseline >"$D/host.before"
systemctl list-timers --all --no-pager 'xgw-*rollback*' >"$D/timers.before"
for f in daemon.py net/nft.py nfqws2.py watch/zapret2_control.py; do
  sum=$(sudo sha256sum "/opt/xgw/lib/xgw/$f" | cut -d' ' -f1)
  matches=
  for rev in 3630b44502b872ca3788e0824c6a9d0d8363b561 46c69fde43ff64f9952bf628b404ba8720fa62e7 "$CODE"; do
    if [[ $(git show "$rev:src/xgw/$f" | sha256sum | cut -d' ' -f1) == "$sum" ]]; then
      matches+=" ${rev:0:7}"
    fi
  done
  printf '%s %s\n' "$f" "${matches:-OTHER}"
done >"$D/installed.txt"
```

## 2. Контракты кандидата

Используй существующее окружение Python с pytest на машине. Если его путь отличается, укажи его в TPY. Прогоны идут от пользователя рабочего стола.

```bash
test_rc=0
PYTHONPATH="$D/source/src:$D/source" "$TPY" -m pytest -q -o addopts='' \
  tests/test_nfqws2.py::EngineTests::test_accounting_controls_engine_rules_and_warnings \
  tests/test_nfqws2.py::EngineTests::test_accounting_loss_stops_worker_and_skips_engine_profiles \
  tests/test_nfqws2.py::EngineTests::test_nfqueue_is_bounded_fail_open_and_loop_free \
  tests/test_nfqws2.py::EngineTests::test_disabled_engine_does_not_touch_runtime \
  tests/test_zapret2.py::test_reply_window_requires_accounting_and_keeps_first_packets_bounded \
  tests/test_zapret2.py::test_synack_observation_arms_only_marked_handshakes_and_uses_selected_queue \
  tests/test_zapret2_panel.py::test_engine_states tests/test_desync_worker.py \
  --junitxml="$D/contracts.xml" >"$D/contracts.txt" 2>&1 || test_rc=$?
printf 'contracts_rc=%d\n' "$test_rc"
tail -n 3 "$D/contracts.txt"
```

PASS требует прохождения всех собранных случаев. Запиши число и nodeid каждого отказа или пропуска. При 0 или отсутствующем ключе проверяется отсутствие очереди, при 1 — её восстановление. При потере учёта работающий контроллер освобождает воркер, список профилей сохраняет базовый Xray, карточка передаёт причину. Выбранный маршрут имеет свои контроли SYN/ACK и окна ответов.

## 3. Две независимые серии на ядре рабочей машины

Прибор создаёт в каждой серии свежие сетевой и PID namespaces и отдельный namespace получателя. Порты 443/7443/7444 ведут только к синтетическому соседу через veth. В режиме candidate импортируется код из закреплённого архива. Сначала прибор проверяет изоляцию, затем применяет правила и меняет учёт только внутри сети опыта. Обработчика NFQUEUE здесь нет. Доставка UDP подтверждается независимым получателем через канал управления, без UDP-ответа, поэтому счётчик conntrack растёт на один пакет за отправку.

```bash
NET_INODE=$(stat -Lc '%i' /proc/self/ns/net)
for n in 1 2; do
  rc=0
  sudo timeout -k 5s 150s unshare --net --mount --pid --fork --kill-child=KILL --mount-proc \
    "$PY" -IB "$R/audit_kernel_lab.py" candidate "$NET_INODE" \
    >"$D/kernel-$n.jsonl" 2>"$D/kernel-$n.err" || rc=$?
  printf 'series=%d rc=%d\n' "$n" "$rc"
  cat "$D/kernel-$n.jsonl"
done
baseline >"$D/host.after"
cmp "$D/host.before" "$D/host.after" || echo HOST_BASELINE_CHANGED
systemctl list-timers --all --no-pager 'xgw-*rollback*' >"$D/timers.after"
```

Обе серии обязательны, в том числе при расхождении с ожиданиями. При отказе изоляции укажи точную операцию и ошибку. В основном namespace опыт не повторять. Если указанный бинарник или Lua-комплект Engine недоступен, сохрани уже собранные строки, статус UDP будет BLOCKED_DEPENDENCY. Таймеры сравнивай по имени и назначению с учётом хода времени; конфиги и значение sysctl — по совпадению до/после.

| Проверка | Критерий для каждой серии |
|---|---|
| Маршрут и контроли | Шесть FIB-строк. Метка 1 выбирает audit-tun, 2 — audit0. Для каждой из девяти строк echo сопоставить expected_rc и echo_rc, отдельно указать отрицательный контроль unmarked_other_uid. При его доставке дать FAIL приоритет в отчёте. |
| A5 без правил, 12 соединений | client_ok=echo=client_fin=final_ack=12, errors=client_errors=0. final_ack — историческое имя числа сокетов, достигших TCP_CLOSE. |
| A5 с XGW, 12 соединений | Показать client_ok, echo, client_fin, final_ack, last_ack_at_deadline, other_at_deadline и ошибки. Для каждой фазы — дельты all, uid, marked_zero, marked_proxy, after_guard_wan, after_guard_tun. Это счётчики всей серии. При здоровом контроле и повторном расхождении обеих пар — REPRODUCED_IN_LAB. LAST_ACK фиксирует состояние получателя в конце окна. Из этих чисел нельзя установить принадлежность каждого позднего пакета или влияние на рабочий sing-box. Если расходятся сами контроли или серии, указать INCONCLUSIVE. |
| Учёт выключен | install_acct_0 даёт actual=0, queue=null. В unaccounted получено 8/8, queue_matches=0. Хостовый sysctl сверяется отдельно. |
| Учёт включён | install_acct_1 даёт actual=1, queue=200. У существующего потока ожидается 8/8 и 0 совпадений. У нового потока ожидается 8/8 и ровно 4 совпадения. Показать все четыре величины. Расхождение по старому потоку фиксировать отдельно. Это попадания под настоящий verdict с bypass, доставку в процесс проверяют другие сценарии. |
| TUN | Для absent и down сверить usable/routes и время. Результат относится к пространству имён. |

## 4. Рабочий шлюз · политика и владелец очереди

Дождись обычного периода off/off, если он предусмотрен текущей основной приёмкой. Во время суточного окна снимки допустимы сразу. Не переключай режим ради этих трёх чтений. Если фактическая политика другая, сохрани её значение и пометь проверку off как NOT_OBSERVED.

```bash
for n in 1 2 3; do
  rc=0
  observe >"$D/runtime-$n.json" 2>"$D/runtime-$n.err" || rc=$?
  printf 'sample=%d rc=%d\n' "$n" "$rc"
  if test "$rc" -eq 0; then cat "$D/runtime-$n.json"; fi
  if test "$n" -lt 3; then sleep 20; fi
done
```

Для сравнения нужны три свежих снимка с совпавшей ревизией политики, стабильным InvocationID демона и одинаковыми mode/engine. Запиши span_s и возраст снимков, факт обновления status_at, unit/lease, MainPID и InvocationID воркеров (в публикации достаточно «тот же/сменился»), listed/owner_verified, размер допуска и дельты seq и nft-счётчиков. Один номер очереди может быть настроен у обоих воркеров. Проверка owner_verified связывает netlink-сокет именно с MainPID. При смене поколения или сбросе счётчиков дельта неопределённа. Для читаемого guard пустой set имеет размер 0, отсутствующий set — null, а guard_read=false означает отсутствие сведений. Отсутствующий или недоступный proc-файл даёт listed=null.

При стабильном off/off, обоих неактивных unit, пустой резервации, закрытом/отсутствующем допуске и отсутствии подтверждённого владельца записать OFF_CONSISTENT, указав качество каждого наблюдения. Если активный unit держит очередь — OFF_WITH_OWNER, отдельно отразить, растут ли seq/счётчики при том же поколении. Если unit активен, а принадлежность сокета установить не удалось — OWNER_UNCONFIRMED. Неполные или несвежие ключевые наблюдения дают INCONCLUSIVE. Из отсутствия прироста за 40 секунд вывод о других интервалах не следует.

## 5. Завершение и автоматическая публикация

Проверь совпадение host.before/after и состояние ранее вооружённого таймера. В отчёт включи дату и версию ОС, код кандидата, фактическую установленную базу по данным основной приёмки (при неизвестной версии так и укажи), версии ядра/nft, результаты контрактов, две отдельные таблицы TCP/UDP, наблюдение off и влияние на основной прогон. Укажи по каждой фазе PASS, FAIL, INCONCLUSIVE или BLOCKED и факты для этого вывода. Идентификаторы, адреса подписок, секреты, полный статус и правила рабочего шлюза не публикуются. Код приложения Flash не меняет.

Создай отчёт в отдельном checkout. Команды работают и после частичного прохода. Впиши результаты как Markdown в переменную пути REPORT с помощью своего редактора, затем выполни второй блок. При конфликте публикации сохрани собственный отчёт под уникальным именем, чужие изменения оставь в ветке.

```bash
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$D/publish" FETCH_HEAD
cd "$D/publish"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_audit-engine-close.md"
```

```bash
test -s "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: report Engine accounting, TCP close and queue ownership on ThinkCentre"
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
