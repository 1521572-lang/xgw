# T10 — приёмка импорта Flowseal на ThinkCentre

Цель — проверить 22 закреплённые конфигурации, выбор правильной ветки HTTP/TLS и
границы области действия. Используй установленный nfqws2 на Ubuntu 24.04 LTS.
Импортёр подготавливает снимок для проверки. Системные настройки и службы XGW
для этих опытов остаются в исходном состоянии. Запуск YouTube через импортированную
стратегию будет отдельным этапом после подтверждения импорта и ветвления.

Прочитай [пересчёт T09](../reports/2026-11-17_desync-t09-cdn-replay.md) и
[первый опыт Flowseal](../TEST-REPORT-REAL-MACHINE-0.2.0-flowseal-youtube-2026-11-15.md).
В T09 обе базовые геометрии прошли. В первом опыте Flowseal был только короткий
1080p у ALT9, без отдельного доказательства прохождения видео через очередь.

Ты сама выполняешь команды, сверяешь результаты и автоматически публикуешь
отчёт. Если терминал или sudo недоступны, запроси доступ и выполни независимые
проверки, которые доступны. Для этого задания достаточно терминала. Перед
экспериментами проверь свободное место и статус обращения по старому WAN-захвату.

## 1. Получение кода и снимка Flowseal

```bash
set -euo pipefail
umask 077
test -z "$(git status --porcelain)"
REPO=$(git rev-parse --show-toplevel)
git fetch origin integration/zapret2-batch1
CODE=$(git rev-parse FETCH_HEAD)
git merge-base --is-ancestor 0a71bf0 "$CODE"
D=$(mktemp -d "$HOME/xgw-t10.XXXXXXXX")
git worktree add --detach "$D/source" "$CODE"
cd "$D/source"
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export PYTHONPATH="$D/source/src"
python3 -m pytest --portable tests/test_desync_flowseal.py tests/test_zapret2.py
mkdir "$D/snapshots"
IMPORT=(python3 -m xgw.desync.flowseal --catalog-dir "$D/source/docs/helpers")
"${IMPORT[@]}" list >"$D/catalog.json"
```

Если сохранился приватный исходный снимок Flowseal с коммитом
`2401b7a13837139b0265632464ba563dddbf80d8`, укажи его путь в `FLOW`. Иначе
выполни блок загрузки из [исходного ТЗ](../TEST-PLAN-REAL-MACHINE-0.2.0-flowseal-youtube.md)
в `"$D/flowseal"` и установи `FLOW="$D/flowseal"`. Используй данные BAT
как файлы для сверки. User-списки в первом опыте пустые. Импортёр создаёт их
изолированные копии и отмечает происхождение `null`. Списки исходного снимка
и шлюза остаются на месте.

Подготовь 44 снимка. Для каждого импорта каталог назначения должен быть новым.

```bash
while IFS= read -r profile; do
  for scope in source youtube; do
    "${IMPORT[@]}" prepare --source-dir "$FLOW" --profile "$profile" \
      --scope "$scope" --output "$D/snapshots/$profile.$scope"
  done
done < <(python3 -c 'import json,sys; print(*json.load(open(sys.argv[1]))["profiles"], sep="\n")' "$D/catalog.json")
```

Сверь `plan.json` для ALT, ALT5, ALT7 и ALT9. Для `FLOWSEAL_LISTS` проверь
исходный порядок блоков, ссылки на положительные списки, exclusions и значения
overlap. Для `ADAPTED_YOUTUBE` проверь замену положительных ограничений шестью
доменами, сохранение exclusions и сопоставление номеров веток с исходными
профилями. ALT5-SYN в режиме source ограничен IPv4. В youtube он записан в
`excluded_profiles` с причиной `ipv4_syn_requires_lab`. Проверка SYN на
IPv4/IPv6 требует отдельного опыта, поскольку имя хоста на SYN ещё неизвестно.

Сделай копию исходного каталога для отрицательного контроля. Измени один байт
BAT или используемого ALT блоба, затем повтори импорт в новый каталог. Ожидай
код 2 и отсутствие выходного снимка. Отдельно повтори импорт в уже занятый путь
и проверь хэш исходного `plan.json`.

## 2. Preflight на реальном nfqws2

Сверь установленный бинарник и Lua до запуска. Путь ниже — штатный для ветки.
Если путь отличается, установи фактический путь из настроек рабочего XGW.
Выполни команды под рабочим пользователем внутри отдельного network namespace.
Проверки запускают только штатный бинарник и создаваемые снимком аргументы.

```bash
BUNDLE=/opt/xgw/zapret2/1.0.7
"$BUNDLE/nfqws2" --version
sudo timeout --kill-after=10s 300s unshare --net -- runuser -u "$(id -un)" -- \
  python3 - "$D/snapshots" "$BUNDLE" >"$D/preflight.json" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root, bundle = map(Path, sys.argv[1:])
base = [str(bundle / "nfqws2"), "--qnum=201", "--fwmark=0x40000000"]
base += [f"--lua-init=@{bundle / 'lua' / name}" for name in (
    "zapret-lib.lua", "zapret-antidpi.lua",
)]
results = []
for path in sorted(root.glob("*/plan.json")):
    plan = json.loads(path.read_text(encoding="utf-8"))
    row = {"profile": plan["profile"], "scope": plan["scope"], "stages": {}}
    for stage in ("--dry-run", "--intercept=0"):
        try:
            proc = subprocess.run([*base, *plan["arguments"], stage],
                                  stdin=subprocess.DEVNULL, timeout=8,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            (path.parent / (stage[2:].replace("=", "_") + ".log")).write_bytes(proc.stdout)
            row["stages"][stage] = proc.returncode
        except subprocess.TimeoutExpired:
            row["stages"][stage] = "TIMEOUT"
    results.append(row)
print(json.dumps(results, indent=2))
PY
```

Посчитай отдельно подготовленные снимки и число прошедших оба preflight для каждой
области. Сохрани первое реальное сообщение об ошибке по типу сбоя. Сверь форматы
в файлах, если `--dry-run` отклоняет положительный список, blob или параметр.
Укажи точную позицию аргумента, исключив приватные пути.

## 3. HTTP/TLS в изолированных namespaces

Проверь минимум ALT в обеих областях. Возьми схему client/server и очистку процессов
из [скрипта локальной лаборатории H05](../helpers/desync_t05_ttl_lab.sh).
Для HTTP достаточно `python3 -m http.server` на порту 80, для HTTPS —
`openssl s_server -WWW` на 443 с локальным сертификатом. Используй veth без
маршрута по умолчанию. Помещай TCP 80/443 в NFQUEUE только в client namespace.
Пропускай пакеты с битом fake `0x40000000` перед правилом queue. Для запуска
в клиентском namespace используй базовые аргументы из preflight, затем `--debug=1`
и массив `arguments` проверенного снимка. Дождись очереди в namespace и ограничь
время процесса через `timeout`. Исполняй аргументы массивом без `eval`.

- В source подбери имя из `list-general.txt`, отсутствующее в Google-списке и
  exclusions. В youtube используй разрешённое имя из шести доменов. Для обеих
  областей используй `curl --noproxy '*' --resolve host:port:LOCAL_IP`,
  одну HTTP и одну HTTPS передачу. Сверь хэш тела ответа.
- В журнале nfqws2 сохрани `l7proto`, профиль `matches` после определения имени
  и реально вызванную стадию Lua. Сопоставь номер с `profiles[].worker_profile`
  в плане. HTTP должен попасть в `H-HTTP`, TLS — в `H` при подходящем имени.
  Запись `payload` в argv сама по себе выбор ветки не подтверждает.
- Проведи отрицательный контроль с именем, отсутствующим в обоих доменных наборах,
  и локальным IP вне положительных source ipset. Для youtube исключи действие
  на имя вне scope. Сверь также сохранённые фильтры exclusions в плане. При
  возможности проверь блок с штатным исключённым hostname/IP в том же namespace.
- Если конкретный source ipset покрывает тестовый адрес, для отрицательной
  проверки подбери другой локальный адрес вне него либо отметь контроль
  `INCONCLUSIVE`. Не подменяй исходный список для получения PASS.
- Технический сбой HTTP/TLS, отсутствие подходящего имени в списке и ошибка
  Lua получают отдельный статус с причиной. QUIC и SYN зафиксируй как отдельные
  опыты; preflight не подтверждает выбор профиля на живом пакете.

Заверши свои процессы, удали только созданные namespaces и сверь исходные PID,
off/off, очередь, конфиги и VPN. Используй настоящий ThinkCentre для приёмки.
Внешний трафик и захват WAN для этого раунда не нужны.

## 4. Автоматическая публикация

Укажи SHA кода, 22×2 итоги импорта и preflight, реальные номера веток и итог
контролей. В отчёте приведи причины исключения SYN, отличия source/youtube, итог
отрицательного теста и состояние машины. Публикуй агрегаты и обезличенные статусы.
Опубликуй отчёт даже при блокере и явно пометь недоступные стадии.

```bash
cd "$REPO"
git fetch origin integration/zapret2-batch1
git switch -c "glm/t10-flowseal-$(date -u +%Y%m%dT%H%M%SZ)" FETCH_HEAD
REPORT="docs/reports/$(date +%F)_desync-t10-flowseal-import.md"
# Сама запиши REPORT по результатам.
git add "$REPORT"
git diff --cached --check
git commit -m "docs: verify staged Flowseal import on Ubuntu 24.04"
git push origin HEAD:integration/zapret2-batch1
git ls-remote origin refs/heads/integration/zapret2-batch1
```

При гонке сделай fetch, rebase и обычный push.
