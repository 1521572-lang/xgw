# ThinkCentre — повторная приёмка контрактов nftables и Tailscale

**Ubuntu 24.04 LTS.** Flash сама выполняет команды и публикует один
обезличенный отчёт при любом исходе. Если недоступны терминал, панель
или sudo, запроси доступ. Правила тестовых конфигураций загружаются
только в отдельные сетевые пространства имён.

Предыдущий проход подтвердил оба пересчёта видео, все девять проверок
`nft --check` и исходное состояние шлюза. В тестах nft пять ожиданий
зависели от системной записи `xgw-singbox`. Четыре проверки Tailscale
сравнивали порядок исключений с ранним отказом для loopback. Кандидат
убирает зависимость от системного UID в базовых фикстурах, проверяет
отдельный UID sing-box и сравнивает исключения Tailscale
с завершающим общим отказом. [Предыдущий отчёт](../reports/2026-11-21T114622Z_playback-metrics-and-marks.md)

## 1. Один запуск

Запусти блок Bash из checkout XGW как пользователь панели. Запиши
`PRETTY_NAME`, ядро и версию nftables. Если pytest установлен
в отдельном окружении, экспортируй абсолютный `XGW_TEST_PYTHON`.
При необходимости подтверди sudo в доступном интерактивном терминале
через `sudo -v`, затем проверь `sudo -n true`.

```bash
bash <<'BASH'
set -uo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]] || exit 2
BR=integration/zapret2-batch1
CODE=bccf12d5a5c74de204bfdfcf0352c550cea0753b
BASE=91abb23512b45e60d2e8492ade3864cb36b81ed2
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
REPO=$(git rev-parse --show-toplevel) || exit 2
D=$(mktemp -d "$HOME/xgw-nft-gate.XXXXXXXX") || exit 2
SRC="$D/current"
OLD="$D/baseline"
printf 'Private run: %s\n' "$D"
trap 'for tree in "$SRC" "$OLD"; do
        if [[ -f "$tree/.git" ]]; then
          git -C "$REPO" worktree remove "$tree"
        fi
      done' EXIT
git -C "$REPO" fetch origin "$BR" &&
  git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD &&
  git -C "$REPO" merge-base --is-ancestor "$BASE" "$CODE" &&
  git -C "$REPO" diff --quiet "$BASE" "$CODE" -- src/xgw &&
  git -C "$REPO" worktree add --detach "$OLD" "$BASE" &&
  git -C "$REPO" worktree add --detach "$SRC" "$CODE" || exit 2

run() {
  local label=$1 rc
  shift
  "$@" >"$D/$label.out" 2>"$D/$label.err"
  rc=$?
  printf '%s\t%s\n' "$label" "$rc" | tee -a "$D/steps.tsv"
  return "$rc"
}
contracts() (
  local tree=$1 junit=$2
  cd "$tree" || exit 2
  [[ $TEST_PY == /* && -x $TEST_PY ]] || exit 2
  timeout -k 4 180 env "PYTHONPATH=$tree/src:$tree" "$TEST_PY" -B -P -m pytest \
    -o addopts='' -o junit_family=xunit2 -p no:cacheprovider -q "--junitxml=$junit" \
    tests/test_nft.py tests/test_zapret2.py tests/test_tailscale.py tests/test_tailscale_t2.py
)
vpn_control() {
  systemctl is-active --quiet xgw.service || return
  systemctl is-active --quiet xgw-xray.service || return
  timeout -k 2 12 env PYTHONPATH=/opt/xgw/lib "$PY" -B -P -m xgw.desync.client status |
    "$PY" -I -c 'import json, sys
v = json.load(sys.stdin)
assert v["fresh"] and v["policy_matched"]
assert v["mode"] == v["engine_mode"] == v["state"] == "off"
print("off/off fresh matched")' || return
  timeout -k 2 12 sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
kernel_fixture() {
  local fixture=$1
  env "PYTHONPATH=$SRC/src:$SRC" "$PY" -B -P -m docs.helpers.nft_rules_fixture "$fixture" \
    >"$D/$fixture.nft" || return
  timeout -k 3 25 sudo -n unshare --net -- /bin/bash -e -c '
    nft --check --file "$1"
    printf "check OK\n"
    nft --file "$1"
    printf "load OK\n"
    nft list ruleset
    printf "list text OK\n"
    nft --json list ruleset
    printf "list json OK\n"
  ' _ "$D/$fixture.nft"
}

run rules-base contracts "$OLD" "$D/base.xml"
run rules-current contracts "$SRC" "$D/current.xml"
run rules-comparison "$PY" -I -B "$SRC/docs/helpers/acceptance_test_gate.py" \
  --current "$D/current.xml" --baseline "$D/base.xml" \
  --current-source "$SRC" --baseline-source "$OLD"

if run sudo sudo -n true &&
   exec 9>>"${XDG_RUNTIME_DIR:-$HOME}/xgw-t09-live.lock" &&
   run lock flock -n 9 && run vpn-before vpn_control; then
  for case in off capture selected selected-replies engine tailscale-direct tailscale-vpn \
      containers blocked; do
    run "netns-$case" kernel_fixture "$case"
  done
  run vpn-after vpn_control &&
    run control-unchanged cmp -s "$D/vpn-before.out" "$D/vpn-after.out"
fi
BASH
```

## 2. Критерии

- **RULES_UNIT** — запиши счётчики passed, failed и skipped для каждой
  копии, а также первую ошибку при отказе. Для кандидата нужны код 0
  и `rules-comparison.ok=true`. Укажи, сколько из девяти известных
  отказов подтвердилось на базе и исчезло на кандидате. Пропуски
  тестов, требующих root, запиши отдельно. При сбое сбора, неполном
  JUnit или новом skip сохрани вердикт отказа.
- **NETNS_NFT** — для каждой из девяти конфигураций нужны `check OK`,
  `load OK`, `list text OK` и `list json OK`. В `netns-containers.out`
  проверь присутствие `singbox_tcp_close` и `singbox_tail_ack`.
  При отказе первого вызова `unshare` укажи блокер. Все вызовы
  привилегированного nft должны оставаться внутри `unshare --net`.
- **CONTROL** — проверь финальное off/off fresh/matched, обе
  активные службы и равенство хэшей настроек. Если режим или хэши
  разошлись, запиши наблюдение и фактическое состояние шлюза.

Результат netns покрывает загрузку и вывод правил на ядре ThinkCentre.
Результат передачи пакетов и FIN/ACK остаётся в принятом отчёте о
TCP close. [Отчёт TCP close](../reports/2026-11-19T160130Z_tcp-close-ab-r2.md)

## 3. Публикация

Подготовь один обезличенный Markdown при любом исходе. Укажи SHA базы,
кандидата, конфигурации и коды проверок. JUnit, полные списки правил,
адреса и хэши настроек остаются в приватном каталоге. Экспортируй
абсолютный путь к отчёту в `REPORT_SRC`. Сама запусти блок
из checkout XGW и верни ссылку после проверки удалённой ветки.

```bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
test -s "$REPORT_SRC"
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-nft-gate-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_nft-rules-gate.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "Report ThinkCentre nftables and Tailscale rule gate"
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
SHA=$(git rev-parse HEAD)
git fetch origin "$BR"
git merge-base --is-ancestor "$SHA" FETCH_HEAD
printf 'https://github.com/1521572-lang/xgw/blob/%s/%s\n' "$SHA" "$REPORT"
BASH
```
