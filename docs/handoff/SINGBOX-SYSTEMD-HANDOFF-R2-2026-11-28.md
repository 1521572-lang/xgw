# ThinkCentre · повтор системной фазы sing-box с PrivateTmp

Ubuntu 24.04 LTS amd64. Кандидат `d6627ce07b49f23ba7e1429b041138761695e825`. На `6099f94` приняты 219 регрессий, 12 проверок watchdog, 30 контрактов Applier, 5 проверок Xray и контрольный переход. Системная фаза остановилась на первом запуске с `203/EXEC`. Стенд размещал исполняемый файл в `/var/tmp`, который скрыт при `PrivateTmp=true`. В повторе временное дерево создаётся в новом выделенном каталоге `/opt/xgw-systemd-*` на исполняемом разделе. `PrivateTmp` входит в проверку обоих юнитов. Повторять только системную фазу. [Первый отчёт ThinkCentre](https://github.com/1521572-lang/xgw/blob/66b999f2449d52f43a3cb4ca4eaa68ef585e2b01/docs/reports/2026-11-27T212513Z_singbox-systemd-handoff.md)

Flash сама запускает команды и публикует обезличенный отчёт при любом исходе. Использовать установленные ядра. Перед блоком проверить доступ к разрешённому sudo, при недоступности запросить права. При сохраняющемся блокере выполнить доступные шаги и опубликовать `NOT_RUN` с причиной. Штатные службы только читаются.

## 1. Системная фаза

Из полного клона XGW выполнить блок. При нестандартном расположении ядер задать абсолютные `XGW_TEST_XRAY` и `XGW_TEST_SINGBOX`. `PRIVATE_ARTIFACTS` указывает на закрытые журналы, а `PRIVATE_SYSTEMD_ROOT` и `PRIVATE_UNITS` — на точные временные ресурсы запуска. Сценарий занимает около 6 минут. Для временных юнитов заданы отдельный лимит работы и отключённый автоматический перезапуск.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 && $(dpkg --print-architecture) == amd64 ]]
REPO=$(git rev-parse --show-toplevel)
CODE=d6627ce07b49f23ba7e1429b041138761695e825
BUNDLE=docs/handoff/artifacts/xgw-singbox-systemd-handoff-r2.bundle
SINGBOX=${XGW_TEST_SINGBOX:-/opt/xgw/sing-box/sing-box}
XRAY=${XGW_TEST_XRAY:-/opt/xgw/xray/xray}
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-handoff.XXXXXXXX")
printf 'PRIVATE_ARTIFACTS %s\nCANDIDATE %s\nOS %s\n' "$D" "$CODE" "$PRETTY_NAME"
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" show "FETCH_HEAD:$BUNDLE" >"$D/code.bundle"
printf '%s  %s\n' 'fa54540532530c58a76a32b3a4ca78109de791ab2a6b01a8c10b968ce1496245' "$D/code.bundle" | sha256sum --check --status -
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
| `SYSTEMD_LAYOUT` | Использован новый каталог под `/opt` на исполняемом разделе. Помощник отклоняет `/tmp`, `/var/tmp`, `/run`, рабочий каталог XGW и раздел с `noexec`. В отчёте привести категорию пути без полного имени. |
| `SYSTEMD_BLUE_POLICY`, `SYSTEMD_GREEN_POLICY` | Оба временных юнита реально запустились. Для каждого подтверждены учётная запись sing-box, пустые capabilities, `NoNewPrivs=1`, `PrivateTmp`, `ProtectSystem=strict`, `ReadOnlyPaths` с `/run` и семейства адресов. При отказе указать этап и обезличенную причину, включая наличие или отсутствие `203/EXEC`. |
| `SYSTEMD_HANDOFF` | Green прошёл запрос через новый мост. После коммита API Xray сохранил запуск, новый поток получил B, старый продолжил получать A. |
| `SYSTEMD_GRACE`, `SYSTEMD_REAP` | 300 секунд без смены часов или дедлайна в файле. Оба потока отвечают, после срока systemd подтверждает остановку blue, старый поток закрывается, green отвечает. Указать число выборок. |
| `SYSTEMD_CLEAN`, `SYSTEMD_ROOT_CLEAN`, `SYSTEMD_ROOT_ABSENT` | У обоих временных юнитов `LoadState=not-found` и `MainPID=0`, Xray стенда завершён, выделенный временный каталог удалён. При сбое проверить только точные имена из приватного журнала. |
| `HOST_FIELDS` | Для пяти штатных юнитов сопоставить `LoadState`, `ActiveState` и `MainPID`. Если контроль VPN выполнен, записать только HTTP-результат и итог без адресов. |

Для `SYSTEMD=PASS` нужны нулевой код и все метки системной фазы. При сбое завершить прогон, записать последний достигнутый этап и состояние очистки. Результаты регрессий и контрольного перехода взять из предыдущего отчёта. Рабочее переключение, физический LAN и внешний трафик в этом повторе имеют статус `NOT_RUN`.

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
  file=docs/reports/$(date -u -r "$REPORT_SRC" +%Y-%m-%dT%H%M%SZ)_singbox-systemd-handoff-r2.md
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
    commit=$(git -C "$repo" -c user.name='XGW acceptance' -c user.email='1521572-lang@users.noreply.github.com' commit-tree "$tree" -p "$tip" -m 'docs: report ThinkCentre systemd handoff repeat with PrivateTmp')
    if git -C "$repo" push origin "$commit:$ref"; then
      printf 'PUBLISHED %s %s\n' "$commit" "$file"
      exit 0
    fi
  done
  exit 1
)
~~~

При недостатке прав записи запросить доступ и повторить с тем же отчётом. Вернуть ссылку на опубликованный коммит.
