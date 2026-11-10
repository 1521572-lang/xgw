# ThinkCentre. zapret2 в поставке XGW

Исполнитель GLM-5.3-Flash. База — отчёт eb707af, код bfb8218, zapret2 off,
nfqws2 v1.0.7 во внешнем каталоге. Шлюз HEALTHY, diag 33/0/0, пул observe.
Задача — принять встроенный комплект и его Python-интеграцию, сохранив настройки и сеть.
Отчёт redirect5: VPN получил тело файла после двух переходов, прямой путь дал HTTP 302.
Это не доказательство отказа сайта или успешного видео; переадресации по этому ТЗ не проверять.
Новых сетевых проб, включения selective/compare, смены WAN/LAN/Tailscale/пула не делать.
Не запускать install_easy, blockcheck или полный xgw install на рабочем шлюзе. Экраном не управлять.

## 1. Подготовка

```bash
set -eu
cd ~/xgw
test -z "$(git status --porcelain)"
git fetch origin freepool
CODE=044409b61f46d4b1b40158c43ef7448b8beeb86b
BASE=bfb82184aabd913b145e9a6cef68b4168012d56c
umask 077
D=$(mktemp -d "$HOME/xgw-zapret2-bundle.XXXXXXXX")
git worktree add --detach "$D/new" "$CODE"
git worktree add --detach "$D/base" "$BASE"
H="$D/new/docs/helpers/zapret2_bundle_check.py"
printf '%s  %s\n' 'baf316b98e7a14e9f1cf81ad77275a6314ee95dc7aadf193bf9c0c6597c7ae6e' "$H" | sha256sum -c -
sudo python3 -I "$H" before --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-before"
```

Нужны baseline_ok, HEALTHY и отсутствие FAIL. Артефакты держать приватно.
Получить готовый архив Ubuntu 26.04 amd64 от владельца, сверить опубликованный SHA-256.
SHA-256 архива с исходниками CODE: `88ac3262820004f4c566b09fd83d84a85ad2feea2db7572d5ec740b87cdaa731`.
Не скачивать другой выпуск и не собирать на шлюзе. Нет архива — NOT_RUN artifact.
Архив должен содержать исходники CODE, UPSTREAM.json, лицензии и zapret2/1.0.7/bundle.json.
Распаковать в отдельный доступный для чтения каталог (nfqws2 сбрасывает UID перед Lua).
Обозначить абсолютный каталог xgw внутри архива как R. Сверить исходники с CODE через cmp.
Не менять права домашних каталогов; для проверки Lua можно использовать отдельный каталог /var/tmp.

## 2. Проверки без изменения шлюза

```bash
(cd "$D/new" && PYTHONPATH=src python3 -m pytest -p no:cacheprovider -o addopts= -q \
 tests/test_zapret2_bundle.py tests/test_zapret2.py tests/test_config.py)
sudo python3 -I "$H" check --state "$D/before.json" --bundle "$R/zapret2/1.0.7"
```

Нужны tests без новых падений и bundle_ok. check выполняет version и intercept=0, без NFQUEUE.
Отсутствуют runtime-библиотеки — NOT_RUN dependencies; устанавливать их только после отдельного
согласия владельца. Нужны liblua5.4-0, libnetfilter-queue1, libnfnetlink0, libmnl0, zlib1g.
Сырые ошибки и пути не публиковать. Несовпадение архитектуры/хешей — STOP.

## 3. Установка комплекта и Python-кода

Перед изменением получить согласие владельца. Сверить установленные config.py, install.py
с `$D/base/src/xgw/`; zapret2_bundle.py должен отсутствовать. При расхождении STOP.
Сохранить эти два файла и config.toml байт-в-байт с правами. Сохранить сведения, существовал ли
`/opt/xgw/zapret2/1.0.7`; иной комплект той же версии не перезаписывать.
Остановить только xgw.service. Установить три файла config.py, install.py, zapret2_bundle.py
из CODE с прежними владельцами/правами (новый — как install.py). Проверить Python-синтаксис.
Поставить готовый комплект функцией xgw.zapret2_bundle.install из CODE: source —
`$R/zapret2/1.0.7`, opt — `/opt/xgw`. Функция только копирует и проверяет файлы, не запускает службы.
Запустить xgw.service. Конфиг не менять, старые binary/lua_dir и внешний каталог оставить.
Xray и sing-box не перезапускать. При ошибке вернуть два сохранённых файла, удалить только
добавленный zapret2_bundle.py и только созданный этим прогоном комплект, запустить демон.
Не удалять старый внешний zapret2 или ранее существовавший комплект.

## 4. Приёмка и итог

```bash
sudo python3 -I "$H" check --state "$D/before.json" --bundle /opt/xgw/zapret2/1.0.7
sudo python3 -I "$H" finish --state "$D/before.json"
sudo xgw diag --no-net >"$D/diag-after"
```

Нужны bundle_ok, rollback_ok (конфиг/ядра прежние, off, capture on), HEALTHY, diag без новых FAIL.
Проверить root-владельца комплекта, каталоги 0755, бинарник 0755, Lua/лицензии 0644.
Ни один worker zapret2 не должен работать. Комплект и код оставить установленными в off.
Не менять явно заданные старые пути ради этой приёмки. Переход работающего режима на новый
бинарник и видео-проверка требуют отдельного ТЗ. При неудаче возврата STOP, сообщить владельцу.
Отчёт на страницу `docs/TEST-REPORT-REAL-MACHINE-0.2.0-zapret2-bundle-ДАТА.md`.
Записать CODE, SHA архива/помощника, тесты, результаты check/finish, состояние до/после,
установлен ли комплект и какие действия NOT_RUN. Без секретов, адресов, доменов и сырых журналов.
