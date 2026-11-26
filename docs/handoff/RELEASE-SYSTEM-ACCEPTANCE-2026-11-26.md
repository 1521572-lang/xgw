# Ubuntu 24.04 · системная приёмка релизного архива XGW

**Кандидат — `264b7ba3400f040b327ce81067aae1540e9ab2c1`.** Flash выполняет один прогон на выделенной Ubuntu 24.04 amd64 с systemd, правом sudo и доступом к загрузке GitHub. Подходит одноразовая тестовая машина или выделенная VM с возможностью запуска `systemd-nspawn` и сетевых пространств имён. На рабочем шлюзе выполнять только отдельное ТЗ Proton.

Кандидат проверяется в контейнере существующего стенда. В контейнере работают настоящие systemd и NetworkManager, клиент LAN обращается к тестовому origin через Xray. Стенд проверяет чистую установку из архива, обновление прежней ревизии из того же архива, возврат к прежнему коду и удаление с сохранением пользовательских настроек.

## 1. Подготовка машины

Нужны Git, системный Python с pytest, systemd-container, NetworkManager, ufw, nftables, dnsmasq-base, sstp-client и зависимости [сборки](https://github.com/1521572-lang/xgw/blob/a29c20c9e3f3c490f893fe8c36dec772659c3dcd/packaging/README.md). Ядро Xray 26.10.21, `geoip.dat` и `geosite.dat` должны находиться в одном каталоге. Задать абсолютный `XGW_XRAY_BIN` к файлу с именем `xray`. Если доступна проверенная сборка sing-box 1.14.3, задать `XGW_SINGBOX_BIN`. Иначе в отчёте указать, что проверена конфигурация с Xray. При отсутствии выделенной машины или зависимостей запросить доступ и записать блокер.

## 2. Получение кандидата и прогон

Команды выполнять подряд в Bash из доверенного клона XGW. Входной комплект и архив проверяются по SHA-256. [Git bundle](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-p1-release-system.bundle)

```bash
set -euo pipefail
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
test "$(uname -m)" = x86_64
test "$(id -u)" != 0
test -d /run/systemd/system
test ! -e /opt/xgw
test ! -e /usr/local/bin/xgw
for tool in systemd-nspawn machinectl nsenter ip nft nmcli ufw dnsmasq sstpc gcc make pkg-config; do
    command -v "$tool" >/dev/null
done
/usr/bin/python3 -m pytest --version
case "${XGW_XRAY_BIN:?укажите абсолютный путь}" in
    /*/xray) test -x "$XGW_XRAY_BIN" ;;
    *) printf '%s\n' 'Нужен абсолютный путь к исполняемому файлу xray' >&2; exit 1 ;;
esac
test -s "$(dirname "$XGW_XRAY_BIN")/geoip.dat"
test -s "$(dirname "$XGW_XRAY_BIN")/geosite.dat"
sudo -v
if sudo -n machinectl show xgwm >/dev/null 2>&1 ||
   ip netns list | awk '{print $1}' | grep -Ex 'xgwm-(inet|lan)' ||
   ip link show dev xgwm-wan >/dev/null 2>&1 ||
   ip link show dev xgwm-lan >/dev/null 2>&1; then
    printf '%s\n' 'Имена ресурсов стенда уже заняты' >&2
    exit 1
fi
repo=$(git rev-parse --show-toplevel)
candidate=264b7ba3400f040b327ce81067aae1540e9ab2c1
previous=2c98b289f6de2dfbef8c865820b4f2f0c1529df9
umask 077
d=$(mktemp -d)
bundle="$d/release-system.bundle"
git -C "$repo" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$repo" show FETCH_HEAD:docs/handoff/artifacts/xgw-p1-release-system.bundle >"$bundle"
printf '%s  %s\n' '1191f2abe359f93a3528823d2e46adb2a195852daa60372fd8926a602f1b43a1' "$bundle" | sha256sum --check -
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
sudo env "PYTHONPATH=$d/src/src:$d/src" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    "XGW_XRAY_BIN=$XGW_XRAY_BIN" "XGW_SINGBOX_BIN=${XGW_SINGBOX_BIN:-}" \
    "XGW_MACHINE_DIR=$d/machine" "XGW_TEST_PREVIOUS_SOURCE=$d/previous" \
    "XGW_TEST_RELEASE_ARCHIVE=${archives[0]}" \
    /usr/bin/python3 -m pytest -o addopts= -rs -s --tb=short \
    tests/stand/test_machine.py -k release_archive_install_upgrade_and_restore \
    2>&1 | tee "$XGW_ACCEPT_LOG"
grep -Fx RELEASE_FRESH_OK "$XGW_ACCEPT_LOG"
grep -Fx RELEASE_UPGRADE_OK "$XGW_ACCEPT_LOG"
grep -Fx RELEASE_RESTORE_OK "$XGW_ACCEPT_LOG"
grep -Fx RELEASE_REMOVAL_OK "$XGW_ACCEPT_LOG"
```

## 3. Критерии и отчёт

| Метка | Что проверено |
|---|---|
| `RELEASE_FRESH_OK` | Чистая установка из tar.gz. Службы активны, LAN достигает тестового origin через VPN, GUI совпадает с манифестом и исходными файлами, все обязательные юниты совпадают с архивом. Бинарный комплект проходит проверку целостности, режим off. |
| `RELEASE_UPGRADE_OK` | Предыдущая ревизия `2c98b28` обновлена из архива. Работают службы и LAN. Байты `config.toml` и `panel.json` совпадают с исходными. |
| `RELEASE_RESTORE_OK` | Переустановка прежней ревизии вернула прежний код. Настройки, службы и маршрутизация клиента работают. |
| `RELEASE_REMOVAL_OK` | Удаление вернуло исходные профили, службы, правила и маршруты временной системы. Пользовательские файлы конфигурации сохранены. |

Если сборка, подготовка или контейнер не стартуют, указать последний выполненный этап и конкретную ошибку. Для PASS нужны `1 passed` и все четыре метки. Цикл установки и восстановления рабочего шлюза этот прогон не затрагивает. При любом исходе опубликовать обезличенный `docs/reports/<UTC>_release-system-acceptance.md` в ветке `docs/flash-proton-ui-manifest` с SHA кандидата, ОС, использованными версиями ядер, результатами и состоянием ресурсов стенда после выхода.
