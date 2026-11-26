# ThinkCentre · полный идентификатор моста FreePool R39

Ubuntu 24.04 LTS. Кандидат `ca36f536c898fcc90d845b9638832a4b1bec0c17`. В первом ТЗ исходный
loopback с 32 hex завершился ошибкой. Flash успешно повторила его
с 8 hex. Проверка кода показала, что FreePool пишет 32 hex штатно.
Исправленный кандидат читает обе длины.
[Отчёт первого прогона](https://github.com/1521572-lang/xgw/blob/da0837b55a0abf49ec1b6fc28b775466e7570f10/docs/reports/2026-11-26T175047Z_freepool-r39-singbox-context.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-bridge-id.bundle)

Flash сама запускает технический прогон. При недоступном терминале
запросить доступ. Использовать уже установленные Xray и sing-box,
зафиксировать их версии. Loopback использует два непривилегированных
процесса и приватный локальный HTTP-источник. Штатные службы,
подписки и конфигурация в сценарии не используются.

## Прогон

От обычного пользователя из полного клона с базой
`9e4c025efb5404086ae601f3dc535a9e881521dd`. При необходимости задать
пути через `XGW_TEST_PYTHON`, `XGW_TEST_XRAY`, `XGW_TEST_SINGBOX`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=ca36f536c898fcc90d845b9638832a4b1bec0c17
PREV=7ae63fabe8f21128a8bb5ae15c81d2c031362c69
D=$(mktemp -d /tmp/xgw-r39-id.XXXXXXXX)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-bridge-id.bundle >"$D/code.bundle"
printf '%s  %s\n' 'd0df05a8f15921a7adffc0c63f4caa48eb330853c26bccaad1c0a573e38c4b95' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests packaging pyproject.toml | tar -x -C "$D/tree"

# Исходная 32-символьная фикстура извлекается без изменений из закреплённого ТЗ.
git -C "$REPO" show "$PREV:docs/handoff/FREEPOOL-R39-SINGBOX-CONTEXT-2026-11-26.md" >"$D/previous.md"
"$PY" -B - "$D" <<'PYTHON'
import sys
from pathlib import Path

root = Path(sys.argv[1])
doc = (root / "previous.md").read_text(encoding="utf-8")
before, marker, rest = doc.partition("<<'PYTHON'\n")
assert before and marker and doc.count(marker) == 1
script, end_marker, _ = rest.partition("\nPYTHON\n")
assert end_marker and 'fingerprint = "a" * 32' in script
assert 'print("R39_BRIDGE_LOOPBACK=PASS")' in script
compile(script, "fixed-source-loopback", "exec")
(root / "loopback.py").write_text(script + "\n", encoding="utf-8")
PYTHON

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
}
host_fields >"$D/before.txt"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"
status=0
if timeout -k 5 160 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_freepool_traffic.py tests/test_singbox.py tests/test_singbox_generations.py \
    tests/test_daemon.py::test_pool_region_reload_only_prioritizes_rebuild_when_pool_carries_traffic \
    >"$D/contracts.log" 2>&1; then
  printf 'R39_BRIDGE_ID_CONTRACTS=PASS\n'
else
  printf 'R39_BRIDGE_ID_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 20 "$D/contracts.log"

if [[ -x "$XRAY" && -x "$SINGBOX" ]]; then
  if timeout -k 2 10 "$XRAY" version >"$D/xray-version.txt" 2>&1 &&
     timeout -k 2 10 "$SINGBOX" version >"$D/singbox-version.txt" 2>&1; then
    head -n 1 "$D/xray-version.txt" "$D/singbox-version.txt"
  else
    printf 'R39_BRIDGE_ID_VERSIONS=FAIL\n'
    status=1
  fi
  if timeout -k 5 35 "$PY" -B -P "$D/loopback.py" "$D" "$XRAY" "$SINGBOX" \
      >"$D/loopback.log" 2>&1; then
    cat "$D/loopback.log"
    printf 'R39_BRIDGE_ID_32_LOOPBACK=PASS\n'
  else
    printf 'R39_BRIDGE_ID_32_LOOPBACK=FAIL\n'
    status=1
  fi
else
  printf 'R39_BRIDGE_ID_32_LOOPBACK=NOT_RUN\n'
fi

host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R39_BRIDGE_ID_HOST_FIELDS_MATCH\n'
else
  printf 'R39_BRIDGE_ID_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- `R39_BRIDGE_FULL_ID=PASS` требует зелёных контрактов,
  `R39_BRIDGE_LOOPBACK=PASS` и `R39_BRIDGE_ID_32_LOOPBACK=PASS`,
  версий обоих ядер и совпадения полей служб. Если ядро недоступно,
  зафиксировать `NOT_RUN` с причиной.
- В контрактах указать обе длины идентификатора, сохранение порта при
  повторной сборке FreePool и раздельные порты при смене поколения.
  В loopback проверить отсутствие моста при остановленном sing-box,
  ответ до и после перезапуска, изменение ключа моста и стабильность ключа
  прямого выхода. Сохранять 32 символа в исходном сценарии.
- Рабочее переключение поколений blue/green и суточный M3 в этом
  проходе открыты. При любом исходе Flash публикует один обезличенный
  `docs/reports/<UTC>_freepool-r39-bridge-id.md` обычным push в
  `docs/flash-proton-ui-manifest`. Указать SHA кандидата и задания.
  При расхождении ветки перенести только отчёт. Пароли, отпечатки,
  конфиги, PID и журналы оставить локально. Системный код Flash не меняет.
