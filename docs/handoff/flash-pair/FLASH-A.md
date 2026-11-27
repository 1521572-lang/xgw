# ThinkCentre · техническое задание Flash A

Вы — исполнитель A в парном испытании XGW. Самостоятельно пройти [общий протокол](PROTOCOL.md), ответить на все пять вопросов по собственным замерам и автоматически опубликовать свой обезличенный отчёт по инструкции из протокола. Условия и лимит у обоих исполнителей одинаковы. Если терминал недоступен, запросить доступ. Ход испытания, параметры стенда и выводы другой модели во время работы не читать.

Запуск из полного клона XGW на ThinkCentre (Ubuntu 24.04 LTS) в Bash. Привязка скриптов к Git-объектам сохраняет точную версию при последующем продвижении ветки. При работе через отдельные вызовы терминала сохранить значения `D`, `REPO`, `ROUND` и `SLOT` в контексте своего чата для публикации.

```bash
umask 077
SLOT=A
ROUND=${XGW_FLASH_ROUND:-1}
REPO=$(git rev-parse --show-toplevel)
D=$(mktemp -d "${TMPDIR:-/tmp}/xgw-flash-$SLOT.XXXXXXXX")
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

Оформить `$D/report.md` и выполнить блок автопубликации из протокола. Для первого раунда файл на GitHub — `docs/reports/flash-pair-v1/r1-A.md`. Сообщить ссылку на коммит со своим отчётом.
