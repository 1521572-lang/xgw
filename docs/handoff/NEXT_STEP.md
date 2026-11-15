# Ubuntu 24.04 — измерить эффект дополнений к плану zapret2

- delivery_branch: `integration/zapret2-batch1`
- base_commit: `f1fb5cb1613fa09dd57e2b25fd114a12c2079fc6`
- code_commit: последний коммит этой ветки, изменивший **этот файл**, вычисли и закрепи ниже
- report: `docs/reports/YYYY-MM-DD_desync-hypotheses-r1.md`
- Общий план: [DESYNC-ROADMAP](DESYNC-ROADMAP.md), исходные номера T01–T12 сохранены.
- Матрица: [DESYNC-EXPERIMENTS-r1](DESYNC-EXPERIMENTS-r1.md).

Ты — модель-исполнитель на реальном шлюзе. Выполни команды, разбор журналов, запуск видео и
vision сама. Если нет терминала/sudo/браузера, **запроси доступ**, не проси владельца запускать
скрипт. Публикуй отчёт и точечные совместимые исправления автоматически, даже при блокере.

Прочитай отчёты batch1-r2 и gui-catalog-map от 2026-11-15 и сетевой отчёт Flowseal от той же
даты, перечисленные в ROADMAP. Здесь нет нового дистрибутива и нет необходимости заменять
весь backend. Новые тактики испытываются allowlist-launcher под управлением установленного
XGW; probe запускается из закреплённого checkout. Worker active не означает PASS видео.

## Получи код

В чистом checkout, Bash, обычный пользователь:

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
git fetch origin integration/zapret2-batch1
TIP=$(git rev-parse FETCH_HEAD)
CODE=$(git log -1 --format=%H "$TIP" -- docs/handoff/NEXT_STEP.md)
BASE=f1fb5cb1613fa09dd57e2b25fd114a12c2079fc6
git merge-base --is-ancestor "$BASE" "$CODE"
REPO=$(git rev-parse --show-toplevel)
D=$(mktemp -d "$HOME/xgw-desync-ab.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
SOURCE="$D/source"
printf '%s\n' "$BASE" "$CODE" "$TIP" > "$D/revisions.txt"
cd "$SOURCE"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
uname -r > "$D/kernel.txt"
curl --version > "$D/curl-version.txt"
nft --version > "$D/nft-version.txt"
```

Если после CODE есть хотфикс, изучи diff и выбери его явно новым CODE, записав причину.
При другой ОС — BLOCKED_ENV, отчёт всё равно опубликуй.

## Очерёдность прохода

1. Если ещё нет отчёта о стрелках GUI, выполни сохранённое
   [малое задание](ARCHIVE-GUI-SORT-INDICATORS.md), используя **GUI CODE=f1fb5cb**.
   Сохрани отдельный отчёт; не повторяй уже принятую работу.
2. Пройди [DESYNC-EXPERIMENTS-r1](DESYNC-EXPERIMENTS-r1.md): предохранитель, доказательство
   пути, парные медиа-прогоны, видео. В сетевом опыте используй новый CODE из этого файла.
3. Заполни [шаблон](../reports/TEMPLATE_desync-hypotheses.md), включая все H01–H12:
   реализованные варианты — измерения; остальные — зависимости/NOT_IMPLEMENTED.
4. Восстанови настройки и исходные offload/worker, проверь GUI/API/HTTPS. Не оставляй
   экспериментальную политику без отдельного решения по результату приёмки.
5. Опубликуй отчёт. Следующий основной батч разработчика — **T03**, с учётом измерений;
   не предлагай повторять прежнюю матрицу HTTP без нового основания.

## Публикация

Допустимы маленькие исправления путей, совместимости Python/curl, таймера или launcher с
объяснением и повторением затронутого теста. Изменение marks, сетевого охвата, C ABI или
автоматической маршрутизации — архитектурное расхождение: восстанови состояние, опубликуй
BLOCKED с точными данными. Не включай приватный D/R, конфиги, HAR, pcap, токены.

Из исходного checkout создай ветку отчёта от актуальной delivery_branch. Перенеси только
проверенные хотфиксы из detached checkout, по точным путям.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/desync-hypotheses-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-hypotheses-r1.md"
# Заполни REPORT по TEMPLATE; хотфиксы добавляй отдельно по точным путям.
git add "$REPORT"
git diff --cached --check
git diff --cached
git commit -m "docs: report real-machine desync hypothesis experiments"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

Если push отклонён из-за нового коммита, fetch/rebase, проверь diff и повтори обычный push.
Force-push запрещён. В итоге дай hash отчёта и фактическое состояние машины.
