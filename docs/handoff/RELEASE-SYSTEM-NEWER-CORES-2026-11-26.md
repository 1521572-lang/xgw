# Ubuntu 24.04 · системная приёмка XGW с более новыми ядрами

**Кандидат — `eb4122ad04456eb85b87da9a59200d05a9829f73`.** Базовый прогон с Xray 26.10.21 уже прошёл все четыре фазы. Этот повтор проверяет совместимость архива с Xray 26.11.9 или установленным более новым выпуском без скачивания другого Xray из контейнера. Если проверяется sing-box, также записать его фактическую версию. [Базовый отчёт](https://github.com/1521572-lang/xgw/blob/3e87153ed1c487b93106cd0938aad286a144f16c/docs/reports/2026-11-26T092052Z_release-system-acceptance.md)

Flash выполняет прогон на выделенной Ubuntu 24.04 amd64 с systemd и sudo. На рабочем ThinkCentre запускать стенд в отдельно согласованное окно, установив `XGW_GATEWAY_TEST_APPROVED=1`. Рабочие бинарники используются как источник копий. Для новых версий стенд воспроизводит запись о приёмке только в изолированном корне контейнера и сверяет бинарники после каждой установки. Приёмка стенда проверяет запуск ядер и трафик через них по сценарию Xray. Состояние приёмки ядер на хосте остаётся за штатным механизмом XGW.

## 1. Подготовка машины

Нужны Git, системный Python с pytest, systemd-container, NetworkManager, ufw, nftables, dnsmasq-base, sstp-client и зависимости сборки. На ThinkCentre по умолчанию читается `/opt/xgw/xray/xray` вместе с `geoip.dat` и `geosite.dat`. При другом расположении задать абсолютный `XGW_XRAY_BIN`. Для дополнительной проверки sing-box задать абсолютный `XGW_SINGBOX_BIN`, например `/opt/xgw/sing-box/sing-box`. Версии и права файлов проверяются при подготовке временных копий до запуска контейнера. Ошибку окружения или доступа указать в отчёте, сохранив выполненные результаты.

## 2. Получение кандидата и прогон

Команды выполнять подряд в Bash из доверенного клона XGW. Входной комплект и архив проверяются по SHA-256. [Git bundle](https://github.com/1521572-lang/xgw/blob/docs/flash-proton-ui-manifest/docs/handoff/artifacts/xgw-p1-release-newer-cores.bundle)

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
if [ -n "${XGW_SINGBOX_BIN:-}" ]; then
    case "$XGW_SINGBOX_BIN" in
        /*/sing-box) sudo -n test -x "$XGW_SINGBOX_BIN" ;;
        *) printf '%s\n' 'Нужен абсолютный путь к исполняемому файлу sing-box' >&2; exit 1 ;;
    esac
fi
if sudo -n machinectl show xgwm >/dev/null 2>&1 ||
   ip netns list | awk '{print $1}' | grep -Ex 'xgwm-(inet|lan)' ||
   ip link show dev xgwm-wan >/dev/null 2>&1 ||
   ip link show dev xgwm-lan >/dev/null 2>&1; then
    printf '%s\n' 'Имена ресурсов стенда уже заняты' >&2
    exit 1
fi
repo=$(git rev-parse --show-toplevel)
candidate=eb4122ad04456eb85b87da9a59200d05a9829f73
previous=2c98b289f6de2dfbef8c865820b4f2f0c1529df9
umask 077
d=$(mktemp -d "$HOME/xgw-release-newer-cores.XXXXXXXX")
bundle="$d/release-system.bundle"
git -C "$repo" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$repo" show FETCH_HEAD:docs/handoff/artifacts/xgw-p1-release-newer-cores.bundle >"$bundle"
printf '%s  %s\n' '18f30cdb5abbe3856767d5d11094ac54a7d00bf5c928516be4ed9483fbe93e5c' "$bundle" | sha256sum --check -
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
    "XGW_XRAY_BIN=$XGW_XRAY_BIN" "XGW_SINGBOX_BIN=${XGW_SINGBOX_BIN:-}" \
    "XGW_MACHINE_DIR=$d/machine" "XGW_TEST_PREVIOUS_SOURCE=$d/previous" \
    "XGW_TEST_RELEASE_ARCHIVE=${archives[0]}" XGW_TEST_ALLOW_NEWER_CORES=1 \
    /usr/bin/python3 -m pytest -o addopts= -rs -s --tb=short --basetemp="$d/pytest" \
    tests/stand/test_machine.py -k release_archive_install_upgrade_and_restore \
    2>&1 | tee "$XGW_ACCEPT_LOG"
grep -F 'RELEASE_CORE xray ' "$XGW_ACCEPT_LOG"
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
| `RELEASE_RESTORE_OK` | Переустановка прежней ревизии вернула прежний код. Настройки, службы и маршрутизация клиента работают. |
| `RELEASE_REMOVAL_OK` | Удаление вернуло исходные профили, службы, правила и маршруты временной системы. Пользовательские файлы конфигурации сохранены. |

Для PASS нужны `1 passed`, все четыре метки и строка `RELEASE_CORE xray` с фактическим выпуском новее базового 26.10.21. При успешном прогоне с базовой версией оставить проверку нового Xray как `NOT_RUN`. Для sing-box указать фактическую версию или `NOT_RUN`. После выхода проверить отсутствие `xgwm`, двух netns, двух veth и монтирований стенда. На рабочем ThinkCentre дополнительно сверить версии и хеши хостовых ядер и конфигураций до и после, состояние служб и обычный HTTPS через VPN. При любом исходе опубликовать обезличенный `docs/reports/<UTC>_release-system-newer-cores.md` в ветке `docs/flash-proton-ui-manifest` с SHA, версиями, метками, ошибками и итогом очистки.
