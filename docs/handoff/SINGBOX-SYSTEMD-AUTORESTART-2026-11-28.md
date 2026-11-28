# ThinkCentre · автоматический перезапуск временного sing-box

Ubuntu 24.04 LTS amd64. Кандидат `88287ae0a17856c0c4ff75b7dd8832abba140e4c`. В проверке `7927a8a` оба перезапуска по команде прошли, 221 регрессионная проверка прошла. В этом задании новый процесс запускает сам менеджер systemd по штатной политике `Restart=always`. Проверить оба порядка относительно коммита API. [Предыдущий отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/4eeafc2067536f59db0aaff7ce32aa87758ed8ef/docs/reports/2026-11-28T000314Z_singbox-systemd-identity.md)

Flash сама выполняет команды и публикует один обезличенный отчёт при любом исходе. Если терминал или разрешённый sudo недоступен, запросить доступ. Использовать установленные ядра. Временные юниты работают в отдельной сети только с `lo`. Менеджер ограничивает время работы временного green 18 секундами и допускает не более двух запусков в интервале 10 минут. Стенд дожидается срабатывания таймаута и проверяет счётчик запусков. Рабочие службы только читаются.

## 1. Команды

Из полного клона XGW выполнить блок. При нестандартном расположении ядер задать абсолютные `XGW_TEST_XRAY` и `XGW_TEST_SINGBOX`. `PRIVATE_ARTIFACTS`, `PRIVATE_SYSTEMD_ROOT` и строка `PRIVATE_UNITS` в журнале указывают на временные ресурсы. Два опыта используют разные сети и каталоги. Регрессии и штатное 300-секундное окно взяты из принятых отчётов.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=88287ae0a17856c0c4ff75b7dd8832abba140e4c
BUNDLE=docs/handoff/artifacts/xgw-singbox-systemd-autorestart.bundle
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '883fe5ca40bfb9a879d69e7e01974296987987098e0be1f5d703e8ccc4172dd8' "$D/code.bundle" | sha256sum --check --status -
git -C "$REPO" bundle verify "$D/code.bundle"
git -C "$REPO" fetch --no-tags "$D/code.bundle" refs/heads/feat/reproducible-proton-ui-and-manifest
[[ $(git -C "$REPO" rev-parse FETCH_HEAD) == "$CODE" ]]
mkdir "$D/tree"
git -C "$REPO" archive "$CODE" src packaging docs/helpers |
    tar -x -C "$D/tree"
cd "$D/tree"

run() {
    local label=$1 rc=0
    shift
    "$@" >"$D/$label.log" 2>&1 || rc=$?
    printf '%s=%s\n' "$label" "$rc" | tee -a "$D/status"
}

host_fields() {
    local unit fields
    for unit in xgw.service xgw-xray.service xgw-singbox.service \
                xgw-singbox-blue.service xgw-singbox-green.service; do
        fields=$(timeout -k 1 4 systemctl show "$unit" -p LoadState -p ActiveState -p MainPID) ||
            [[ "$fields" == *'LoadState=not-found'* ]] || return 1
        [[ "$fields" == *'LoadState='* && "$fields" == *'ActiveState='* && "$fields" == *'MainPID='* ]] ||
            return 1
        printf '%s\n%s\n' "$unit" "$fields"
    done
}

before=0
host_fields >"$D/host.before" 2>"$D/host.before.err" || before=$?
if [[ -x /usr/local/bin/xgw ]] && sudo -n true 2>/dev/null; then
    run HOST_STATUS sudo -n /usr/bin/timeout -k 2 12 /usr/local/bin/xgw singbox status
else
    echo 'HOST_STATUS=NOT_RUN missing launcher or sudo' | tee -a "$D/status"
fi
if [[ ! -x "$XRAY" || ! -x "$SINGBOX" ]] ||
   ! timeout -k 2 8 "$XRAY" version >"$D/xray-version.log" 2>&1 ||
   ! timeout -k 2 8 "$SINGBOX" version >"$D/singbox-version.log" 2>&1; then
    echo 'SYSTEMD=NOT_RUN missing or non-executable core' | tee -a "$D/status"
elif [[ ! -d /run/systemd/system ]] || ! getent passwd xgw-singbox >/dev/null ||
     ! getent group xgw-singbox >/dev/null; then
    echo 'SYSTEMD=NOT_RUN missing system manager or installed service identity' | tee -a "$D/status"
elif [[ ! -x /usr/bin/unshare ]] || ! command -v ip >/dev/null; then
    echo 'SYSTEMD=NOT_RUN missing unshare or ip' | tee -a "$D/status"
elif ! sudo -n true 2>/dev/null; then
    echo 'SYSTEMD=NOT_RUN sudo access unavailable' | tee -a "$D/status"
else
    for phase in before after; do
        LAB_ROOT="/opt/xgw-systemd-${D##*.}-$phase"
        label="AUTO_RESTART_${phase^^}"
        printf 'PRIVATE_SYSTEMD_ROOT %s %s\n' "$phase" "$LAB_ROOT"
        run "$label" sudo -n /usr/bin/timeout -s INT -k 20 80 /usr/bin/env -i \
            PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD:$PWD/src" \
            /usr/bin/python3 -B -P -m docs.helpers.singbox_systemd_handoff \
            "$LAB_ROOT" "$XRAY" "$SINGBOX" --restart-check "auto-$phase"
        grep -E '^SYSTEMD_[A-Z_]+=PASS( |$)' "$D/$label.log" || true
        if [[ ! -e $LAB_ROOT && ! -L $LAB_ROOT ]]; then
            printf '%s_ROOT_ABSENT=YES\n' "$label"
        else
            printf '%s_ROOT_ABSENT=NO\n' "$label"
        fi
    done
fi

after=0
host_fields >"$D/host.after" 2>"$D/host.after.err" || after=$?
if [[ $before == 0 && $after == 0 ]]; then
    if cmp -s "$D/host.before" "$D/host.after"; then echo HOST_FIELDS=MATCH; else echo HOST_FIELDS=DRIFT; fi
else
    echo HOST_FIELDS=UNKNOWN
fi
BASH
~~~

## 2. Что записать

| Метка | Критерий |
| --- | --- |
| `SYSTEMD_AUTO_RESTART` | В каждом сценарии временный green имел `Restart=always`. После истечения лимита новый запуск подтверждён, счётчик `NRestarts` вырос с 0 до 1. Песочница и сеть проверены для нового процесса. |
| `AUTO_RESTART_BEFORE`, `SYSTEMD_RESTART_BEFORE` | Green перезапустился до коммита. XGW отказал в переключении и снял кандидата. Прежний конфиг прочитан, старое и новое соединения через blue получают A. Запуск Xray сохранён. |
| `AUTO_RESTART_AFTER`, `SYSTEMD_RESTART_AFTER` | Green принят, `identity_ok=true`. После автостарта `identity_ok=null`, новый запрос через green получает B, старый поток через blue продолжает получать A. Запуск Xray сохранён. |
| `SYSTEMD_CLEAN`, `SYSTEMD_ROOT_CLEAN`, `HOST_FIELDS` | В обоих опытах временные юниты и Xray завершены, каталоги удалены. `LoadState`, `ActiveState`, `MainPID` пяти штатных юнитов совпали. |
| `HOST_STATUS` | Из читаемого штатным CLI состояния привести только активный слот, наличие `pending` и `draining`. Это предварительное наблюдение для будущего окна. При недоступности указать причину. |

Описать оба опыта независимо и указать последний подтверждённый этап при сбое. Рабочее переключение systemd, физический LAN и внешний трафик остаются отдельной приёмкой. Не публиковать содержимое приватных логов, имена временных юнитов или PID.

## 3. Автоматическая публикация

Включить SHA карточки и кандидата, версии Ubuntu, Python, pytest, Xray и sing-box, UTC и исходы фаз. Приватные пути, адреса, порты, PID, данные сокетов, конфиги и полные журналы оставить на ThinkCentre. Задать абсолютный путь к обезличенному Markdown в `REPORT_SRC`. Выполнить из полного клона при любом исходе.

~~~bash
(
  set -euo pipefail
  umask 077
  [[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
  ref=refs/heads/docs/flash-proton-ui-manifest
  repo=$(git rev-parse --show-toplevel)
  pub=$(mktemp -d)
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-systemd-autorestart.md
  export GIT_INDEX_FILE="$pub/index"
  blob=$(git -C "$repo" hash-object -w -- "$REPORT_SRC")
  local_ref=refs/xgw-report/$(basename "$pub")
  trap 'git -C "$repo" update-ref -d "$local_ref"' EXIT
  for i in 1 2 3; do
    git -C "$repo" fetch --quiet --no-tags --no-write-fetch-head origin "$ref:$local_ref"
    tip=$(git -C "$repo" rev-parse "$local_ref")
    if prev=$(git -C "$repo" rev-parse --verify "$tip:$file" 2>/dev/null); then
      [[ $prev == "$blob" ]] || exit 1
      printf 'PUBLISHED %s %s\n' "$tip" "$file"
      exit 0
    fi
    git -C "$repo" read-tree "$tip"
    git -C "$repo" update-index --add --cacheinfo "100644,$blob,$file"
    tree=$(git -C "$repo" write-tree)
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre automatic restart of temporary sing-box')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
