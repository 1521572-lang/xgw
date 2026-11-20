# ThinkCentre — повторный разбор счётчиков медиамаршрута T12

Исполнитель Flash самостоятельно открывает терминал на ThinkCentre с
Ubuntu 24.04 LTS. При недоступном терминале или каталоге артефактов
запроси доступ и продолжи сам. Задание состоит из чтения сохранённых
записей и публикации отчёта. Выполняй пересчёт от пользователя, которому
принадлежат журналы. Для этого прохода достаточно обычных прав.

Исходный проход подтвердил оба окна 720p, очередь в обоих окнах, обычный
сайт через VPN при Selective и новый CDN-сеанс во время fallback после
SIGKILL. Для seek были 44 совпадения сокетов, одно совпадение счётчика
zapret2 и одно полное совпадение. У initial 42 совпадения сокетов и
очереди, но ни одного совпадения счётчика zapret2. Нужно выяснить, что
именно было видно в счётчиках Xray в этих окнах.
[Отчёт живого прогона](../reports/2026-11-20T103848Z_selective-media-proof-r2.md)

## 1. Пересчёт

В терминале из рабочего репозитория XGW выполни весь блок одним вызовом.
Он прочитает закреплённые версии анализатора и обе тройки исходных
JSONL. Если найдено несколько полных комплектов, выбери по времени и
журналу шагов тот, который использован в живом отчёте. Передай его путь
как `XGW_R2_RUN=/абсолютный/путь bash <<'BASH'` в первой строке блока.

```bash
bash <<'BASH'
set -uo pipefail
umask 077
BR=integration/zapret2-batch1
OLD=1e0c29099eb1c8186c7c7ffb2f4931adfc988596
CODE=c1bc318f02bc0f35a34975e5c2817af0a487007e
FILE=docs/helpers/selective_media_evidence.py
REPO=$(git rev-parse --show-toplevel) || exit 2
OUT=$(mktemp -d "$HOME/xgw-media-counter-replay.XXXXXXXX") || exit 2

has_logs() {
  local label source
  for label in initial seek; do
    for source in player marked gateway; do
      [[ -r "$1/$label-$source.jsonl" ]] || return 1
    done
  done
}

RUN=${XGW_R2_RUN:-}
if [[ -z $RUN ]]; then
  candidates=()
  while IFS= read -r -d '' player; do
    candidate=${player%/*}
    if has_logs "$candidate"; then
      candidates+=("$candidate")
    fi
  done < <(find "$HOME" -maxdepth 4 -type f -name initial-player.jsonl -print0)
  if (( ${#candidates[@]} != 1 )); then
    printf 'COMPLETE_LOG_SETS=%s\n' "${#candidates[@]}"
    if (( ${#candidates[@]} )); then printf '%s\n' "${candidates[@]}"; fi
    exit 2
  fi
  RUN=${candidates[0]}
fi
if ! has_logs "$RUN"; then
  echo LOGS_UNAVAILABLE
  exit 2
fi

git -C "$REPO" fetch origin "$BR" &&
  git -C "$REPO" merge-base --is-ancestor "$CODE" FETCH_HEAD &&
  git -C "$REPO" merge-base --is-ancestor "$OLD" "$CODE" &&
  git -C "$REPO" show "$OLD:$FILE" >"$OUT/old.py" &&
  git -C "$REPO" show "$CODE:$FILE" >"$OUT/new.py" || exit 2

for label in initial seek; do
  args=(--player "$RUN/$label-player.jsonl" --marked "$RUN/$label-marked.jsonl"
        --gateway "$RUN/$label-gateway.jsonl")
  python3 "$OUT/old.py" "${args[@]}" >"$OUT/$label-old.json"
  old_rc=$?
  python3 "$OUT/new.py" "${args[@]}" >"$OUT/$label-new.json"
  new_rc=$?
  printf '%s old_rc=%s new_rc=%s\n' "$label" "$old_rc" "$new_rc"
  if (( old_rc || new_rc )); then
    continue
  fi
  python3 - "$OUT" "$label" <<'PY'
import json, sys
from pathlib import Path

directory, label = Path(sys.argv[1]), sys.argv[2]
old = json.loads((directory / f"{label}-old.json").read_text())
new = json.loads((directory / f"{label}-new.json").read_text())
keys = ("counts", "background_windows", "media_path", "nfqueue")
counts = new["counts"]
expected = {"initial": (46, 42, 42, 0, 0), "seek": (54, 44, 44, 1, 1)}
count_keys = ("comparable_windows", "socket_matches", "queue_matches",
              "outbound_matches", "full_matches")
print(json.dumps({
    "window": label,
    "unchanged": all(old[key] == new[key] for key in keys),
    "matches_report": tuple(counts.get(key, 0) for key in count_keys) == expected[label],
    **{key: new[key] for key in keys},
    "outbound_diagnostics": new["outbound_diagnostics"],
}, sort_keys=True))
PY
done
printf 'LOCAL_RESULTS=%s\n' "$OUT"
BASH
```

## 2. Критерии и решение по результату

- `REPLAY=PASS` при коде 0 у обеих версий для каждого окна,
  `unchanged=true` и `matches_report=true`. Иначе укажи фазу и наблюдаемый
  сбой. Если файлы потеряны или прав на чтение получить не удалось,
  зафиксируй `NOT_RUN` с причиной.
- Запиши `zapret2_background_peak_bytes_per_second` и суммы по
  `unmatched_reasons`. Для `no_growth` прирост равен нулю. Для
  `at_or_below_background` прирост положительный, но скорость не выше
  фонового максимума. `counter_unavailable` и `background_unavailable`
  означают пробел в соответствующем измерении.
- Сверь в пяти самых крупных окнах без подтверждённой дельты zapret2
  три группы downlink и признак очереди выше фона. Положительный
  групповой счётчик VPN показывает трафик группы в этом интервале.
  Для привязки к видео по-прежнему нужны отдельные наблюдения по потоку.
- Укажи, какой вариант подтверждается `initial`: нулевой счётчик,
  фоновый порог, отсутствующее измерение или смесь. `seek` служит
  положительным контролем. Допуски и статусы маршрута переносятся из
  пересчёта без ручной переклассификации. Живой отчёт остаётся источником
  результатов fallback и качества видео.

## 3. Отчёт и публикация

Сразу после пересчёта самостоятельно опубликуй один отчёт при
`PASS`, `FAIL`, `NOT_RUN` или `BLOCKED_ENV`. Включи SHA анализатора,
статус доступа, оба набора чисел, причины и возможное объяснение.
Используй относительное время и обезличенные агрегаты. Сырые JSONL,
пути домашнего каталога, IP, URL, PID, теги серверов и куки хранятся
на ThinkCentre. Если терминал так и недоступен, опубликуй `BLOCKED_ENV`
доступным способом на GitHub.

Сохрани Markdown в приватный файл и укажи его абсолютный путь в первой
строке следующего блока. Блок выполняется целиком и публикует только
новый отчёт в текущей ветке проекта.

```bash
REPORT_SRC=/абсолютный/путь/к/отчету.md bash <<'BASH'
set -euo pipefail
umask 077
BR=integration/zapret2-batch1
test -s "$REPORT_SRC"
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-media-counter-publish.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_selective-counter-replay.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
test "$(git diff --cached --name-only)" = "$REPORT"
git diff --cached --check
git commit -m "docs: report Selective media counter replay on ThinkCentre"
if ! git push origin "HEAD:refs/heads/$BR"; then
  git fetch origin "$BR"
  git rebase FETCH_HEAD
  git push origin "HEAD:refs/heads/$BR"
fi
SHA=$(git rev-parse HEAD)
git fetch origin "$BR"
git merge-base --is-ancestor "$SHA" FETCH_HEAD
printf 'https://github.com/1521572-lang/xgw/blob/%s/%s\n' "$SHA" "$REPORT"
BASH
```
