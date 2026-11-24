# ThinkCentre — переход Standalone и возврат к поколениям sing-box

**Ubuntu 24.04 LTS.** Flash сама выполняет команды и автоматически
публикует один обезличенный отчёт при любом исходе. Запроси доступ при
недоступности терминала, sudo или GitHub.

В r2 штатное ожидание остановки VPN было принято сценарием за отказ.
После дополнительных прогонов обычный VPN работал, но вместо
управляемого поколения остался базовый юнит sing-box. Этот проход
проверяет код исправления в тестовых каталогах и читает текущее
состояние рабочего шлюза. Сетевые переключения, установка и CDN-пробы
в этом задании — `NOT_RUN`. [Отчёт r2](../reports/2026-11-23T110026Z_t09-live-worker-timing.md)

## 1. Запуск

Выполни `sudo -v`. Если pytest установлен в venv, экспортируй абсолютный
`XGW_TEST_PYTHON`. Запусти блок из рабочей копии XGW.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
printf 'STANDALONE_RETURN_HOST %s %s\n' "$PRETTY_NAME" "$(uname -r)"
BR=integration/zapret2-batch1
CODE=d8a4a0967a009ec6fb1a4b6dcf81fa27e5836c5a
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-standalone-return.XXXXXXXX")
printf 'STANDALONE_RETURN_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests docs/helpers packaging vpn_ui pyproject.toml |
  tar -x -C "$D/tree"
cd "$D/tree"
export PYTHONPATH="$D/tree:$D/tree/src:$D/tree/tests"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=

snapshot() {
  local label=$1 unit units
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n timeout -k 3 60 "$PY" -I -B - snapshot >"$D/fib.$label.json" || return
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.$label" || return
  units=$(timeout -k 2 8 systemctl list-units --all --plain --no-legend --no-pager \
    'xgw-singbox*.service') || return
  for unit in xgw-singbox.service xgw-singbox-blue.service xgw-singbox-green.service; do
    printf '%s\n' "$unit"
    if awk '{print $1}' <<<"$units" | grep -Fx "$unit" >/dev/null; then
      timeout -k 2 8 systemctl show "$unit" -p LoadState -p ActiveState -p MainPID || return
    else
      printf 'UnitNotListed\n'
    fi
  done >"$D/units.$label"
  sudo -n timeout -k 2 12 "$PY" -I -B - >"$D/generation.$label.json" <<'PY'
import json
from pathlib import Path

runtime = Path("/run/xgw")
file = runtime / "singbox-generations.json"
try:
    state = json.loads(file.read_bytes())
except FileNotFoundError:
    state = {}
fields = {"active": state.get("active", "legacy"),
          "marker_exists": (runtime / "singbox-managed").is_file(),
          "state_exists": bool(state), "pending": bool(state.get("pending")),
          "draining": bool(state.get("draining")),
          "resume_managed": state.get("resume_managed") is True}
print(json.dumps(fields, sort_keys=True))
PY
}

before=0
if snapshot before; then
  before=1
  printf 'STANDALONE_RETURN_BEFORE\n'
  cat "$D/generation.before.json"
fi

contracts() {
  local label=$1 rc=0
  shift
  timeout -k 3 180 "$TEST_PY" -B -P -m pytest \
    -o addopts= -p no:cacheprovider -q --tb=short "$@" >"$D/$label.out" 2>&1 || rc=$?
  printf 'STANDALONE_RETURN_TEST %s %s\n' "$label" "$rc"
  tail -n 4 "$D/$label.out"
}
contracts status --portable tests/test_selective_admission.py tests/test_desync_standalone.py \
  tests/test_zapret2.py tests/test_zapret2_panel.py
contracts managed-contract tests/test_singbox_generations.py::test_standalone_return_keeps_legacy_until_managed_bridge_is_verified
contracts generations-api tests/test_singbox_generations.py tests/test_applier.py

if (( before )) && snapshot after; then
  printf 'STANDALONE_RETURN_AFTER\n'
  cat "$D/generation.after.json"
  if cmp -s "$D/fib.before.json" "$D/fib.after.json" &&
     cmp -s "$D/settings.before" "$D/settings.after" &&
     cmp -s "$D/units.before" "$D/units.after" &&
     cmp -s "$D/generation.before.json" "$D/generation.after.json"; then
    printf 'STANDALONE_RETURN_GATEWAY_UNCHANGED\n'
  else
    printf 'STANDALONE_RETURN_GATEWAY_CHANGED\n'
  fi
else
  printf 'STANDALONE_RETURN_GATEWAY_NOT_VERIFIED\n'
fi
BASH
~~~

## 2. Проверка на копии установленного пакета

После контрактов раздела 1 запусти подготовку пяти файлов на копии
`/opt/xgw/lib/xgw`. Если по разделу 1 уже есть опубликованный результат
для `d8a4a09`, используй его и выполни только этот раздел. Сценарий
копирует установленный пакет в приватный каталог, применяет точный
патч к копии и сверяет исходные файлы после проверки.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=947cf7236f5a7466c49d0630699ceb6167c95d80
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/standalone_return_preflight.sh" | bash -s -- "$CODE"
BASH
~~~

Ожидается `STANDALONE_OVERLAY_COPY_PATCHED` либо
`STANDALONE_OVERLAY_ALREADY_PRESENT`, затем `STANDALONE_OVERLAY_COPY_COMPILES`,
6 контрактов статуса и три контракта возврата на копии. Среди них
отмена раннего входа до остановки мостов и в процессе остановки. Хелпер панели
проверяется в разделе 1 на полном дереве с его зависимостями. Финальная метка
`STANDALONE_OVERLAY_INSTALLED_UNCHANGED` подтверждает, что пять
установленных файлов совпали. При `STANDALONE_OVERLAY_CONTEXT_MISMATCH`
укажи имя файла и обезличенную причину. Патч и установленный пакет
остаются зафиксированными для сверки Codex.

## 3. Критерии отчёта

- `status` — 135 тестов. Старый API с `blocked/vpn_stopping`
  должен дождаться `preparing/nfqueue` и подтверждённого `active`.
  Штатное ожидание публикуется как `preparing`, а `queue_busy`
  завершает ожидание с явной причиной. До готовности прямой маршрут
  закрыт.
- `managed-contract` — один тест. После остановки двух юнитов намерение
  вернуть управляемое поколение сохраняется в `/run`. Базовый sing-box
  поднимается первым. Отказ проверки кандидата оставляет его работающим
  и сохраняет признак ожидания. После успешной проверки и применения
  через API состояние становится `blue` или `green`, признак очищается,
  устаревший базовый юнит переходит в штатный drain. Набор
  `generations-api` проверяет соседние пути API и отката.
- Приведи значения `active`, `marker_exists`, `pending`, `draining` и
  `resume_managed` на работающем шлюзе до и после. В r2 остался
  `active=legacy`. Отсутствие нового признака в установленной базе
  допустимо. При расхождении укажи поле, фазу и наблюдение. Проверка
  реального восстановления поколения остаётся отдельным проходом.
- Укажи SHA и версию Ubuntu. Публикуй только итоги и обезличенные
  значения. Исходные настройки, SHA конфигов, PID и приватные пути
  остаются на машине.
- Укажи отдельно итог из исходников и итог на копии установленного пакета.
  На рабочем пакете в этом задании выполняется чтение.

## 4. Автоматическая публикация

Задай абсолютный путь к отчёту в `REPORT_SRC`. Выполни блок из рабочей
копии при любом исходе. Верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-standalone-return-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_standalone-managed-return.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Standalone and managed sing-box return'
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
