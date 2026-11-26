# Ubuntu 24.04 · системная приёмка архива с sing-box и трафиком LAN

**Кандидат — `2b6da9261b07f1c9f1f8c86052d15d0ade18593a`.** Flash проверяет выпуск с обоими ядрами. Xray 26.11.9 уже прошёл чистую установку, обновление, возврат и удаление. В том отчёте путь через sing-box 1.14.4 остался `NOT_RUN`. Этот прогон проверяет системную службу и маршрут отдельного тестового LAN-клиента через мост Xray → sing-box → Hysteria2. [Отчёт с Xray 26.11.9](https://github.com/1521572-lang/xgw/blob/1c35a8b5f67e14706542898e839394ebe6c87aa8/docs/reports/2026-11-26T094814Z_release-system-newer-cores.md)

Выполняй на выделенной Ubuntu 24.04 amd64 либо в согласованное окно на ThinkCentre с `XGW_GATEWAY_TEST_APPROVED=1`. Перед запуском на рабочем шлюзе локально зафиксируй хеши обоих рабочих бинарников, `config.toml`, `panel.json`, состояния служб и штатный VPN-контроль. Стенд использует копии ядер и отдельное сетевое пространство имён. Тестовый выход Hysteria2 и origin создаются внутри стенда.

## 1. Подготовка машины

Нужны Git, системный Python с pytest, systemd-container, NetworkManager, ufw, nftables, dnsmasq-base, sstp-client и зависимости сборки. По умолчанию читаются `/opt/xgw/xray/xray` с `geoip.dat` и `geosite.dat` и `/opt/xgw/sing-box/sing-box`. При другом расположении задай абсолютные `XGW_XRAY_BIN` и `XGW_SINGBOX_BIN`. Используй установленные на ThinkCentre Xray 26.11.9 и sing-box 1.14.4 или более новые установленные выпуски. Если одного ядра нет, зафиксируй `NOT_RUN` и причину.

## 2. Получение кандидата и прогон

Команды выполнять подряд в Bash из доверенного клона XGW. Входной комплект и архив проверяются по SHA-256. [Git bundle](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-p1-release-singbox-lan.bundle)

```bash
set -euo pipefail
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
test "$(uname -m)" = x86_64
test "$(id -u)" != 0
test -d /run/systemd/system
if [ -e /opt/xgw ] || [ -e /usr/local/bin/xgw ]; then
    test "${XGW_GATEWAY_TEST_APPROVED:-0}" = 1
fi
for tool in systemd-nspawn machinectl nsenter ip nft nmcli ufw dnsmasq sstpc gcc make pkg-config; do
    command -v "$tool" >/dev/null
done
/usr/bin/python3 -m pytest --version
if ! sudo -n true 2>/dev/null; then sudo -v; fi
XGW_XRAY_BIN=${XGW_XRAY_BIN:-/opt/xgw/xray/xray}
case "$XGW_XRAY_BIN" in
    /*/xray) sudo -n test -x "$XGW_XRAY_BIN" ;;
    *) printf '%s\n' 'Нужен абсолютный путь к исполняемому файлу xray' >&2; exit 1 ;;
esac
sudo -n test -s "$(dirname "$XGW_XRAY_BIN")/geoip.dat"
sudo -n test -s "$(dirname "$XGW_XRAY_BIN")/geosite.dat"
XGW_SINGBOX_BIN=${XGW_SINGBOX_BIN:-/opt/xgw/sing-box/sing-box}
case "$XGW_SINGBOX_BIN" in
    /*/sing-box) sudo -n test -x "$XGW_SINGBOX_BIN" ;;
    *) printf '%s\n' 'Нужен абсолютный путь к исполняемому файлу sing-box' >&2; exit 1 ;;
esac
if sudo -n machinectl show xgwm >/dev/null 2>&1 ||
   ip netns list | awk '{print $1}' | grep -Ex 'xgwm-(inet|lan)' ||
   ip link show dev xgwm-wan >/dev/null 2>&1 ||
   ip link show dev xgwm-lan >/dev/null 2>&1; then
    printf '%s\n' 'Имена ресурсов стенда уже заняты' >&2
    exit 1
fi
repo=$(git rev-parse --show-toplevel)
candidate=2b6da9261b07f1c9f1f8c86052d15d0ade18593a
previous=2c98b289f6de2dfbef8c865820b4f2f0c1529df9
umask 077
d=$(mktemp -d "$HOME/xgw-release-singbox-lan.XXXXXXXX")
bundle="$d/release-system.bundle"
git -C "$repo" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$repo" show FETCH_HEAD:docs/handoff/artifacts/xgw-p1-release-singbox-lan.bundle >"$bundle"
printf '%s  %s\n' 'a632c8e82c23618647f3aab83db3cfbd122e971928def717112c2684cbd0814a' "$bundle" | sha256sum --check -
git -C "$repo" bundle verify "$bundle"
git -C "$repo" fetch "$bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
test "$(git -C "$repo" rev-parse FETCH_HEAD)" = "$candidate"
mkdir "$d/src" "$d/previous" "$d/dist"
git -C "$repo" archive "$candidate" | tar -x -C "$d/src"
git -C "$repo" archive "$previous" src packaging config.example.toml | tar -x -C "$d/previous"
cd "$d/src"
/usr/bin/python3 packaging/build_release.py --output "$d/dist" 2>&1 | tee "$d/build.log"
(cd "$d/dist" && sha256sum --check ./*.sha256)
archives=("$d/dist"/*.tar.gz)
test "${#archives[@]}" = 1
test -f "${archives[0]}"
XGW_ACCEPT_LOG="$d/system.log"
sudo -n env "PYTHONPATH=$d/src/src:$d/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    "XGW_XRAY_BIN=$XGW_XRAY_BIN" "XGW_SINGBOX_BIN=$XGW_SINGBOX_BIN" \
    "XGW_MACHINE_DIR=$d/machine" "XGW_TEST_PREVIOUS_SOURCE=$d/previous" \
    "XGW_TEST_RELEASE_ARCHIVE=${archives[0]}" XGW_TEST_ALLOW_NEWER_CORES=1 \
    /usr/bin/python3 -m pytest -o addopts= -rs -s --tb=short --basetemp="$d/pytest" \
    tests/stand/test_machine.py -k release_archive_install_upgrade_and_restore \
    2>&1 | tee "$XGW_ACCEPT_LOG"
grep -F 'RELEASE_CORE xray ' "$XGW_ACCEPT_LOG"
grep -F 'RELEASE_CORE sing-box ' "$XGW_ACCEPT_LOG"
grep -F RELEASE_LAN_SINGBOX_OK "$XGW_ACCEPT_LOG"
grep -F RELEASE_FRESH_OK "$XGW_ACCEPT_LOG"
grep -F RELEASE_UPGRADE_OK "$XGW_ACCEPT_LOG"
grep -F RELEASE_RESTORE_OK "$XGW_ACCEPT_LOG"
grep -F RELEASE_REMOVAL_OK "$XGW_ACCEPT_LOG"
```

## 3. Критерии и отчёт

| Метка | Что проверено |
|---|---|
| `RELEASE_FRESH_OK` | Чистая установка из tar.gz. Службы активны, LAN достигает тестового origin через VPN, GUI совпадает с манифестом и исходными файлами, все обязательные юниты совпадают с архивом. Бинарный комплект проходит проверку целостности, режим off. |
| `RELEASE_UPGRADE_OK` | Предыдущая ревизия `2c98b28` обновлена из архива. Работают службы и LAN. Байты `config.toml` и `panel.json` совпадают с исходными. |
| `RELEASE_LAN_SINGBOX_OK` | Запрос от отдельного клиента LAN достиг тестового origin через единственного VPN-участника. Применённые конфиги связывают исходящий SOCKS Xray, локальный вход sing-box и выход Hysteria2. Служба работает с выделенным UID, пустыми наборами capabilities и `NoNewPrivs=1`. |
| `RELEASE_RESTORE_OK` | Переустановка прежней ревизии вернула прежний код. Настройки, службы и маршрутизация клиента работают. |
| `RELEASE_REMOVAL_OK` | Удаление вернуло исходные профили, службы, правила и маршруты временной системы. Пользовательские файлы конфигурации сохранены. |

Для PASS нужны `1 passed`, обе строки `RELEASE_CORE`, отдельная метка LAN через sing-box и все четыре метки системной приёмки. Укажи точный этап при сбое и сохрани журналы локально. После выхода проверь удаление машины, двух netns, двух veth и монтирований. На ThinkCentre повтори контроль рабочих файлов, служб и VPN. При любом исходе опубликуй обезличенный `docs/reports/<UTC>_release-system-singbox-lan.md` в ветке `docs/flash-proton-ui-manifest`. HTTPS с отдельного физического клиента через рабочий мост остаётся отдельным пунктом ROADMAP.
