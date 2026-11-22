# ThinkCentre — сверка источника Flowseal и комплекта zapret2, A7

**Ubuntu 24.04 LTS.** Flash самостоятельно запускает готовые команды
и публикует один обезличенный отчёт при любом исходе. При недоступности
терминала, sudo или GitHub запроси доступ.

R8 принят. Дедлайн дополнительных проб сработал один раз, маршруты
сохранились и HTTPS дал 12/12 в обеих фазах. Текущее ТЗ продолжает
пункты T06/T10. Оно проверяет воспроизводимость каталога, контракты
перевода и семантику установленного комплекта. [Отчёт r8](../reports/2026-11-22T221358Z_watchdog-scan-deadline.md)

## 1. Запуск

В терминале ThinkCentre выполни `sudo -v`. Если pytest в отдельном
окружении, экспортируй абсолютный `XGW_TEST_PYTHON`. Запусти блок
из существующей рабочей копии XGW. Он развернёт проверочные файлы
в закрытом каталоге, прочитает состояние шлюза и сверит его в конце.
BAT-файлы используются как текст. Lua-контроль выполняется в отдельном
сетевом пространстве с `--intercept=0`.

~~~bash
bash <<'BASH'
set -euo pipefail
umask 077
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $EUID != 0 ]]
BR=integration/zapret2-batch1
CODE=d671eecdb1bb4001f9d9de58fbc4fc33646792ae
SOURCE=2401b7a13837139b0265632464ba563dddbf80d8
UPSTREAM=https://github.com/Flowseal/zapret-discord-youtube.git
REPO=$(git rev-parse --show-toplevel)
PY=/usr/bin/python3
TEST_PY=${XGW_TEST_PYTHON:-$PY}
[[ $TEST_PY == /* && -x $TEST_PY ]]
sudo -n true
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD
D=$(mktemp -d "$HOME/xgw-flowseal-catalog.XXXXXXXX")
printf 'A7_CODE %s\nPRIVATE_ARTIFACTS %s\n' "$CODE" "$D"
mkdir -p "$D/tree" "$D/bat"
git -C "$REPO" archive "$CODE" src tests docs/helpers pyproject.toml | tar -x -C "$D/tree"
cd "$D/tree"

fib() {
  git -C "$REPO" show "$CODE:docs/helpers/audit_host_observe.py" |
    sudo -n /usr/bin/timeout -k 3 60 "$PY" -I -B - snapshot
}
fib >"$D/fib.before"
sudo -n sha256sum /etc/xgw/config.toml /etc/xgw/panel.json >"$D/settings.before"

if timeout -k 3 120 env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS= \
    PYTHONPATH="$D/tree/src:$D/tree/tests" "$TEST_PY" -B -P -m pytest \
    --portable -o addopts= -p no:cacheprovider -q --tb=short \
    tests/test_desync_flowseal.py >"$D/contracts.out" 2>&1 &&
    grep -Eq '^10 passed in ' "$D/contracts.out"; then
  grep -E '^10 passed in ' "$D/contracts.out"
  printf 'A7_CONTRACTS_OK\n'
else
  printf 'A7_CONTRACTS_FAILED\n'
fi

git init --bare -q "$D/source.git"
if timeout -k 3 90 git -C "$D/source.git" fetch --no-tags --depth=1 "$UPSTREAM" "$SOURCE" \
     >"$D/upstream.out" 2>&1 && [[ $(git -C "$D/source.git" rev-parse FETCH_HEAD) == "$SOURCE" ]]; then
  git -C "$D/source.git" ls-tree -z --name-only "$SOURCE" |
    while IFS= read -r -d '' file; do
      if [[ $file == general*.bat && $file != */* ]]; then
        git -C "$D/source.git" show "$SOURCE:$file" >"$D/bat/$file"
      fi
    done
  if "$PY" -B docs/helpers/make_flowseal.py docs/helpers/flowseal-youtube-source.json \
      docs/helpers --check --source-tree "$D/bat" >"$D/catalog.out" 2>&1; then
    cat "$D/catalog.out"
  else
    printf 'A7_CATALOG_MISMATCH\n'
  fi
else
  printf 'A7_SOURCE_UNAVAILABLE\n'
  "$PY" -B docs/helpers/make_flowseal.py docs/helpers/flowseal-youtube-source.json \
    docs/helpers --check || printf 'A7_CATALOG_MISMATCH\n'
fi

NF=/opt/xgw/zapret2/1.0.7/nfqws2
if env PYTHONPATH="$D/tree/src" "$PY" -B -P - "$NF" >"$D/bundle.out" 2>&1 <<'PYTHON'
import sys
from pathlib import Path

from xgw import zapret2
from xgw.config import Config
from xgw.desync import flowseal, preflight
from xgw.net import cmd
from xgw.zapret2_bundle import COMMIT, VERSION

binary = Path(sys.argv[1])
cfg = Config()
cfg.zapret2.queue_num = 201
base = zapret2.arguments(cfg)[:5]
assert base[0] == str(binary)
try:
    safe = preflight.prepare(base, cmd.run)
    banner = cmd.run([safe[0], "--version"], timeout=5)
    version = preflight._VERSION.search(banner)
    if not version or version[1] != VERSION or not COMMIT.startswith(version[2]):
        raise ValueError("engine_version_mismatch")
except FileNotFoundError:
    raise SystemExit("A7_ENGINE_MISSING") from None
except (OSError, ValueError, cmd.CommandError):
    raise SystemExit("A7_ENGINE_MISMATCH") from None
print("A7_ENGINE_MATCH")

cfg.zapret2.mode = "standalone"
cfg.zapret2.strategy = flowseal.LIVE_STRATEGY
cfg.zapret2.domains = list(flowseal.YOUTUBE_DOMAINS)
try:
    argv = zapret2.arguments(cfg)
except FileNotFoundError:
    print("A7_ALT9_ASSETS_MISSING")
except (OSError, ValueError, KeyError):
    print("A7_ALT9_ASSETS_REJECTED")
else:
    try:
        cmd.run([*preflight.prepare(argv, cmd.run), "--dry-run"], timeout=10)
    except (ValueError, OSError, cmd.CommandError):
        print("A7_ALT9_DRY_RUN_FAILED")
    else:
        print("A7_ALT9_DRY_RUN_OK")
PYTHON
then
  grep -E '^A7_(ENGINE_MATCH|ALT9_(DRY_RUN_(OK|FAILED)|ASSETS_(MISSING|REJECTED)))$' "$D/bundle.out"
  LUA='local s="ABCDE"; local p=resolve_pos(s,"unknown","2"); local z=resolve_pos(s,"unknown","2",true); print("AUDIT_POS",resolve_pos(s,"unknown","1"),p,z,#s:sub(1,p-1),resolve_pos(s,"unknown","99")==nil); local m="rnd,dupsid,sni=www.google.com"; local a=tls_mod(string.rep(string.char(0),4),m,fake_default_tls); local b=tls_mod(fake_default_tls,m,fake_default_tls); print("AUDIT_TLS",type(a),type(b),type(b)=="string" and #b or 0)'
  lua_rc=0
  sudo -n /usr/bin/timeout -k 2 15 unshare --net "$NF" --qnum=201 --intercept=0 \
    "--lua-init=$LUA" >"$D/lua.out" 2>&1 || lua_rc=$?
  printf 'A7_LUA_RC %s\n' "$lua_rc"
  grep -E '^AUDIT_(POS|TLS)[[:space:]]' "$D/lua.out" || true
else
  grep -E '^A7_ENGINE_(MISSING|MISMATCH)$' "$D/bundle.out" || printf 'A7_ENGINE_CHECK_FAILED\n'
fi

fib >"$D/fib.after"
if cmp -s "$D/fib.before" "$D/fib.after" &&
   sudo -n sha256sum --check --status "$D/settings.before"; then
  printf 'A7_GATEWAY_UNCHANGED\n'
else
  printf 'A7_GATEWAY_CHANGED\n'
fi
BASH
~~~

Если GitHub временно недоступен только для исходного репозитория
Flowseal, сохрани результат проверки закреплённого каталога из
checkout и пометь сверку BAT как `SOURCE_UNAVAILABLE`. Результат
`source_bat=0` покрывает воспроизводимость артефактов из каталога.

## 2. Критерии и отчёт

- `A7_CONTRACTS_OK` и 10 passed. Контракты покрывают привязку
  BAT-секций к веткам, порядок, исключения, числовые позиции,
  два литерала TLS, перенос IP ID и отклонение неподдержанного
  cutoff во включённой секции. Укажи число проверок и время.
- `FLOWSEAL_CHECK_OK configurations=22 source_bat=22` подтверждает
  размеры и SHA-256 закреплённых BAT, порядок опций и идентичность
  регенерированных каталога и вспомогательного launcher.
  Все 45 секций с cutoff остаются исключёнными.
- `A7_ENGINE_MATCH` означает совпадение установленной версии
  1.0.7 с коммитом `038c97e`, проверку Lua-файлов и манифеста
  при его наличии. Если манифест отсутствует, preflight сверяет
  версию бинарника. Для `MISSING` или `MISMATCH` запиши исход и
  оставь остальную часть прогона в отчёте.
- Для ALT9 зафиксируй `DRY_RUN_OK`, `DRY_RUN_FAILED`,
  `ASSETS_MISSING` или `ASSETS_REJECTED`. При отсутствии
  ассетов этот пункт остаётся непроверенным на установленном комплекте.
  Проверка порядка веток выполняется контрактами, а dry-run
  подтверждает принятие составленных аргументов.
- Для изолированного Lua укажи код завершения и обе строки.
  Ожидается `AUDIT_POS 2 3 2 2 true` и `AUDIT_TLS nil string N`
  при N > 4. Пустой вывод, таймаут и отсутствие доступа к
  `unshare` имеют отдельные исходы. Для этого прогона
  `playback=NOT_RUN`.
- Укажи `A7_GATEWAY_UNCHANGED` или `A7_GATEWAY_CHANGED`.
  В отчёт включи только совпадение служб, классов маршрутов и
  настроек, а при отличии перечисли изменившиеся классы полей.
  Сырые журналы, локальные пути и конфиги остаются на машине.

## 3. Публикация

Укажи абсолютный путь к готовому обезличенному отчёту в `REPORT_SRC`.
Выполни блок из рабочей копии при любом исходе и верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-flowseal-catalog-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_flowseal-a7-catalog.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre Flowseal catalog provenance and bundle validation'
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
git fetch origin "$BR"
git merge-base --is-ancestor HEAD FETCH_HEAD
printf 'PUBLISHED %s %s\n' "$(git rev-parse HEAD)" "$REPORT"
BASH
~~~
