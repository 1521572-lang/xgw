# ThinkCentre · смена поколения sing-box в отдельной сети стенда

Ubuntu 24.04 LTS amd64. Кандидат `31d0de416f67ec8bd7ef02d969425c666d080f4d`. В R2 временный blue запустился из `/opt` и прошёл проверку песочницы. Первый обмен остановился на `ECONNREFUSED` при обращении служебного UID к фикстуре на loopback шлюза. В R3 фикстуры, тестовый Xray и оба временных sing-box используют общую отдельную сеть только с `lo`. У временных юнитов сохраняется `PrivateTmp=true`. [Отчёт R2](https://github.com/1521572-lang/xgw/blob/1efbe1e0b649b27bd374d27daaa275722c9f867f/docs/reports/2026-11-27T220401Z_singbox-systemd-handoff-r2.md)

Flash сама запускает команды и публикует обезличенный отчёт при любом исходе. Выполняется только системная фаза. Использовать установленные ядра. Если терминал или разрешённый sudo недоступен, запросить доступ. Если запуск отдельной сети запрещён, указать точную ошибку и закончить системную фазу. Защита, конфигурация сети и рабочие службы шлюза в проверке только наблюдаются.

## 1. Системная фаза

Из полного клона XGW выполнить блок. При нестандартном расположении ядер задать абсолютные `XGW_TEST_XRAY` и `XGW_TEST_SINGBOX`. `PRIVATE_ARTIFACTS`, `PRIVATE_SYSTEMD_ROOT` и строка `PRIVATE_UNITS` в журнале указывают на ресурсы этого запуска. Помощник создаёт временное сетевое пространство, сверяет, что оно отличается от исходного и содержит только `lo`, поднимает этот интерфейс и передаёт путь к пространству двум временным юнитам. На сетевом пространстве нет внешнего интерфейса, именованного подключения или маршрута к WAN.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=31d0de416f67ec8bd7ef02d969425c666d080f4d
BUNDLE=docs/handoff/artifacts/xgw-singbox-systemd-handoff-r3.bundle
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' '0cd990056824e202e48292c8612aa40cf3759703d9b42633c079a2aff6e195d9' "$D/code.bundle" | sha256sum --check --status -
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
    LAB_ROOT="/opt/xgw-systemd-${D##*.}"
    printf 'PRIVATE_SYSTEMD_ROOT %s\n' "$LAB_ROOT"
    run SYSTEMD sudo -n /usr/bin/timeout -s INT -k 20 395 /usr/bin/env -i \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin "PYTHONPATH=$PWD:$PWD/src" \
        /usr/bin/python3 -B -P -m docs.helpers.singbox_systemd_handoff \
        "$LAB_ROOT" "$XRAY" "$SINGBOX"
    grep -E '^SYSTEMD_[A-Z_]+=PASS( |$)' "$D/SYSTEMD.log" || true
    if [[ ! -e $LAB_ROOT && ! -L $LAB_ROOT ]]; then
        echo SYSTEMD_ROOT_ABSENT=YES
    else
        echo SYSTEMD_ROOT_ABSENT=NO
    fi
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
| `SYSTEMD_NETNS`, `SYSTEMD_LAYOUT` | Новая сеть отличается от исходной и содержит только loopback. Каталог стенда находится на исполняемом разделе под `/opt`. |
| `SYSTEMD_BLUE_POLICY`, `SYSTEMD_BLUE_DATA` | Blue запущен с рабочим UID, `PrivateTmp`, пустыми capabilities, `NoNewPrivs=1` и ссылкой на сеть стенда. Первый запрос через Xray и blue получает `Ax`. Если обмен сорвался, зафиксировать этап и категорию ошибки. |
| `SYSTEMD_GREEN_POLICY`, `SYSTEMD_HANDOFF` | Green прошёл ту же проверку ограничений и запрос через мост. После коммита API Xray сохранил запуск, новый поток получил B, старый продолжил получать A. |
| `SYSTEMD_GRACE`, `SYSTEMD_REAP` | Полное окно 300 секунд. Оба потока отвечают, после срока systemd подтверждает остановку blue, старый поток закрывается, green отвечает. Указать число выборок. |
| `SYSTEMD_CLEAN`, `SYSTEMD_ROOT_CLEAN`, `SYSTEMD_ROOT_ABSENT`, `HOST_FIELDS` | Оба временных юнита и тестовый Xray завершены, выделенный каталог удалён. Для пяти рабочих юнитов сверены `LoadState`, `ActiveState` и `MainPID`. |

Для `SYSTEMD=PASS` нужны код 0 и все метки системной фазы. При сбое укажи первый неподтверждённый этап и состояние очистки. Обычный переход и регрессии уже приняты первым отчётом. Внешний трафик, физический LAN и смена рабочих юнитов остаются отдельной приёмкой.

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
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-systemd-handoff-r3.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre systemd handoff in a private network namespace')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
