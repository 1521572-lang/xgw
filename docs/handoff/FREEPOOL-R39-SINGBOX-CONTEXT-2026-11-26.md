# ThinkCentre · поколение sing-box и мост FreePool R39

Ubuntu 24.04 LTS. Кандидат `e43f45ac28642ab549d93504ad294b80906f5db8`. Проверить применимость
замера FreePool через мост к активному sing-box.
[Отчёт поколения Xray](https://github.com/1521572-lang/xgw/blob/bd978da82f3995efa54f2ab44a72998de2879393/docs/reports/2026-11-26T173610Z_freepool-r39-xray-generation.md) · [Бандл](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-freepool-r39-singbox-context.bundle)

Flash выполняет команды сама. При недоступности терминала запросить
доступ. Упражнение использует установленные версии ядер, без привязки
к номеру версии. Оно запускает только два собственных непривилегированных
процесса и HTTP-источник в приватном временном каталоге. Все входы
слушают loopback с временными паролями для прокси. Маршрут sing-box
разрешает только адрес и порт тестового HTTP-источника. Штатные
конфиги и подписки для проверки не нужны.

## Прогон

Выполнить от обычного пользователя из полного клона с базой
`9e4c025efb5404086ae601f3dc535a9e881521dd`. Пути к тестовому Python,
Xray и sing-box задаются через `XGW_TEST_PYTHON`, `XGW_TEST_XRAY`
и `XGW_TEST_SINGBOX` при необходимости.

```bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=e43f45ac28642ab549d93504ad294b80906f5db8
D=$(mktemp -d /tmp/xgw-r39-bridge.XXXXXXXX)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
printf 'PRIVATE_ARTIFACTS %s\nOS %s\nCANDIDATE %s\n' "$D" "$PRETTY_NAME" "$CODE"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show FETCH_HEAD:docs/handoff/artifacts/xgw-freepool-r39-singbox-context.bundle >"$D/code.bundle"
printf '%s  %s\n' '1f4b60de6d0809560d3b68862bc2d94eb3d88d31315fddd2bf0019c5e8c872a1' "$D/code.bundle" | sha256sum --check -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$REPO" rev-parse FETCH_HEAD)" = "$CODE"
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src tests packaging pyproject.toml | tar -x -C "$D/tree"

host_fields() {
  systemctl show --property=ActiveState,MainPID \
    xgw.service xgw-xray.service xgw-singbox.service
}
host_fields >"$D/before.txt"
export PYTHONPATH="$D/tree/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS=
cd "$D/tree"
status=0
if timeout -k 5 160 "$TEST_PY" -B -m pytest -o addopts= -q -p no:cacheprovider \
    tests/test_freepool_traffic.py tests/test_singbox.py tests/test_singbox_generations.py \
    tests/test_daemon.py::test_pool_region_reload_only_prioritizes_rebuild_when_pool_carries_traffic \
    >"$D/contracts.log" 2>&1; then
  printf 'R39_BRIDGE_CONTRACTS=PASS\n'
else
  printf 'R39_BRIDGE_CONTRACTS=FAIL\n'
  status=1
fi
tail -n 20 "$D/contracts.log"

if [[ -x "$XRAY" && -x "$SINGBOX" ]]; then
  if timeout -k 2 10 "$XRAY" version >"$D/xray-version.txt" 2>&1 &&
     timeout -k 2 10 "$SINGBOX" version >"$D/singbox-version.txt" 2>&1; then
    head -n 1 "$D/xray-version.txt" "$D/singbox-version.txt"
  else
    printf 'R39_BRIDGE_VERSIONS=FAIL\n'
    status=1
  fi
  if timeout -k 5 35 "$PY" -B -P - "$D" "$XRAY" "$SINGBOX" >"$D/loopback.log" 2>&1 <<'PYTHON'
import http.server
import secrets
import socket
import sys
import threading
from pathlib import Path

from xgw.apply.singbox import SingboxCore
from xgw.config import Config
from xgw.generator import builder, singbox
from xgw.paths import Paths, atomic_write_json
from xgw.watch.checks import http_get_via_proxy
from xgw.xraycore.service import ProcessXrayService

local = "127.0.0.1"
body = b"xgw-r39-bridge\n"
run_dir, xray_binary, sb_binary = map(Path, sys.argv[1:])
paths = Paths(root=run_dir / "control")
paths.ensure()
fingerprint = "a" * 32
tag_a, tag_b = "pool-de-aaaa", "pool-de-bbbb"
bridge_in = singbox.tag_in(fingerprint, "d")
bridge_out = singbox.tag_out(fingerprint, "d")
bridge_password, probe_password = (secrets.token_hex(16) for _ in range(2))


class Origin(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


with http.server.HTTPServer((local, 0), Origin) as origin:
    destination = origin.server_address[1]
    with socket.socket() as reservation, socket.socket() as other:
        reservation.bind((local, 0))
        other.bind((local, 0))
        bridge_port, probe_port = reservation.getsockname()[1], other.getsockname()[1]
    thread = threading.Thread(target=origin.serve_forever, daemon=True)
    thread.start()
    sb_cfg = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "socks", "tag": bridge_in, "listen": local, "listen_port": bridge_port,
            "users": [{"username": f"{singbox.BRIDGE_USER}-d", "password": bridge_password}],
        }],
        "outbounds": [{"type": "direct", "tag": bridge_out}],
        "route": {"rules": [
            {"inbound": [bridge_in], "ip_cidr": ["127.0.0.1/32"], "port": [destination],
             "action": "route", "outbound": bridge_out},
            {"action": "reject"},
        ]},
    }
    xray_cfg = {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": "probe-de-aaaa", "protocol": "http", "listen": local, "port": probe_port,
            "settings": {"accounts": [{"user": "probe", "pass": probe_password}]},
        }],
        "outbounds": [
            {"tag": tag_a, **singbox.bridge_outbound(bridge_port, "d", bridge_password)},
            {"tag": tag_b, "protocol": "freedom"},
        ],
        "routing": {"rules": [
            {"type": "field", "inboundTag": ["probe-de-aaaa"], "outboundTag": tag_a},
        ]},
    }
    atomic_write_json(paths.xray_config_file, xray_cfg)
    atomic_write_json(paths.singbox_config_file, sb_cfg)
    sb = ProcessXrayService(sb_binary, paths.singbox_config_file)
    xray = ProcessXrayService(xray_binary, paths.xray_config_file)
    core = SingboxCore(Config(), paths, sb, validator=lambda _: (True, ""))

    def keys():
        return builder.pool_outbound_keys(xray_cfg, bridge_contexts=core.bridge_measurement_contexts)

    def fetch():
        return http_get_via_proxy(
            local, probe_port, f"http://{local}:{destination}/fixture", timeout=1, silence=1,
            max_total=3, proxy_user="probe", proxy_pass=probe_password,
        )

    try:
        xray.start()
        assert set(keys()) == {tag_b} and not fetch().ok
        sb.start()
        first = keys()
        assert set(first) == {tag_a, tag_b} and keys() == first
        served = fetch()
        assert served.ok and served.downloaded == len(body)
        sb.stop()
        assert keys() == {tag_b: first[tag_b]} and not fetch().ok
        sb.start()
        second = keys()
        assert set(second) == {tag_a, tag_b}
        assert second[tag_a] != first[tag_a] and second[tag_b] == first[tag_b]
        served = fetch()
        assert served.ok and served.downloaded == len(body)
    finally:
        xray.stop()
        sb.stop()
        origin.shutdown()
        thread.join()
print("R39_BRIDGE_LOOPBACK=PASS")
PYTHON
  then
    cat "$D/loopback.log"
  else
    printf 'R39_BRIDGE_LOOPBACK=FAIL\n'
    status=1
  fi
else
  printf 'R39_BRIDGE_LOOPBACK=NOT_RUN\n'
fi

host_fields >"$D/after.txt"
if cmp -s "$D/before.txt" "$D/after.txt"; then
  printf 'R39_BRIDGE_HOST_FIELDS_MATCH\n'
else
  printf 'R39_BRIDGE_HOST_FIELDS_DIFFER\n'
  status=1
fi
exit "$status"
BASH
```

## Приёмка и публикация

- `R39_SINGBOX_CONTEXT=PASS` требует зелёных контрактов, загрузки до и
  после перезапуска отдельного sing-box, отказа при остановленном ядре
  и совпадения полей штатных служб. При недоступности ядер отразить
  `NOT_RUN` для loopback с причиной. Указать версии и число тестов.
- Контракты проверяют соответствие активного слота, его конфигурации
  и порта моста, пропуск при занятой блокировке применения, исключение
  неподтверждённого моста и сохранение замера
  прямого выхода Xray. При смене контекста во время пробы показать
  учёт байтов без сохранения скорости.
- Указать область приёмки. Проверка поколений blue/green выполнена
  контрактами. Живой прогон использует отдельные процессы и один
  loopback-мост. Переключение рабочих поколений, хеши бинарников,
  публичный WAN и сутки M3 остаются открытыми.
- При любом исходе Flash публикует один обезличенный
  `docs/reports/<UTC>_freepool-r39-singbox-context.md` в ветке
  `docs/flash-proton-ui-manifest` обычным push. Указать SHA задания
  и кандидата. При расхождении ветки перенести только отчёт поверх
  актуальной вершины. Пароли, отпечатки, конфиги, PID и полные
  журналы остаются локально. Системный код Flash не меняет.
