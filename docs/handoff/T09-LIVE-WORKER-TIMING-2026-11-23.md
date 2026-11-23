# ThinkCentre — живая HTTPS-матрица T09 с CDN из Standalone, r2

**Ubuntu 24.04 LTS.** Flash самостоятельно запускает закреплённый сценарий
и публикует один обезличенный отчёт при любом исходе. При недоступности
терминала, sudo, локальной панели или GitHub запроси доступ. Выполняй
сетевую часть в согласованное окно обслуживания с учётом двух штатных
запусков `xgw.service` при временной установке и откате.

В изолированной NFQUEUE запуски заняли 121 и 55 мс. Чтобы оценить
вклад на рабочем шлюзе, нужны данные запуска и полной длительности
одной и той же попытки. В первом проходе URL, полученный через VPN,
прошёл контроль VPN, но обе прямые пробы завершились TLS-таймаутом.
В r2 URL отдельно получают в Standalone, как в ранее успешной матрице
`direct-b`. VPN-URL служит контролем исходного режима.

[Отчёт r1](../reports/2026-11-23T063407Z_t09-live-worker-timing.md) · [Успешная матрица direct-b](../reports/2026-11-20T060738Z_selective-cdn-peer.md#3-прямой-контроль-и-матрица)

## 1. Запуск

Из обычного терминала пользователя рабочего стола проверь вход в штатную
панель и выполни `sudo -v`. Если pytest установлен в venv, экспортируй
`XGW_TEST_PYTHON` с абсолютным путём к его Python. При недоступном
тестовом ролике допустима одна попытка с другим роликом через
`XGW_T09_VIDEO`. Для неё используй 720p/HTTPS и длительность от 195 с.
При TLS-отказе на свежем CDN зафиксируй исход и заверши этот проход.

~~~bash
bash <<'BASH'
set -euo pipefail
BR=integration/zapret2-batch1
CODE=7ea65a544f0a69ce06937c8012c28a1b2032ae17
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BR"
git merge-base --is-ancestor "$CODE" FETCH_HEAD
git show "$CODE:docs/helpers/t09_live_worker_timing.sh" | bash -s -- "$CODE"
BASH
~~~

Сценарий пишет шаги `T09_STEP` и приватные файлы в каталог
`PRIVATE_ARTIFACTS`. До изменения политики он выполняет 180 контрактов,
берёт общий lock, сверяет три заменяемых файла и текущий `zapret2.py`
с `3a00777`, подтверждает off/off и обычный VPN. Затем получает свежий
подписанный URL, проверяет `206/65536` через VPN и включает независимый
40-минутный возврат. Сценарий включает Standalone `multisplit` для
доменных имён YouTube и запрашивает свежий URL без прокси yt-dlp.
У диапазона 64 КиБ должны пройти два ответа `206`, второй с закреплением
IPv4 первого. Проверяются одна ревизия Standalone и прирост счётчика
zapret2 в сопоставимых снимках Xray. После подтверждённого off/off
сценарий использует этот URL для допуска Selective на установленной базе.
Нужны два успешных ответа с разными штампами. При первом TLS-таймауте
допустим один штатный повтор. После допуска сценарий подтверждает правило
Xray, возврат в off/off и временно устанавливает телеметрию.

Установка заменяет `desync/worker.py`, `desync/jobs.py` и
`watch/zapret2_control.py`. Для карточки используется малая правка
закреплённой базы. Драйвер Xray, генератор маршрутов и текущий
`daemon.py` в поставку этого опыта не входят. Четыре попытки идут в
порядке `fake_md5 → multidisorder → multidisorder → fake_md5`.
Каждая отделена подтверждённым off. Общий лимит задания — 850 с.
Задание использует один URL, чья оставшаяся жизнь проверяется до допуска,
установки и запуска матрицы.

## 2. Что включить в отчёт

- ОС, SHA кандидата, количество тестов, исход сверки базы и очередей.
  Укажи коды HTTP для обычного VPN и диапазона. При отказе прямой
  пробы укажи этап, причину и результат штатного повтора. Если
  `overlay-apply` отсутствует, результат установки и матрицы — `NOT_RUN`.
- Приведи результаты `standalone-resolve`, `standalone-range-pair` и
  `standalone-route`. Укажи коды, байты и факт совпадения IPv4 двух
  запросов curl. Скопируй обезличенные `same_hostname`,
  `same_connector_ip` и `zapret2_downlink_delta` при наличии. Отдельно
  укажи допуск того же URL в Selective. Успех Standalone и отказ Selective
  дают основание сравнить служебный путь и контроль на одном IP.
  Метрики окна сами по себе не связывают конкретные сокеты с Xray.
- При запуске матрицы укажи состояние и `restore` задания. Для каждого
  профиля и круга приведи состояние, фазу таймаута при наличии,
  `elapsed_ms`, `policy_apply`, `outcome_wait`, `off_confirm` и
  `worker_start`. Пустое измерение обозначь явно. Полнота наблюдения
  означает четыре строки, терминальное `complete` и `restore=pass`.
- Для каждого круга приведи `worker_start.samples` и число наблюдаемых
  строк. Если сумма `attempt_with_worker_start.total_ms` положительна,
  доля равна `100 × worker_start.total_ms / attempt_with_worker_start.total_ms`.
  Общую долю считай по суммам двух кругов, с тем же знаменателем.
  При отсутствии замеров или положительной длительности результат
  `NOT_MEASURED`. При неполном покрытии вывод относится лишь к попыткам
  с подтверждённым владельцем. Время до резервирования очереди и
  подтверждение `off` измеряются отдельно от запуска.
- Укажи финальную сверку трёх файлов, настроек, off/off, пустых очередей,
  VPN и таймера. Успехи учитывай как HTTPS-допуск.
  Сопоставимость CDN-IP по попыткам остаётся `NOT_VERIFIED`.
  Воспроизведение, живая ротация и постоянный воркер — `NOT_RUN`.
- В отчёт публикуй агрегаты и краткие причины. Подписанный URL, адреса,
  токены, идентификатор задания, пути и полный вывод остаются на машине.

## 3. Возврат и публикация

При штатном выходе сценарий запускает возврат и печатает
`T09_RESTORED` после проверки. Если терминал оборвался, повтори
штатный возврат из обычного терминала с sudo. Укажи абсолютный
`XGW_T09_RUN`, напечатанный для этого прогона. При недоступности
sudo оставь независимый таймер активным и запроси доступ для сверки.

~~~bash
bash <<'BASH'
set -euo pipefail
[[ $XGW_T09_RUN == /* ]]
mapfile -t restore <"$XGW_T09_RUN/restore-location"
[[ ${#restore[@]} == 3 && ${restore[0]} == /var/lib/xgw/handoff/t09-worker-timing.* ]]
sudo -n /bin/bash "${restore[0]}/guard.sh" \
  "${restore[0]}" /usr/bin/python3 "${restore[1]}" "${restore[2]}" --selective-worker-timing
sudo -n test -f "${restore[0]}/restore-completed"
sudo -n sha256sum --check --status "${restore[0]}/config-before.sha256"
systemctl is-active xgw.service
systemctl show xgw-zapret2.service xgw-nfqws2.service -p ActiveState -p MainPID
sudo -n systemctl stop xgw-selective-worker-timing-rollback.timer
BASH
~~~

Укажи абсолютный путь к обезличенному отчёту в `REPORT_SRC` и
выполни блок из рабочей копии при любом исходе. Верни ссылку на коммит.

~~~bash
bash -s -- "$REPORT_SRC" <<'BASH'
set -euo pipefail
umask 077
REPORT_SRC=$1
BR=integration/zapret2-batch1
[[ $REPORT_SRC == /* && -s $REPORT_SRC ]]
REPO=$(git rev-parse --show-toplevel)
PUB=$(mktemp -d "$HOME/xgw-t09-live-report.XXXXXXXX")
git -C "$REPO" fetch origin "$BR"
git -C "$REPO" worktree add --detach "$PUB/repo" FETCH_HEAD
trap 'git -C "$REPO" worktree remove "$PUB/repo" && rmdir -- "$PUB"' EXIT
cd "$PUB/repo"
REPORT="docs/reports/$(date -u +%Y-%m-%dT%H%M%SZ)_t09-live-worker-timing.md"
test ! -e "$REPORT"
cp -- "$REPORT_SRC" "$REPORT"
git add -- "$REPORT"
git diff --cached --check
git commit -m 'Report ThinkCentre live HTTPS matrix worker timing'
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
