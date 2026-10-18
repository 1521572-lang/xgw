# Программа испытаний XGW 0.1.12 на реальной машине

**Для исполнителя.** Выполняй шаги строго по порядку. В каждом шаге — команда (копируй
целиком), «Ожидается» и «Если не так». Ничего не придумывай сверх написанного. Не уверен —
остановись и спроси заказчика. Все выводы команд сохраняй в файлы, как написано: из них
собирается отчёт (§10).

Машина: ThinkCentre, Ubuntu 24.04.5 LTS, Docker, роутер HUAWEI AX2 за шлюзом. Стоит XGW
**0.1.11** в боевом режиме: от него работает интернет всего дома.

Что нового в 0.1.12: у шлюза **два ядра** — Xray и sing-box (как у Happ). sing-box ведёт
серверы, которых нет в Xray (hysteria2, TUIC, AnyTLS, WireGuard, Shadowsocks с плагинами), и
служит запасным путём, когда провайдер глушит соединения Xray. У каждого сервера в `xgw servers`
появилась метка ядра: `[xray]`, `[xray+frag]`, `[sb]`, `[sb+frag]`, `[sb+mux]`.

Цели:

1. Поставить 0.1.12 вместе с sing-box (шаг 2).
2. Убедиться, что служба, метки и диагностика в порядке (шаг 3).
3. Проверить, что трафик идёт через sing-box на этой машине (шаг 4).
4. **Главное:** узнать, помогает ли sing-box у домашнего провайдера (шаг 5), и посмотреть, что
   шлюз делает сам (шаг 6).
5. Проверить слежение за sing-box (шаг 7) и что в журналах нет секретов (шаг 8).

## 0. Запрещено

- `xgw net down`, `xgw uninstall`, `reboot`, `install.sh --force` — **никогда**.
- `flush ruleset`, ручные команды `nft`, `ip`, `iptables`, `sysctl -w` — **никогда**.
- Запускать `sing-box` и `xray` вручную, править их файлы, останавливать `xgw-xray`.
- Открывать или скачивать адреса подписок (curl, браузер), копировать ссылки серверов.
  (Единственная загрузка — sing-box: её делает установка, шаг 2.)
- Править код XGW.
- Коммитить что-либо, кроме отчёта (§10). Файлы из `~/xgw-0.1.12-test` в Git **не класть**.
- Писать в отчёт: адреса подписок, UUID, пароли, ключи, токены, IP и домены серверов, свой
  внешний IP. Серверы называй по имени или тегу (`spare-nl-1a2b`).

Аварийный выход, если пропал интернет: `sudo xgw disable` (интернет пойдёт напрямую), затем
сообщить заказчику.

**Остановись и спроси заказчика** перед шагами 5 и 7 — там это написано отдельно.

## 1. Подготовка

Шаг 1.1. Каталог для результатов:

```bash
mkdir -p ~/xgw-0.1.12-test/before ~/xgw-0.1.12-test/after && chmod 700 ~/xgw-0.1.12-test && cd ~/xgw-0.1.12-test && date
```

Ожидается: печатается дата. Дальше все команды выполняй из этого каталога.

Шаг 1.2. Снимок состояния до обновления:

```bash
sudo xgw --version; sudo xgw status > before/status.txt; sudo xgw servers > before/servers.txt; sudo xgw diag > before/diag.txt; tail -1 before/diag.txt
```

Ожидается: `xgw 0.1.11` и строка «Итог: OK — …, WARN — …, FAIL — 0».
Если не так (другая версия или FAIL не 0): записать в отчёт и спросить заказчика, продолжать ли.

Шаг 1.3. Что за серверы в подписках (протоколы, без адресов и имён):

```bash
sudo python3 - <<'EOF' | tee before/protocols.txt
import json, collections
data = json.load(open("/var/lib/xgw/inventory.json"))
print(collections.Counter(item.get("protocol") for item in data["servers"]))
EOF
```

Ожидается: словарь вида `Counter({'vless': 40, ...})`. Записать в отчёт, есть ли среди протоколов
`hysteria2`, `tuic`, `anytls` или `wireguard`: у 0.1.11 такие серверы были «пропущены», у
0.1.12 — их ведёт sing-box.

## 2. Установка 0.1.12

Шаг 2.1:

```bash
cd ~/xgw && git pull && git log -1 --format=%H && grep __version__ src/xgw/__init__.py && cd ~/xgw-0.1.12-test
```

(Если код лежит в другом каталоге — перейди в него вместо `~/xgw`.)
Ожидается: `__version__ = "0.1.12"`. Записать хеш.

Шаг 2.2. Установка (из каталога кода):

```bash
cd ~/xgw && date +%T | tee ~/xgw-0.1.12-test/install-time.txt && sudo sh packaging/install.sh --yes 2>&1 | tee ~/xgw-0.1.12-test/after/install.txt | tail -25; echo "код ${PIPESTATUS[0]}"; cd ~/xgw-0.1.12-test
```

Ожидается: «код 0», в выводе строка «sing-box v1.14.3 — /opt/xgw/sing-box». Время из
`install-time.txt` — «время установки» в шагах ниже.
Если код не 0: **стоп**, сохранить вывод, сообщить заказчику.
Если sing-box «не загружен» (предупреждение, а код 0): записать причину и выполнить
`sudo xgw update-singbox`; если и он не загрузил — **стоп**, дальше шаги 4–7 не делать, в отчёте
написать, что проверены только шаги 1–3.

Шаг 2.3. Повторная установка поверх (должна быть безопасной):

```bash
sudo xgw update-singbox; echo "код $?"
```

Ожидается: «sing-box 1.14.3 — уже нужная версия», код 0.

## 3. Службы, метки, диагностика

Шаг 3.1:

```bash
systemctl is-active xgw-net xgw-xray xgw xgw-dhcp xgw-singbox; ls -l /opt/xgw/sing-box/sing-box /etc/xgw/sing-box/config.json; /opt/xgw/sing-box/sing-box version | head -1
```

Ожидается: `active` для всех пяти, оба файла на месте, `sing-box version 1.14.3`.
Если `xgw-singbox` — `inactive` и файла `/etc/xgw/sing-box/config.json` нет: это нормально,
если в подписках нет серверов, пригодных для sing-box (при `[core] mode = "auto"` пригодны и
обычные серверы VLESS, VMess, Trojan). Подожди 2 минуты и повтори; если так и есть — записать.

Шаг 3.2. Метки ядра и диагностика:

```bash
sudo xgw servers > after/servers.txt; grep -oE '\[(xray|xray\+frag|sb|sb\+frag|sb\+mux)\]' after/servers.txt | sort | uniq -c; sudo xgw diag > after/diag.txt; grep -E 'sing-box|Службы' after/diag.txt; tail -1 after/diag.txt
```

Ожидается: у каждого сервера метка (`[xray]` у большинства); строки diag: «OK    sing-box:
версия 1.14.3», «OK    sing-box: конфиг: принят sing-box check, мостов: N», службы работают;
итог «FAIL — 0».

Шаг 3.3. Страница с серверами в панели (смотрит заказчик, 1 минута): панель → «Серверы»:
у каждого сервера бейдж ядра («Xray», «sing-box»…), у серверов, которые умеют оба ядра, —
список «Авто / Только Xray / Только sing-box». Записать, как заказчик это видит.

## 4. Трафик через sing-box

Шаг 4.1. Выбери **безлимитный** сервер в работе, который умеет оба ядра (метка `[xray]`,
в `xgw servers` — в блоке «Участники»), и запиши его тег:

```bash
sudo xgw servers | sed -n '1,8p'
```

Шаг 4.2. Закрепить за ним sing-box (вместо `TAG` — тег, например `proxy-nl-1a2b`):

```bash
TAG=proxy-xx-0000   # ← подставь тег
sudo xgw core $TAG sing-box && sleep 60 && sudo xgw servers | grep "$TAG"
```

Ожидается: «ядро сервера … только sing-box», через минуту у сервера метка `[sb]`.
Если команда ответила «не найден» или «подходит нескольким» — взять другой тег.
Если метка так и осталась `[xray]`: подождать ещё 2 минуты (конфиг sing-box мог ждать окна
перезапуска), потом записать.

Шаг 4.3. Весь трафик машины через этот сервер и проверка выхода:

```bash
sudo xgw pin $TAG --ttl 10m && sleep 5 && curl -s --max-time 20 https://ifconfig.me > after/exit-singbox.txt; echo "код $?"; wc -c after/exit-singbox.txt
```

Ожидается: «код 0», файл не пуст. **Сам адрес в отчёт не переписывать.**

Шаг 4.4. Вернуть как было:

```bash
sudo xgw unpin && sudo xgw core $TAG auto && sleep 60 && sudo xgw servers | grep "$TAG"; curl -s --max-time 20 https://ifconfig.me > after/exit-after.txt; echo "код $?"
```

Ожидается: метка снова `[xray]`, «код 0». Сравни `exit-singbox.txt` и `exit-after.txt`:
`cmp after/exit-singbox.txt after/exit-after.txt && echo "тот же" || echo "разные"` —
для отчёта достаточно слова «тот же» или «разные» (один и тот же сервер — адрес тот же).

## 5. Помогает ли sing-box у этого провайдера

**Предупреди заказчика:** «10–15 минут все серверы будут работать через второе ядро; интернет
будет, соединения могут обрываться». Дождись согласия.

Шаг 5.1. Конфиг: копия и проверка, что секции `[core]` ещё нет:

```bash
sudo cp /etc/xgw/config.toml ~/xgw-0.1.12-test/config.toml.bak && sudo chmod 600 ~/xgw-0.1.12-test/config.toml.bak && sudo grep -c '^\[core\]' /etc/xgw/config.toml
```

Ожидается: `0`. Если `1` или больше — **стоп**, шаг 5 пропустить, записать «секция уже есть».

Шаг 5.2. Базовая картина на Xray (так шлюз работает сейчас):

```bash
sudo xgw probe --all > after/probe-xray.txt; cat after/probe-xray.txt
```

Шаг 5.3. Все серверы, которые это умеют, — через sing-box:

```bash
printf '\n[core]\nmode = "sing-box"\n' | sudo tee -a /etc/xgw/config.toml >/dev/null && sudo xgw apply --now; sleep 90; sudo xgw servers | grep -oE '\[(xray|xray\+frag|sb|sb\+frag|sb\+mux)\]' | sort | uniq -c
```

Ожидается: большинство серверов — `[sb]`. (`xgw apply --now` может написать про перечитывание
sing-box — это нормально.)
Если `[sb]` нет совсем: подождать ещё 2 минуты и повторить последнюю часть команды; если снова
нет — шаг 5.6 (вернуть) и записать.

Шаг 5.4:

```bash
sudo xgw probe --all > after/probe-singbox.txt; cat after/probe-singbox.txt
```

Шаг 5.5. Только Xray — для контроля (серверы, которые умеет лишь sing-box, на это время
пропадут из списка):

```bash
sudo sed -i 's/^mode = "sing-box"$/mode = "xray"/' /etc/xgw/config.toml && sudo xgw apply --now; sleep 90; sudo xgw servers | grep -c '\[sb'
```

Ожидается: `0`. Затем `sudo xgw probe --all > after/probe-xray-only.txt`.

Шаг 5.6. Вернуть конфиг как было:

```bash
sudo install -m 600 -o root -g root ~/xgw-0.1.12-test/config.toml.bak /etc/xgw/config.toml && sudo grep -c '^\[core\]' /etc/xgw/config.toml; sudo xgw apply --now; date +%T
```

Ожидается: `0`.

Шаг 5.7. В отчёт — таблица по серверам: вердикт в `probe-xray-only.txt` и в `probe-singbox.txt`.
Вывод одной фразой:

- есть серверы с вердиктом `OK` или `SLOW` только в `probe-singbox.txt` → «sing-box помогает у
  этого провайдера» и список таких серверов;
- есть серверы, у которых вердикт хуже в `probe-singbox.txt` (например, `OK` → `TIMEOUT`) →
  отметить и их: часть серверов sing-box ведёт хуже Xray (так бывает с REALITY и Vision);
- одинаково → «sing-box этому провайдеру не помогает».

## 6. Что шлюз делает сам

Шаг 6.1. Оставить режим `auto` (после шага 5.6) и подождать 30 минут (`sleep 1800`, можно
частями). За это время запасные серверы проверяются по расписанию.

Шаг 6.2. Собрать итог:

```bash
T=$(cat ~/xgw-0.1.12-test/install-time.txt)
sudo xgw servers > after/servers-auto.txt; grep -oE '\[(xray|xray\+frag|sb|sb\+frag|sb\+mux)\]' after/servers-auto.txt | sort | uniq -c
sudo journalctl -u xgw --since "$T" --no-pager -o cat | grep -E 'profile:|fragment:|singbox:|профиль обхода|sing-box' > after/events.txt; wc -l after/events.txt
sudo journalctl -u xgw --since "$T" --no-pager -o cat | grep -E ' скан ' | awk '{print $6, $7}' | sort | uniq -c > after/scans.txt; cat after/scans.txt
systemctl show xgw-xray xgw-singbox -p ExecMainStartTimestamp
```

Ожидается:

- в `events.txt` могут быть строки «profile: «имя» отвечает на профиле «…» — он закреплён» и
  «profile: … не отвечает на профиле «…» — пробую «…»» (если какой-то запасной блокировался);
  «apply: профиль обхода (…): применено через API без перезапуска»;
- время запуска `xgw-xray` и `xgw-singbox` — **раньше** этих событий (ядра не перезапускались);
- уведомлений на рабочий стол и в Telegram о смене профилей нет.

Если событий `profile:` нет совсем: это не ошибка, если все запасные отвечают на обычном
профиле (в `scans.txt` только `OK`/`SLOW`). Записать.

Шаг 6.3. В отчёт — таблица: имя сервера, вердикт до, профиль после (из `events.txt`), и
сколько серверов на каком профиле (первая команда).

## 7. Слежение за sing-box

**Спроси заказчика:** «Сейчас на минуту отключу второе ядро; интернет останется, но
соединения через серверы на sing-box оборвутся. Можно?» Дождись согласия. Если сейчас
основной сервер (в `sudo xgw status` строка «Основной») на `[sb]`, соединения через него
оборвутся на несколько секунд.

Шаг 7.1:

```bash
systemctl show xgw-singbox -p MainPID --value | tee before/singbox-pid.txt; sudo kill -9 $(cat before/singbox-pid.txt); sleep 60; systemctl is-active xgw-singbox; systemctl show xgw-singbox -p MainPID --value
```

Ожидается: после минуты `active` и **другой** номер процесса (systemd или демон его поднял).
Затем `sudo xgw status | head -12` — состояние `HEALTHY` или `DEGRADED`, интернет работает.

Шаг 7.2. События:

```bash
T=$(cat ~/xgw-0.1.12-test/install-time.txt); sudo journalctl -u xgw --since "$T" --no-pager -o cat | grep -E 'sing-box' | tail -8
```

Ожидается: допустима строка «sing-box не отвечал — служба перезапущена» (если systemd не успел
раньше демона). Записать, что видно.

## 8. Нет ли секретов в журналах

Шаг 8.1:

```bash
sudo xgw logs --export --out ~/xgw-0.1.12-test/export.tgz && mkdir -p ~/xgw-0.1.12-test/export && tar -xzf ~/xgw-0.1.12-test/export.tgz -C ~/xgw-0.1.12-test/export && ls ~/xgw-0.1.12-test/export/*/ | head -20
```

Шаг 8.2. Поиск секретов в архиве:

```bash
cd ~/xgw-0.1.12-test/export && grep -rnE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|vless://|vmess://|trojan://|hysteria2://|tuic://|anytls://|wireguard://|"private_key": "[^*]|"pre_shared_key": "[^*]|"secret": "[^*]|"password": "[^*]' . | head -10; echo "найдено: $(grep -rnE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|vless://|"password": "[^*]|"private_key": "[^*]' . | wc -l)"; cd ~/xgw-0.1.12-test
```

Ожидается: `найдено: 0`; в файле `singbox-config.json` пароли и ключи — `***`.
Если что-то нашлось — **не копировать** найденное в отчёт; написать «найдены секреты в
<имя файла>» и сообщить заказчику сразу.

## 9. Итоговое состояние

Шаг 9.1:

```bash
systemctl is-active xgw-net xgw-xray xgw-singbox xgw xgw-dhcp; sudo grep -c '^\[core\]' /etc/xgw/config.toml; sudo xgw diag | tail -1; sudo xgw status | head -5; rm -rf ~/xgw-0.1.12-test/export ~/xgw-0.1.12-test/export.tgz
```

Ожидается: пять `active` (`xgw-singbox` — `inactive` допустим, если конфига sing-box нет),
`0`, «FAIL — 0». Телефон и устройства заказчика — «через VPN».

## 10. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.12-<ГГГГ-ММ-ДД>.md` в репозитории. Заполни бланк:

```markdown
# Отчёт об испытаниях XGW 0.1.12 на реальной машине

Код: <хеш>. Установка: <время>, код <0/…>.

## Итог
<3–5 предложений: что работает, что нет; помогает ли sing-box у этого провайдера>

## Кейсы
| Шаг | Результат | Кратко |
|---|---|---|
| 1.3 протоколы в подписках | | <есть ли hysteria2/tuic/anytls/wireguard> |
| 2 установка и sing-box | пройден / нет | |
| 3 службы, метки, diag | пройден / нет | <сколько серверов на каких метках> |
| 4 трафик через sing-box | пройден / нет | <тот же адрес выхода после возврата: да/нет> |
| 5 sing-box против Xray | помогает / не помогает / хуже | |
| 6 профили сами | | <сколько серверов сменили профиль> |
| 7 слежение | пройден / нет | <за сколько секунд поднялся> |
| 8 секреты в журналах | 0 / найдены | |

## Шаг 3.3 — панель
<что видит заказчик>

## Шаг 5 — sing-box и Xray
| Сервер | Подписка | Xray | sing-box |
|---|---|---|---|
Вывод: <фраза из шага 5.7>.

## Шаг 6 — профили, выбранные шлюзом
| Сервер | Вердикт до | Профиль после | Событие |
|---|---|---|---|

## Дефекты
<для каждого: как повторить, что ожидалось, что получилось>

## Что не проверено и почему

## Итоговое состояние машины
```

Перед коммитом проверь, что в отчёте нет секретов:

```bash
grep -nE 'vless://|vmess://|trojan://|ss://|hysteria2://|[0-9a-f]{8}-[0-9a-f]{4}-|token|/sub/' docs/TEST-REPORT-REAL-MACHINE-0.1.12-*.md
```

Ожидается: пусто. Если что-то нашлось — убрать из отчёта.

Коммит только отчёта: `git add docs/TEST-REPORT-REAL-MACHINE-0.1.12-*.md && git commit -m
"Отчёт об испытаниях XGW 0.1.12 на реальной машине" && git push`.
