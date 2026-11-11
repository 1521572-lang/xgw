# ThinkCentre. YouTube через zapret2 без VPN — повтор после STOP

CODE `4a0e3eb70dffeae8274b80f71aad421fffe7e33d`, версия 0.2.0, freepool, исполнитель GLM-5.3-Flash.
Это актуальная редакция ТЗ после отчёта 47169f1. Код утилиты и помощник прежние.
ТЗ читать из свежей origin/freepool: в worktree CODE лежит его прежняя редакция.
Цель: ролик воспроизводится, отправка и приём идут через zapret2, VPN-выходов нет.
HTTP 200 страницы и готовый обработчик сами по себе PASS не дают. Дистрибутив не собирать.

## 1. Доступ: получить до начала прогона

Все команды, установку, клики и чтение результатов выполняет исполнитель своими инструментами.
Сначала проверить терминал ThinkCentre, `id -u`, `sudo -n true` (когда uid не 0), управление
графической сессией и доступ к GitHub. При отказе sudo проверить `NoNewPrivs` в `/proc/self/status`.
Если прав нет, запросить у владельца **терминал с root/sudo либо перезапуск агента с нужными
правами**, дождаться ответа, проверить доступ и продолжить самому. Не просить выполнить команды.
Тесты без sudo не заменяют этот шаг. Не заканчивать NOT_RUN сразу после первой ошибки sudo.
NOT_RUN допустим после отказа в доступе или подтверждённой невозможности его предоставить;
при ожидаемом ответе сохранить контекст и ждать. В отчёте указать инструмент, UTC и причину.
Git и GUI выполнять от обычного пользователя графической сессии. Если инструмент только root,
самому открыть пользовательский канал через runuser; root-команды выполнять в root-канале.
Определить пользователя/каталог репозитория по активной сессии, не угадывать `/root/xgw`.

Разрешены установка исходников XGW, рестарт демона, переключение VPN/standalone и остановка
только xgw-zapret2.service для проверки отказа. При смене режима XGW сам перезапускает Xray
и останавливает свои VPN-мосты. Соединения прервутся. Не менять WAN/LAN/Tailscale, sysctl,
подписки, чужие службы, не перезагружать ПК и не скачивать программы. Секреты не публиковать.

## 2. Подготовка в пользовательской bash-сессии

При ошибке блока сначала прочитать причину. Для ошибки доступа вернуться к §1.
Старую команду тестов из отчёта не повторять: ниже устранена зависимость от системного UID.

```bash
set -euo pipefail
cd "${XGW_REPO:-$HOME/xgw}"
test -z "$(git status --porcelain)"
sudo -v
sudo nft -j list tables >/dev/null
git fetch origin freepool
CODE=4a0e3eb70dffeae8274b80f71aad421fffe7e33d
git merge-base --is-ancestor "$CODE" origin/freepool
umask 077
D=$(mktemp -d "$HOME/xgw-zapret2-standalone.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
H="$D/new/docs/helpers/zapret2_standalone_check.py"
printf '%s  %s\n' 7ef6f6c839951bd5322dd36febcaa94f6a0eafca230e9f044e0c512b4735c99e "$H" | sha256sum -c -
date -u +%FT%TZ
sudo xgw status --json >"$D/status-before.json"
sudo xgw diag --no-net >"$D/diag-before.txt" || DIAG_BEFORE_RC=$?
sudo python3 -I "$H" snapshot "$D/baseline.json"
```

В root-канале те же административные команды исполняются без sudo, с фактическими D/H.
Прочитать исходный статус и диагностику, открыть окно с Vision. Нужны исправный VPN,
zapret2 off, capture on. Записать исходные WARN/FAIL, PID ядер, режим пула и ручной выбор.
Другой исходный режим не сбрасывать молча. Проверить установленные nfqws2/Lua и их права,
свободную NFQUEUE, block_quic=true, fail_mode=closed. Несоответствие — STOP с точной причиной.
**До удаления probe_urls** сохранить публичный watch-адрес из настроек/согласованных прогонов
в приватный файл в D. Это адрес страницы ролика, не временная ссылка на видеосегмент.

## 3. Тесты на ThinkCentre без зависимости от его UID

Пять падений отчёта — зависимость тестов от наличия xgw-singbox, а не новое правило standalone.
Правило существовало до CODE. Не вписывать UID 992 в ожидания и не удалять пользователя/правило.
Следующий блок подменяет определение UID только в процессе pytest; код и система не меняются.
Тест test_dedicated_singbox_uid_has_bypass_and_loopback_refusal сам задаёт UID 27123 и
проверяет реальную ветвь генератора с UID. Все прежние тесты остаются, xfail/skip не добавляются.
PY — уже установленный интерпретатор с pytest и PyQt6; если раньше использовали venv, выбрать его.

```bash
PY=${XGW_TEST_PYTHON:-$(command -v python3)}
"$PY" -c 'import pytest; import PyQt6.QtWidgets'
(cd "$D/new" && sudo env QT_QPA_PLATFORM=offscreen "$PY" - <<'PY'
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path.cwd() / "src"))
class HostIndependent:
    @pytest.fixture(autouse=True)
    def fixed_uid(self, monkeypatch):
        monkeypatch.setattr("xgw.net.nft.singbox_user_uid", lambda: None)
files = ["test_zapret2_standalone.py", "test_zapret2.py", "test_zapret2_panel.py",
         "test_generator.py", "test_nft.py", "test_net.py"]
raise SystemExit(pytest.main(["-o", "addopts=", "-q", "-p", "no:cacheprovider",
                             *["tests/" + f for f in files]], plugins=[HostIndependent()]))
PY
)
(cd "$D/new" && PYTHONPATH=src QT_QPA_PLATFORM=offscreen "$PY" -m pytest \
 -o addopts= -q -p no:cacheprovider tests/test_gui_qt.py -k zapret2)
```

Ожидается 0 failed; прежние 15 root/nft-пропусков должны выполниться с нужными правами.
Пропуск разобрать: отсутствие прав → §1; отсутствующая зависимость → запросить доступ к уже
установленной среде, не устанавливать пакеты молча. Не объявлять пропущенные проверки PASS.
Новый FAIL после этой изоляции — STOP с именем теста, traceback приватно, краткой причиной в отчёте.
Успех тестов → в этой же сессии продолжить установку и видео, не ждать следующего поручения.

## 4. Установка и включение режима

Закрыть окно XGW самому. Сохранить пакет и настройки; затем установить все исходники CODE,
сверить каждый файл до запуска демона. Ядра, зависимости Python и nfqws2 не заменять.

```bash
sudo bash -s -- "$D" <<'SH'
set -euo pipefail
D=$1; G=/opt/xgw/lib/xgw
test -f "$G/daemon.py"
install -d -m 0700 "$D/backup"
cp -a "$G" "$D/backup/xgw"
cp -a /etc/xgw "$D/backup/etc-xgw"
if test -f /var/lib/xgw/capture.json; then cp -a /var/lib/xgw/capture.json "$D/backup/"; fi
git -c safe.directory="$D/new" -C "$D/new" ls-files -z src/xgw >"$D/backup/files"
test -s "$D/backup/files"
trap 'cp -a "$D/backup/xgw/." "$G/"; systemctl start xgw.service' ERR
systemctl stop xgw.service
while IFS= read -r -d '' f; do
  install -D -o root -g root -m 0644 "$D/new/$f" "$G/${f#src/xgw/}"
  cmp -- "$D/new/$f" "$G/${f#src/xgw/}"
done <"$D/backup/files"
systemctl start xgw.service
trap - ERR
SH
```

Дождаться свежего статуса, сравнить с baseline. От одной установки PID Xray не меняется.
При ошибке до переключения восстановить пакет backup/xgw, запустить демон и записать STOP.
Открыть xgw gui, через Vision проверить кнопку «zapret2 без VPN» и читаемость окна.
В настройках выбрать multidisorder, удалить probe_urls, сохранить; watch-адрес уже сохранён.
Нажать «zapret2 без VPN», самому подтвердить штатный диалог. Ожидать готовность до 120 с.

```bash
sudo python3 -I "$H" snapshot "$D/ready.json"
```

Нужны ready=true, without_vpn_config=true, vpn_bridges=0, lease=true, queue=true.
Приватно проверить отсутствие VPN-выходов, балансировщиков, burstObservatory в рабочем конфиге.
Увидеть «Обработчик готов · без VPN», проверить обычную страницу вне выбранных доменов.
При ready=false прочитать причину в статусе/журнале, зафиксировать FAIL и перейти к возврату (§6).

## 5. Ролик, отправка и приём без VPN

Закрыть прежние вкладки YouTube. Самому создать отдельный профиль и запустить видимый Firefox
от пользователя графической сессии, проверить отсутствие расширений VPN и стороннего прокси.
Для snap профиль создать в его доступном каталоге пользователя (`~/snap/firefox/common/`),
для обычного Firefox — в D; каталог должен принадлежать пользователю браузера. Начать с about:blank.
При root-инструменте использовать runuser и окружение действующей графической сессии;
имя пользователя, DISPLAY/WAYLAND_DISPLAY и XDG_RUNTIME_DIR определить, не угадывать.

```bash
sudo python3 -I "$H" snapshot "$D/video-before.json"
```

Теперь открыть сохранённый watch-адрес, нажать Play. Через Vision наблюдать 60 с, записать
три позиции плеера, качество (желательно 720p), движение кадров и остановки/буферизацию.
Перемотать вперёд, проверить продолжение. Не делать fetch/GET/curl к видеоссылкам и не открывать
параллельно другие ролики. Старый профиль и cookie владельца не менять.

```bash
sudo python3 -I "$H" snapshot "$D/video-after.json"
sudo python3 -I "$H" delta "$D/video-before.json" "$D/video-after.json"
```

PASS VIDEO: видимое воспроизведение/перемотка, direct_data_confirmed=true, uplink вырос,
downlink вырос минимум на 2 МиБ, vpn_delta=0, конфиг и PID Xray/nfqws2 прежние.
При малом объёме продолжить тот же ролик до 120 с и снять новый after-файл с другим именем.
При отказе записать ошибку плеера и счётчики; страницу HTTP 200 не считать видео. При отказе
конкретного ролика допустим один другой публичный ролик. Затем результат, без серии GET-исследований.

## 6. Отказ, восстановление и возврат

Остановить `sudo systemctl stop xgw-zapret2.service`. В пределах двух шагов watchdog увидеть
блокировку выбранных доменов, worker_pid=0, without_vpn_config=true и отсутствие VPN-мостов.
Открыть ролик в новом чистом профиле: новый поток не проходит; старый буфер не доказательство.
Обычная страница остаётся доступна. Автовключение VPN — FAIL. Снять отдельный snapshot отказа.
Выполнить `sudo systemctl restart xgw.service`, дождаться ready=true, снова проверить ролик
и прямой маршрут. Это проверка восстановления и сохранения режима, без перезагрузки ПК.
Кнопкой питания снять перехват: прямой интернет, обработчик остановлен, VPN не включился.
Включить питание: standalone восстановился. Нажать «Вернуться к VPN», дождаться исправного VPN,
сверить прежние настройки пула/устройств/ручного выбора. Смена PID Xray при смене режима ожидаема.
При общем PASS снова включить standalone и оставить работающим по поручению владельца.
При FAIL вернуть исходный VPN через интерфейс новой версии; сохранить ошибку и конечное состояние.
Если панель недоступна, восстановить исходный /etc/xgw/panel.json из backup, выполнить
`sudo xgw apply --now`, проверить VPN. После успешного возврата при необходимости восстановить
пакет backup/xgw и перезапустить демон. При неудаче возврата STOP с причиной; таблицы вручную
не удалять, неизвестные поколения конфигов ядер не подменять. Приватные резервные копии сохранить.

## 7. Отчёт публикуется исполнителем автоматически

До одной страницы: CODE, UTC, инструмент/права запуска, тесты с изоляцией UID, установка,
Vision/позиции плеера/качество, upload/download/vpn_delta, стабильность PID, отказ и восстановление,
кнопки, конечный режим. Отдельно MODE, VIDEO, FAILURE, RESTORE, GUI; общий PASS только если все PASS.
При FAIL/STOP/NOT_RUN указать фактическую причину; не делать вывод о невозможности zapret2 вообще.
Отчёт писать в checkout свежей freepool, не в detached worktree CODE.
Сохранить новый `docs/TEST-REPORT-REAL-MACHINE-0.2.0-zapret2-standalone-r2-ДАТА.md`,
не перезаписывать первый отчёт. Проверить секреты, коммитить только отчёт и сразу выполнить обычный
push в freepool без запроса подтверждения. При обновлении ветки перенести свой коммит на свежую
origin/freepool без force; сверить удалённый файл, сообщить хеш и ссылку. При невозможности
публикации сохранить отчёт и причину. Для продолжения после успешных этапов отдельный запрос не нужен.
