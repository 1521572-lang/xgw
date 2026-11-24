#!/bin/bash
# Run the Flowseal settings acceptance with the pinned checkout and demo gateway.
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=$1
MODE=${2:-all}
[[ $CODE =~ ^[0-9a-f]{40}$ ]]
[[ $MODE == all || $MODE == ui ]]
REPO=$(git rev-parse --show-toplevel)
TEST_PY=${XGW_TEST_PYTHON:-/usr/bin/python3}
WEB_PY=${XGW_WEB_PYTHON:-$TEST_PY}
QT_PY=${XGW_QT_PYTHON:-$TEST_PY}
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-flowseal-ui.XXXXXXXX")
printf 'PINNED %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
git -C "$REPO" archive "$CODE" src tests docs/helpers vpn_ui pyproject.toml | tar -x -C "$D"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
export PYTHONPATH="$D:$D/src:$D/tests"

snapshot() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n timeout -k 3 60 /usr/bin/python3 -I -B - snapshot
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}

sudo -n true
snapshot >"$D/state.before"
if [[ $MODE == all ]]; then
  match_rc=0
  (cd "$REPO" && bash "$D/docs/helpers/flowseal_policy_trial.sh" "$CODE") \
    >"$D/match.out" 2>"$D/match.err" || match_rc=$?
  cat "$D/match.out"
  printf 'FLOWSEAL_MATCH_EXIT %s\n' "$match_rc"
fi
cd "$D"

contracts_rc=0
timeout -k 3 100 "$TEST_PY" -B -P -m pytest -o addopts= -p no:cacheprovider \
  -q --tb=short --portable tests/test_zapret2_panel.py tests/test_zapret2_management.py \
  >"$D/contracts.out" 2>&1 || contracts_rc=$?
tail -n 6 "$D/contracts.out"
printf 'FLOWSEAL_CONTRACTS_EXIT %s\n' "$contracts_rc"
if command -v node >/dev/null && [[ $(node -p "process.versions.node.split('.')[0]") -ge 18 ]]; then
  node_rc=0
  timeout -k 2 25 node --test tests/test_zapret2_web_refresh.cjs >"$D/node.out" 2>&1 || node_rc=$?
  tail -n 9 "$D/node.out"
  printf 'FLOWSEAL_NODE_EXIT %s\n' "$node_rc"
else
  printf 'FLOWSEAL_NODE_NOT_AVAILABLE\n'
fi

DRIVER=${XGW_GECKODRIVER:-}
if [[ -z $DRIVER ]]; then
  for candidate in /snap/bin/geckodriver /snap/bin/firefox.geckodriver; do
    if [[ -x $candidate ]]; then DRIVER=$candidate; break; fi
  done
fi
if [[ -z $DRIVER ]]; then DRIVER=$(command -v geckodriver || true); fi
if command -v xvfb-run >/dev/null && [[ -x $DRIVER && -x $WEB_PY ]] &&
   "$WEB_PY" -B -c 'import selenium'; then
  web_rc=0
  env -u WAYLAND_DISPLAY -u MOZ_HEADLESS -u MOZ_ENABLE_WAYLAND \
    timeout -k 5 145 xvfb-run -a "$WEB_PY" -B -P "$D/docs/helpers/flowseal_ui_firefox.py" \
    "$D" "$DRIVER" >"$D/web.out" 2>"$D/web.err" || web_rc=$?
  cat "$D/web.out"
  printf 'FLOWSEAL_WEB_EXIT %s\n' "$web_rc"
else
  printf 'FLOWSEAL_WEB_NOT_AVAILABLE\n'
fi

if [[ -x $QT_PY ]] && "$QT_PY" -B -c 'import PyQt6.QtWidgets, pytest'; then
  qt_rc=0
  QT_QPA_PLATFORM=offscreen timeout -k 3 60 "$QT_PY" -B -P -m pytest \
    -o addopts= -p no:cacheprovider -q --tb=short \
    tests/test_gui_qt.py::test_alt9_settings_dialog_preserves_saved_exclusions_and_sends_intentional_clear \
    >"$D/qt.out" 2>&1 || qt_rc=$?
  tail -n 6 "$D/qt.out"
  printf 'FLOWSEAL_QT_EXIT %s\n' "$qt_rc"
else
  printf 'FLOWSEAL_QT_NOT_AVAILABLE\n'
fi

snapshot >"$D/state.after"
if cmp -s "$D/state.before" "$D/state.after"; then
  printf 'FLOWSEAL_UI_GATEWAY_UNCHANGED\n'
else
  printf 'FLOWSEAL_UI_GATEWAY_STATE_DIFFERED\n'
  exit 2
fi
[[ ${match_rc:-0} == 0 && $contracts_rc == 0 && ${node_rc:-0} == 0 &&
   ${web_rc:-2} == 0 && ${qt_rc:-2} == 0 ]]
