# ThinkCentre · диагностика UID и перехвата sing-box

**Ubuntu 24.04 LTS.** Flash сама запускает готовые команды и публикует
обезличенный отчёт при любом исходе. При недоступности терминала,
sudo, pytest, установленных ядер или GitHub запроси доступ. Доступные
фазы выполняются независимо. Код и проверки подготовлены Codex.

[Отчёт r3](../reports/2026-11-25T005145Z_t12-lan-singbox-r3.md) подтвердил
HTTP 200 через оба ядра, два dial на 443, штатный UID и ноль повторных
захватов UDP. На работающем шлюзе участников через мост пока нет.
В `xgw diag` теперь проверяются `CapInh` и `NoNewPrivileges`, а при
включённом локальном перехвате проверяется положение `return` для
выделенного UID относительно маркировки в цепочке IPv4 `output`.

## Запуск

Начни из обычной рабочей копии. При необходимости выполни `sudo -v`.
Через `XGW_TEST_PYTHON` задай существующий Python с pytest. Нестандартные
пути установленных ядер можно указать в `XGW_TEST_XRAY` и `XGW_TEST_SINGBOX`.
Режим рабочего шлюза оставь как есть. На нём запускается только чтение
и сравнение снимков. Временный стенд использует отдельные пространства
имён, локальный источник TLS и приватный каталог артефактов.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=7015097e367dd0df4b17f429203308323e7c52f4
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
XRAY_BIN=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
SB_BIN=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-t12-sb-diag.XXXXXXXX")
mkdir "$D/tree" "$D/kernel-private"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui packaging pyproject.toml \
  | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\nPRIVATE_ARTIFACTS %s\n' "$PRETTY_NAME" "$CODE" "$D"
uname -r
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests:$D/tree/tests/stand"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"

snapshot() {
  sudo -n timeout -k 3 60 "$PY" -I -B - snapshot <docs/helpers/audit_host_observe.py &&
    sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}

run_phase() {
  local label=$1 code=0
  shift
  "$@" >"$D/$label.log" 2>&1 || code=$?
  tail -n 18 "$D/$label.log"
  printf '%s_EXIT %s\n' "$label" "$code"
  return "$code"
}

host_diag() {
  sudo -n timeout -k 2 25 /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    "PYTHONPATH=$D/tree/src" "$PY" -B -P - <<'PYTHON'
import json

from xgw.config import load
from xgw.diag import Diag
from xgw.paths import Paths

paths = Paths.from_env()
cfg, _ = load(paths.config_file)
checks = Diag(cfg, paths, net=False)._core_users()
print(json.dumps({"state": "checked" if checks else "not_applicable",
                  "checks": [{"name": c.name, "level": c.level, "text": c.text} for c in checks]},
                 ensure_ascii=False))
PYTHON
}

kernel() {
  [[ $XRAY_BIN == /* && -x $XRAY_BIN && $SB_BIN == /* && -x $SB_BIN ]] || {
    printf 'STAND_CORES_UNAVAILABLE\n'; return 3;
  }
  "$SB_BIN" version | head -n 1 || true
  nft --version || true
  sudo -n timeout -k 5 180 unshare --mount --propagation private --pid --fork \
    --kill-child --mount-proc /bin/sh -c '
      mount -t tmpfs -o nosuid,nodev,mode=0755 tmpfs /run || exit 3
      mkdir /run/lan-artifacts || exit 3
      mount --bind "$1" /run/lan-artifacts || exit 3
      shift
      exec "$@"
    ' sh "$D/kernel-private" /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    "PYTHONPATH=$PYTHONPATH" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    XGW_XRAY_BIN="$XRAY_BIN" XGW_SINGBOX_BIN="$SB_BIN" \
    "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider --color=no -v -rs -s --tb=short \
    --basetemp /run/lan-artifacts/p \
    'tests/stand/test_stand_lan.py::test_lan_https_attributes_real_tproxy_socket[sing-box]'
}

before=0
snapshot >"$D/state.before" 2>"$D/snapshot.before.err" || before=$?
run_phase CONTRACTS timeout -k 3 90 "$TEST_PY" -B -P -m pytest \
  -o addopts= -p no:cacheprovider --color=no -v -rs --tb=short --basetemp "$D/pytest" \
  tests/test_diag.py::test_core_identity_checks_running_uid_and_all_capability_sets \
  tests/test_nft.py::test_singbox_output_rule_matches_the_exact_uid_before_the_capture_mark \
  tests/test_nft.py::test_singbox_output_rule_unreadable_is_unknown \
  tests/test_nft.py::test_dedicated_singbox_uid_has_bypass_and_loopback_refusal || true
run_phase HOST_DIAG host_diag || true
run_phase KERNEL kernel || true
after=0
snapshot >"$D/state.after" 2>"$D/snapshot.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
  if cmp -s "$D/state.before" "$D/state.after"; then
    printf 'T12_GATEWAY_UNCHANGED\n'
  else
    printf 'T12_GATEWAY_SNAPSHOT_DIFF\n'
  fi
else
  printf 'T12_GATEWAY_SNAPSHOT_NOT_AVAILABLE %s %s\n' "$before" "$after"
fi
BASH
~~~

## Итоги фаз

- **CONTRACTS** — прошедшие, упавшие и пропущенные проверки. Отдельно
  отметь UID другого пользователя, правило после маркировки, условное
  правило, недоступное чтение и выключенный `NoNewPrivileges`.
- **HOST_DIAG** — проверка запускается при наличии установленной
  конфигурации sing-box, в том числе без участника через мост. Запиши
  вердикты UID и прав процесса, а при включённом локальном перехвате
  также вердикт правила IPv4. На ThinkCentre получено `checked` с
  двумя OK. [Отчёт](../reports/2026-11-25T013151Z_t12-singbox-diag.md)
- **KERNEL** — штатное правило, `BRIDGE_OUTPUT_RULE`, HTTP 200 с
  проверкой TLS, `group=sing-box` и ноль повторных перехватов. В этом
  сценарии используется функция из `xgw diag`, читающая nftables.
- **Шлюз** — сравнение снимков и хэшей. Живой LAN ждёт отдельного
  авторизованного клиента, живой мост ждёт рабочего участника. Внешние
  HTTPS-запросы, установка и захват трафика в этот проход не входят.

## Автоматическая публикация

Публикуй версии, SHA, метки, исходы фаз и агрегаты. Адреса, снимки,
настройки, TLS-ключи и сырые журналы оставь на машине. Подставь
абсолютный путь к обезличенному Markdown в `REPORT_SRC`, выполни блок
из рабочей копии и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t12-sb-diag-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t12-singbox-diag.md"
test ! -e "$REPORT"
install -m 0644 -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre sing-box UID and capture diagnostics'
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
git fetch origin "$BR"
git merge-base --is-ancestor HEAD FETCH_HEAD
printf 'PUBLISHED %s %s\n' "$(git rev-parse HEAD)" "$REPORT"
BASH
~~~
