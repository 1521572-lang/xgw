# ThinkCentre · раунд 2 · исполнитель B

В новом чате самостоятельно выполните техническую проверку XGW на ThinkCentre с Ubuntu 24.04 LTS. Лимит — 25 минут активной работы. При отсутствии терминала запросите доступ. Координатор выдаёт эту карточку первой. Для анализа используйте собственные журналы этого запуска. Откройте пять вопросов, требования к отчёту и команду публикации в [закреплённом протоколе](https://github.com/1521572-lang/xgw/blob/2aedffdeaa19e63d9294fc3f2f845607c20e8588/docs/handoff/flash-pair/PROTOCOL.md).

Выполните весь блок в Bash из полного клона XGW. Он задаёт слот и номер раунда, создаёт приватный каталог и проверяет версии скриптов по SHA-256.

```bash
umask 077
SLOT=B
ROUND=2
REPO=$(git rev-parse --show-toplevel)
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-flash-r2-$SLOT.XXXXXXXX")
printf 'Приватный каталог %s\n' "$D"
(
set -euo pipefail
git -C "$REPO" fetch --no-tags origin refs/heads/docs/flash-proton-ui-manifest
git -C "$REPO" cat-file blob c79837ebe47afc79d215bf1bc8a5904c0a959d0b >"$D/run.sh"
git -C "$REPO" cat-file blob 296a2a61bb8af4cebf0ce97d82328560b1bfca5e >"$D/ranges.py"
cd "$D"
sha256sum --check - <<'SUMS'
ec5864ccf851644553a3af24e1d6e11bc5b80c85490cb38f1847f5e38070f418  run.sh
0e67ddba3646dbc346f0dc92c039382dca1dae1c0eec2f252d66a540fbe45943  ranges.py
SUMS
bash "$D/run.sh" "$REPO" "$D" "$SLOT"
)
```

Ответьте на все пять вопросов протокола. Включите SHA коммита **этой карточки** из полученной ссылки, UTC, новый run ID, фактическое время, помощь и повторы, полный блок `evidence.txt` и его SHA-256. При сбое укажите результат каждого доступного этапа и причину пропусков.

Сохраните отчёт как `$D/report.md` и самостоятельно выполните блок автопубликации из протокола при любом исходе. Для отдельного вызова терминала восстановите сохранённые `REPO` и `D`, задайте `SLOT=B` и `ROUND=2`. Файл назначения — `docs/reports/flash-pair-v1/r2-B.md` в ветке `docs/flash-proton-ui-manifest`. Укажите ссылку на опубликованный коммит в своём чате.
