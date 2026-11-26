# ThinkCentre · публичный IPv4 WAN для FreePool R39

Ubuntu 24.04 LTS. Кандидат `06e3f010c1c3a3ed267774939eebe3ebd4b5376e`. Проверить фоновую привязку
скорости FreePool к публичному IPv4 при неизменном локальном маршруте.
[Отчёт полного ID моста](https://github.com/1521572-lang/xgw/blob/2271bb637cec00aa5ad71ca3c06dc0e0fbfa250b/docs/reports/2026-11-26T175911Z_freepool-r39-bridge-id.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-public-wan.bundle)

Flash сама выполняет технический прогон. При недоступном терминале
запросить доступ. Контракты используют фикстуры и loopback. Проверка
WAN выполняет одну ограниченную пробу существующего HTTPS-адреса
`probe.trace_url` из настроек. Она использует штатную bypass-марку.
Требуется уже доступный административный сеанс с возможностью
поставить SO_MARK. Службы, настройки и назначение клиентов для
этой проверки не изменяются. Публичный адрес и отпечаток в отчёт
не включаются.

## Прогон

От обычного пользователя из полного клона с базой
`9e4c025efb5404086ae601f3dc535a9e881521dd`. При необходимости указать
путь к Python с pytest через `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=06e3f010c1c3a3ed267774939eebe3ebd4b5376e
D=$(mktemp -d /tmp/xgw-r39-public.XXXXXXXX)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-public-wan.bundle >"$D/code.bundle"
printf '%s  %s\n' '9ff345e6eb8a20163b672b2fb5d11f8316f983a116c796cfff2b742d5be6430d' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml config.example.toml | tar -x -C "$D/tree"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
}
host_fields >"$D/before.txt"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"
status=0
if timeout -k 5 180 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_freepool_wan_epoch.py tests/test_freepool_traffic.py \
    tests/test_config.py tests/test_fetch.py >"$D/contracts.log" 2>&1; then
  printf 'R39_PUBLIC_WAN_CONTRACTS=PASS\n'
else
  printf 'R39_PUBLIC_WAN_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 20 "$D/contracts.log"

if sudo -n true >"$D/sudo.log" 2>&1; then
  if timeout -k 3 45 sudo -n "$PY" -I -B - "$D/tree/src" >"$D/wan.log" 2>&1 <<'PYTHON'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from xgw import config, marknet
from xgw.freepool import wan_epoch

cfg, _warnings = config.load(Path("/etc/xgw/config.toml"))
mark = cfg.capture.mark_bypass
if not marknet.mark_usable(mark):
    print("R39_PUBLIC_WAN_HOST=NOT_RUN_MARK")
    raise SystemExit
before = wan_epoch.route_identity(cfg, mark)
if before is None:
    print("R39_PUBLIC_WAN_HOST=NOT_RUN_ROUTE")
    raise SystemExit
key = wan_epoch.public_identity(cfg, mark, before)
after = wan_epoch.route_identity(cfg, mark)
if key and before == after:
    print("R39_PUBLIC_WAN_HOST=PASS")
else:
    print("R39_PUBLIC_WAN_HOST=NO_EVIDENCE")
PYTHON
  then
    cat "$D/wan.log"
  else
    printf 'R39_PUBLIC_WAN_HOST=FAIL\n'
    status=1
  fi
else
  printf 'R39_PUBLIC_WAN_HOST=NOT_RUN_ACCESS\n'
fi

host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R39_PUBLIC_WAN_HOST_FIELDS_MATCH\n'
else
  printf 'R39_PUBLIC_WAN_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- Указать отдельно `R39_PUBLIC_WAN_CONTRACTS` и `R39_PUBLIC_WAN_HOST`.
  Полный PASS этого ТЗ требует зелёных контрактов, подтверждения
  адреса на хосте и совпадения снимков штатных служб. При
  `NO_EVIDENCE` либо `NOT_RUN` указать причину в доступных пределах.
  Повторять запросы при отсутствии подтверждения не требуется.
- Контракты должны покрыть включение только для действующего пула
  по явной настройке, предел ответа, отсутствие немаркированной
  пробы, проверку привязки HTTPS-узла к тому же маршруту, отказ
  для приватного адреса, IPv6 и неоднозначного ответа. Смена адреса
  при неизменном маршруте, отказ от запоздавшего результата и
  переоткрытие состояния подтверждаются фикстурами.
- Живое переключение провайдера и публичного адреса, изменение
  штатной установки, хеши ядер и сутки M3 остаются открытыми.
- При любом исходе Flash публикует один обезличенный
  `docs/reports/<UTC>_freepool-r39-public-wan.md` обычным push
  в `docs/flash-proton-ui-manifest`. Указать SHA кандидата, SHA ТЗ
  и ОС. При расхождении ветки перенести только отчёт поверх
  актуальной вершины. Адреса, отпечатки, локальные логи и конфиги
  остаются локально. Системный код Flash не меняет.
