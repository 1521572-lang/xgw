# ThinkCentre · параметры замера скорости FreePool R39

Ubuntu 24.04 LTS. Кандидат `3ae948447453be70e975e60eb2d5ed3d7cd47d14`. Дополнение к
[повтору F16 и проверке WAN](FREEPOOL-F16-R39-2026-11-26.md). У этого
прохода свой отчёт. Итоги F16 и проверки реального WAN берутся из
предыдущего ТЗ.

Flash сама запускает команды. При недоступности терминала запросить
доступ. Прогон использует временный каталог и локальный тестовый HTTP
сервер на loopback, а операции пула выполняет на фикстурах. Рабочие
подписки, настройки и служебные процессы для прогона не нужны.
[Бандл кандидата](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-probe-parameters.bundle)

## Прогон

Выполнить из полного клона с базой `9e4c025efb5404086ae601f3dc535a9e881521dd`.
Для отдельного окружения pytest задать `XGW_TEST_PYTHON`.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=3ae948447453be70e975e60eb2d5ed3d7cd47d14
D=$(mktemp -d "$HOME/xgw-freepool-r39-probe.XXXXXXXX")
TEST_PY=/usr/bin/python3
if [[ -v XGW_TEST_PYTHON ]]; then TEST_PY=$XGW_TEST_PYTHON; fi
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-probe-parameters.bundle >"$D/code.bundle"
printf '%s  %s\n' '001c0ef733655a37de1034f5ecfe5fcaf4c986266b4d8fadc0f293c6cdc7ca03' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests pyproject.toml | tar -x -C "$D/tree"

host_fields() {
  systemctl show --property=ActiveState,MainPID xgw.service xgw-xray.service xgw-singbox.service
}
host_fields >"$D/before.txt"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"
status=0
if timeout -k 5 150 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_speed.py tests/test_freepool_traffic.py tests/test_freepool_wan_epoch.py \
    >"$D/contracts.log" 2>&1; then
  printf 'R39_PROBE_CONTRACTS=PASS\n'
else
  printf 'R39_PROBE_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 25 "$D/contracts.log"
host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R39_PROBE_HOST_FIELDS_MATCH\n'
else
  printf 'R39_PROBE_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- Для `R39_PROBE_PARAMETERS=PASS` нужны зелёные тесты и совпадение полей
  служб. В отчёте указать число тестов и подтвердить, что изменения
  основного или запасного URL, пределы байтов и времени и User-Agent
  меняют отпечаток. Интервал проверки и выдержка закрепления его
  сохраняют. Основной и запасной адреса проверяются также loopback-запросами.
- Старый замер без отпечатка и замер с несовпадающими параметрами
  исключаются из сводки и выбора. Закрепление живого участника сохраняется.
  При смене параметров во время измерения учитываются байты, а скорость
  не сохраняется.
- Пользовательский трафик, смена WAN, публичная идентичность и отпечатки
  ядер в этом проходе `NOT_RUN`. Общее состояние R39 указать по двум
  независимым отчётам, когда оба опубликованы.
- При любом исходе Flash публикует один обезличенный
  `docs/reports/<UTC>_freepool-r39-probe-parameters.md` в
  `docs/flash-proton-ui-manifest` обычным push. Указать SHA задания и
  кандидата, ОС и этап с причиной, если он не пройден. При расхождении
  ветки перенести только отчёт поверх актуальной вершины. Полные журналы
  и содержимое временного каталога остаются локально. Системный код
  Flash не меняет.
