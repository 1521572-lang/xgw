# ThinkCentre · отмена проверки кандидата FreePool

Ubuntu 24.04 LTS. Кандидат `78891cc31eff99a4b892d560a8f0c60a6be5327f`. В предыдущем отчёте у 332 из 352
неудачных проверок был вердикт `TIMEOUT`. Старый кеш не содержит фаз.
Этот проход проверяет исправление отмены и выясняет, появились ли в
штатном кеше записи с фазой. [Отчёт разбивки](https://github.com/1521572-lang/xgw/blob/65d1b383757e530ec3f5b7426c550f87044c2fc8/docs/reports/2026-11-26T125249Z_freepool-r50-check-failures.md)

Flash сама выполняет команды. При недоступности терминала или чтения
кеша запросить доступ. Испытание использует отдельный процесс установленного
Xray и тестовый HTTP-ответ на 127.0.0.1. Кандидат запускается из временного
каталога. Штатный демон, его маршруты и режим пула работают в прежнем режиме.
[Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r50-probe-cancel.bundle)

## Прогон

Выполнить из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`. Если pytest находится в отдельном
окружении, задать `XGW_TEST_PYTHON`. По умолчанию используется `/opt/xgw/xray/xray`.
Для иной штатной установки задать `XGW_TEST_FREEPOOL_XRAY` с абсолютным путём к бинарнику.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=78891cc31eff99a4b892d560a8f0c60a6be5327f
D=$(mktemp -d "$HOME/xgw-freepool-cancel.XXXXXXXX")
PY=/usr/bin/python3
TEST_PY=$PY
XRAY=/opt/xgw/xray/xray
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
if [[ -v XGW_TEST_FREEPOOL_XRAY ]]; then XRAY=$XGW_TEST_FREEPOOL_XRAY; fi
unset XGW_TEST_FREEPOOL_XRAY
printf 'PRIVATE_ARTIFACTS %s\n' "$D"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r50-probe-cancel.bundle >"$D/code.bundle"
printf '%s  %s\n' '3e90ade6a8caededa671097b7306587c06562fe6d34dae4bf31849c41ba06481' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml | tar -x -C "$D/tree"
printf 'OS %s\nPINNED %s\n' "$PRETTY_NAME" "$CODE"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
  sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json
}
host_fields >"$D/before.txt"
status=0

timeout -k 3 120 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
  tests/test_freepool_cancel.py tests/test_freepool.py tests/test_freepool_backend.py \
  >"$D/contracts.log" 2>&1 || status=1
tail -n 24 "$D/contracts.log"
if [[ $XRAY = /* && -x $XRAY ]]; then
  timeout -k 2 10 "$XRAY" version >"$D/xray-version.txt"
  sed -n '1p' "$D/xray-version.txt"
  XGW_TEST_FREEPOOL_XRAY="$XRAY" timeout -k 3 25 \
    "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    'tests/test_freepool_cancel.py::test_cancelled_download_stops_real_loopback_socket[xray]' \
    >"$D/xray.log" 2>&1 || status=1
  tail -n 24 "$D/xray.log"
else
  printf 'R50_XRAY_CANCEL=NOT_RUN\n'
fi

if sudo -n timeout -k 2 15 /usr/bin/env -i "PYTHONPATH=$PYTHONPATH" "$PY" \
    -B -P -m xgw.cli pool candidates --explain --json >"$D/cache.json" 2>"$D/cache.err"; then
  "$PY" -I -B - "$D/cache.json" <<'PYTHON'
import json
import sys
from collections import Counter
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_bytes())
timeouts = Counter()
for row in data["failed_checks"]:
    if row["verdict"] == "TIMEOUT":
        timeouts[row["phase"]] += row["count"]
known = sum(value for phase, value in timeouts.items() if phase != "unknown")
print(json.dumps({"timeout_phases": timeouts, "total_timeouts": sum(timeouts.values()),
                  "known_timeout_phases": known, "mode": data["mode"]}, sort_keys=True))
print("R50_TIMEOUT_PHASES=OBSERVED" if known else "R50_TIMEOUT_PHASES=NOT_RUN")
PYTHON
else
  printf 'R50_TIMEOUT_CACHE_READ_FAILED\n'
fi

host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R50_HOST_FIELDS_MATCH\n'
else
  printf 'R50_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Итог

- `R50_CANCEL_CONTRACTS=PASS` требует зелёного базового набора. Тесты проверяют закрытие
  сокета, уборку процесса и файлов, прежний сохранённый вердикт и учёт
  частично прочитанных байтов.
- `R50_XRAY_CANCEL=PASS` требует прохода отдельного кейса с бинарником и совпадения
  снимков шлюза. При отсутствии бинарника указать `R50_XRAY_CANCEL=NOT_RUN`.
- `R50_TIMEOUT_PHASES=NOT_RUN` ожидаем, если в штатном кеше ещё нет новых записей.
  При наличии фаз опубликовать только счётчики. Испытание на loopback
  проверяет корректность отмены и не объясняет причину старых таймаутов.
- При любом исходе опубликовать один обезличенный `docs/reports/<UTC>_freepool-r50-probe-cancel.md` в ветке
  `docs/flash-proton-ui-manifest` обычным push. Указать SHA кандидата и ТЗ, ОС, версию ядра Xray
  если проверялось, исходы и итог сверки. Исходный кеш, журналы, адреса
  и конфиги оставить локально. При конфликте перенести только отчёт
  поверх актуальной вершины.
