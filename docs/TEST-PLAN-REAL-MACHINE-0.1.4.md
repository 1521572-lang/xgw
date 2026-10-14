# Программа испытаний XGW 0.1.4 на реальной машине

Задание для модели-тестировщика. Машина та же, что в отчёте
`docs/TEST-REPORT-REAL-MACHINE-2026-10-14.md` (дальше — «прошлый отчёт»): ThinkCentre,
Ubuntu 24.04.5 LTS, на ней сейчас стоит XGW 0.1.3. Задача — поставить 0.1.4 поверх, проверить
исправления дефектов F1–F12 из прошлого отчёта и убедиться, что ничего из уже работавшего не
сломалось. Итог — новый отчёт в том же формате (раздел 8).

Читать до начала работы: README (разделы «Установка», «Перехват трафика», «Контейнеры
Docker», «Проверки серверов», «Службы и файлы», «Частые проблемы»), ASSUMPTIONS пп. 170–175 —
там описано, что и почему изменилось, и что **не проверено** — именно это и нужно проверить.

## 0. Правила работы

Нарушение любого пункта — повод остановиться и написать об этом в отчёте, а не продолжать.

1. **Сеть меняется только командами XGW** (`xgw install`, `enable`, `disable`, `net up`,
   `apply`, `uninstall`) и правкой `/etc/xgw/config.toml`. Никаких `nft flush ruleset`, никаких
   ручных правок чужих таблиц nftables, правил ufw и Docker. Исключения, разрешённые этой
   программой, названы в кейсах явно.
2. **Аварийный выход всегда под рукой**: `sudo xgw disable` — прямой интернет за секунды.
   Если в любом кейсе интернет на машине или у устройства в LAN пропал больше чем на
   2 минуты и это не ожидаемое поведение кейса — `sudo xgw disable`, записать время, вывод
   `sudo xgw status`, `sudo xgw diag`, `sudo journalctl -u xgw -u xgw-xray --since -15min` и
   оформить дефект.
3. **Доступ к машине не только по сети.** Перед кейсами REAL-10, REAL-12 и REAL-17
   (перезагрузка, недоступный адрес проверки) убедиться, что есть локальная консоль или
   другой путь, не зависящий от перехвата.
4. **Секреты в отчёт не попадают**: адреса подписок, UUID, пароли, ключи Reality, токены
   панели, страницы статуса и Telegram. Имена серверов и адреса VPN-узлов — можно. Перед
   коммитом отчёта — `grep` по нему на `vless://`, `vmess://`, `trojan://`, `ss://`, `token=`,
   части UUID своих подписок.
5. **Ничего не «чинить» в коде XGW.** Найденное — дефект в отчёте (что сделали, что
   ожидали, что получили, вывод команд). Обходной путь можно применить, только если без
   него дальше не пройти, и он описывается в отчёте.
6. **Закрепление сервера (`xgw pin`) — только в кейсе REAL-13**, и после него — `xgw unpin`.
7. Telegram с настоящим токеном не проверяется (как и в прошлый раз).
8. Windows-версии больше нет (ASSUMPTIONS, п. 175): ничего в Windows не проверяется.

## 1. Что изменилось в 0.1.4 (что проверять)

| Дефект прошлого отчёта | Что сделано | Кейс |
|---|---|---|
| F1 — LEAK заслонял «не отвечает probe.url», XGW менял живые серверы, интернет пропал | сканы и замены ждут по самому признаку, а не по имени состояния; ядро на время недоступного probe.url пробует серверы по запасному адресу | REAL-12 |
| F2 — признак «не отвечает probe.url» требовал одну ошибку у всех | признак — «файл не получил ни один сервер», ошибки могут быть разными; `xgw probe --all` подсказывает при одной ошибке у 80 % | REAL-12 |
| F3 — ложный совет урезать проверки при неизвестном размере пробы | пока размер неизвестен — без предупреждения, с пометкой «наугад» | REAL-12 |
| F4 — контейнеры Docker мимо VPN | `capture.containers = true` (по умолчанию): метка и маршрут в TUN-интерфейс | REAL-11 |
| F5 — `xgw status` молчит об остановленном демоне | первая строка «СЛУЖБА xgw НЕ РАБОТАЕТ», код возврата 3 | REAL-14 |
| F6 — LEAK каждые 20 с перегружал правила и писал событие | раз на проверку утечки; сервер, сам выходящий в RU, меняется на запасной | REAL-13 |
| F7 — `probe.url_fallback` не использовался | запасной адрес проб ядра; без него — `probe.trace_url` | REAL-12 |
| F8 — остаётся `xgwtun0` после возврата на TPROXY | убирается сам, если не нужен контейнерам | REAL-15 |
| F9–F11 — стенд «одноразовой машины» на этом хосте | абсолютный путь к Xray, копирование поверх работающего, Docker хоста в контейнере замаскирован, IPv6 на `wan0` | REAL-16 |
| F12 — `ubuntu-fan` ломает DHCP после перезагрузки | своя служба `xgw-dhcp` со своим конфигом, `/etc/dnsmasq.d` не читается | REAL-09, REAL-10 |

## 2. Стенд и исходное состояние

Из прошлого отчёта (проверить, что так и есть, и записать в таблицу стенда):

- WAN `enp3s0f0`, 192.168.50.24/24, шлюз провайдера 192.168.50.1;
- LAN `enp4s0`, 192.168.60.1/24 **плюс временный адрес 192.168.137.1/24**, добавленный в
  профиль `xgw-lan` вручную (прошлый отчёт, §8 п. 1);
- LAN-клиент — роутер `10:71:00:ce:58:48` со статическим WAN 192.168.137.2 и своим NAT;
- Docker (`docker.io` 29.1.3) установлен и запущен;
- файл пакета ubuntu-fan убран в `/root/xgw-config-backup/ubuntu-fan.disabled`;
- XGW 0.1.3, `capture.method = "tproxy"`, перехват включён, две подписки заказчика.

### 2.1. Снимок «до»

Сохранить в каталог, например `~/xgw-0.1.4-test/before/` (в отчёт — только выводы, без
секретов):

```bash
sudo xgw status > status.txt; echo "код $?" >> status.txt
sudo xgw diag > diag.txt
sudo nft list ruleset > nft.txt
ip rule show > ip-rule.txt; ip route show table all > ip-route.txt
ip -br addr > ip-addr.txt; ip -br link > ip-link.txt
nmcli -t -f NAME,UUID,DEVICE,AUTOCONNECT connection show > nm.txt
systemctl is-active xgw-net xgw-xray xgw dnsmasq > units.txt
systemctl is-enabled xgw-net xgw-xray xgw dnsmasq >> units.txt
ls -la /etc/dnsmasq.d/ > dnsmasq.d.txt
sudo cat /var/lib/xgw/backup/install.json | python3 -m json.tool > journal.json
sudo cp -a /etc/xgw ~/xgw-0.1.4-test/before/etc-xgw   # полная копия настроек — на откат
docker ps -a > docker.txt; docker network ls >> docker.txt
```

### 2.2. Роутер в LAN — до обновления

**Важно:** повторная установка переписывает адреса профиля `xgw-lan` по `lan_address`
(192.168.60.1/24), и временный 192.168.137.1/24 пропадёт — роутер со статическим WAN
останется без шлюза. Поэтому до обновления:

- **предпочтительно:** переключить WAN роутера на DHCP. Тогда он получит адрес
  192.168.60.100–200 от XGW — заодно проверяется то, что в прошлый раз проверить не удалось
  (выдача адреса по DHCP, REAL-05 п. 1);
- если это невозможно — записать, как вернуть адрес после установки (прошлый отчёт, §8
  п. 1), и в отчёте отметить, что DHCP снова не проверен на настоящем устройстве. В этом
  случае для REAL-10 нужен другой DHCP-клиент в LAN: ноутбук или телефон кабелем/через
  точку доступа в `enp4s0`.

## 3. Формат каждого кейса в отчёте

Для каждого кейса: что сделано (команды), что ожидалось, что получено (выводы, время),
итог — **пройден / пройден частично / не пройден / не выполнялся** с причиной. Наблюдения на
время (например, «20 минут без замен») — с отметками времени.

## 4. Кейсы

### REAL-09. Обновление 0.1.3 → 0.1.4 и перевод DHCP на свою службу (F12)

1. `cd <каталог репозитория> && git pull` — коммит, в котором `src/xgw/__init__.py`
   говорит `0.1.4`. Записать хеш коммита.
2. Установка поверх: `sudo sh packaging/install.sh --yes` (или, как в прошлый раз,
   `sudo PYTHONPATH=src python3 -P -m xgw install --yes`). Сохранить вывод целиком.
3. Ожидается в выводе:
   - в плане: «DHCP … своя служба xgw-dhcp (dnsmasq, /etc/xgw/dnsmasq.conf)»; про
     контейнеры — «перехват: сеть enp4s0, эта машина и контейнеры Docker (docker0, br-*)»;
   - шаг «… DHCP теперь раздаёт своя служба xgw-dhcp» (`dnsmasq.service` перезапущен или
     остановлен — в зависимости от того, был ли он до XGW, см. журнал из §2.1);
   - «DHCP на enp4s0: служба xgw-dhcp (dnsmasq)», «XGW установлен».
4. Проверить после установки:
   - `systemctl is-active xgw-dhcp` → `active`; `systemctl is-enabled xgw-dhcp` → `enabled`;
   - `ls /etc/dnsmasq.d/` — файла `xgw.conf` нет;
   - `cat /etc/xgw/dnsmasq.conf` — `port=0`, `interface=enp4s0`, `bind-dynamic`,
     `user=dnsmasq`, `dhcp-leasefile=/var/lib/xgw/dhcp.leases`;
   - `systemctl is-active dnsmasq; systemctl is-enabled dnsmasq` — состояние, каким оно было
     **до первой установки XGW** (запись `"dnsmasq"` в журнале из §2.1: если там
     `"package": true`, служба должна быть выключена и не включаться при загрузке);
   - в `/var/lib/xgw/backup/install.json` больше нет ключа `"dnsmasq"`;
   - `sudo ss -lunp 'sport = :67'` — слушает `dnsmasq`, и это процесс службы `xgw-dhcp`
     (`systemctl status xgw-dhcp` показывает тот же PID);
   - `/var/lib/xgw/dhcp.leases` есть (аренды перенесены из `/var/lib/misc/dnsmasq.leases`,
     если там что-то было);
   - `sudo xgw status` — `HEALTHY`, «Перехват: включён — сеть enp4s0, эта машина и
     контейнеры Docker»; `sudo xgw diag` — FAIL нет, строка «Службы: … xgw-dhcp работают».
5. Роутер (§2.2): получил адрес по DHCP (`/var/lib/xgw/dhcp.leases`,
   `journalctl -u xgw-dhcp`), устройства за ним выходят в интернет через VPN (как в
   REAL-05 прошлого отчёта).

### REAL-10. `ubuntu-fan` в `/etc/dnsmasq.d` и перезагрузка (F12)

1. Вернуть файл пакета на место:
   `sudo cp /root/xgw-config-backup/ubuntu-fan.disabled /etc/dnsmasq.d/ubuntu-fan`
   (это исходный файл пакета, его возврат разрешён этой программой). `grep -n bind
   /etc/dnsmasq.d/ubuntu-fan` — записать, что в нём.
2. Без перезагрузки: `sudo systemctl restart xgw-dhcp` → `active`, в
   `journalctl -u xgw-dhcp -n 30` нет `cannot set --bind-interfaces and --bind-dynamic`.
3. Перезагрузка машины (`sudo reboot`). Как и в прошлый раз, удобно поставить разовую
   службу, которая через 60 с после загрузки пишет в файл: состояние
   `xgw-net xgw-xray xgw xgw-dhcp dnsmasq`, `xgw status`, внешний адрес машины, `nft list
   table ip xgw | grep -c tproxy`, `journalctl -u xgw-dhcp -b`, итог `xgw diag`. После
   снятия показаний — отключить и удалить её.
4. Ожидается: все четыре службы XGW `active`; `xgw-dhcp` поднялся сам; DHCP-клиент в LAN
   (роутер с WAN по DHCP либо другое устройство) получает адрес 192.168.60.x со шлюзом и
   DNS 192.168.60.1 (`journalctl -u xgw-dhcp -b | grep DHCPACK`); `xgw diag` — FAIL нет.
5. Файл `ubuntu-fan` оставить на месте до конца испытаний (это и есть «машина с Docker»).

### REAL-11. Контейнеры Docker через VPN (F4)

Предусловие: Docker запущен (`systemctl is-active docker`).

1. Устройство перехвата:
   - `ip rule show` — есть `fwmark 0x3 lookup 101`;
   - `ip route show table 101` — `default dev xgwtun0` и `blackhole default metric 4096`;
   - `ip -br link show xgwtun0` — интерфейс есть;
   - `sudo python3 -c "import json;print([i['tag'] for i in json.load(open('/etc/xgw/xray/config.json'))['inbounds']])"`
     — среди inbound'ов есть `tun-in` (при `capture.method = "tproxy"`);
   - `sudo nft list table ip xgw` — цепочка `containers` с `meta mark set 0x00000003`, в
     `prerouting` — `iifname "docker0" goto containers` и `iifname "br-*" goto containers`;
   - `cat /proc/sys/net/bridge/bridge-nf-call-iptables` — записать значение (у Docker
     обычно 1; именно с ним TPROXY не работал, см. ASSUMPTIONS п. 171).
2. Выход контейнера:
   - `docker run --rm alpine wget -qO- https://ifconfig.me` — адрес VPN-узла, **не**
     46.242.12.248 (провайдер); тот же запрос с самой машины — тот же или другой VPN-узел;
   - в журнале Xray (`journalctl -u xgw-xray -n 50`) — `[tun-in -> proxy-…]` в момент запроса;
   - DNS: `docker run --rm alpine nslookup example.com` — ответ есть; в журнале Xray —
     `tun-in -> dns-out`;
   - сеть `docker network create`: `docker network create xgwtest && docker run --rm
     --network xgwtest alpine wget -qO- https://ifconfig.me` — адрес VPN; затем
     `docker network rm xgwtest`.
3. Опубликованный порт контейнера (ответы не должны уходить в Xray):
   - `docker run -d --rm --name xgwpub -p 18080:8080 alpine sh -c 'while true; do printf
     "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok" | nc -l -p 8080; done'`;
   - с **другого устройства в сети провайдера** (192.168.50.0/24): `curl
     http://192.168.50.24:18080/` → `ok`. Если ufw закрывает порт — записать это (ufw и
     опубликованные порты Docker — не дело XGW), правила ufw не трогать, попробовать с
     самой машины `curl http://192.168.50.24:18080/` и отметить, что внешняя проверка не
     выполнена;
   - `docker stop xgwpub`.
4. `sudo xgw disable` → контейнер выходит с адресом провайдера; `sudo xgw enable` → снова
   VPN. Время переключения записать.
5. Docker сам работает: `docker pull alpine:3.20` проходит (dockerd — процесс машины, идёт
   через VPN); два контейнера в одной сети видят друг друга (`docker network create t2;
   docker run -d --rm --name a --network t2 alpine sleep 60; docker run --rm --network t2
   alpine ping -c1 a`; `docker network rm t2` после остановки `a`).
6. Выключатель: в `/etc/xgw/config.toml` в `[capture]` — `containers = false`, затем
   `sudo xgw net up` и `sudo xgw apply --now`. Ожидается: контейнер выходит с адресом
   провайдера, сама машина и LAN — через VPN; в `ip rule` нет `fwmark 0x3`. Вернуть
   `containers = true`, `sudo xgw net up`, `sudo xgw apply --now` → снова VPN.
7. «Docker появился после XGW» (необязательно, если сложно): `sudo systemctl stop docker
   docker.socket`, `sudo ip link del docker0`, `capture.containers` оставить `true`,
   `sudo xgw apply --now`; убедиться, что `tun-in` пропал из конфига Xray (на перезапуске
   Docker нет). Затем `sudo systemctl start docker` и **без команд XGW** ждать до 2 минут:
   в `sudo xgw status` / журнале демона — событие «появился Docker — контейнеры пойдут через
   VPN, Xray перезапускается», `tun-in` в конфиге снова есть, `docker run --rm alpine wget
   -qO- https://ifconfig.me` — адрес VPN. В промежутке контейнер без интернета (это
   ожидаемо), но **не** с адресом провайдера.

### REAL-12. Недоступный `probe.url` (F1, F2, F3, F7)

Это тот кейс, на котором в прошлый раз пропал интернет. Перед началом — правило 0.3.

1. Подготовка: `sudo xgw status` — `HEALTHY`; записать участников и выбранный сервер.
2. Подмена адреса: в `/etc/xgw/config.toml` `[probe] url = "https://127.0.0.1:9999/bad"`,
   `url_fallback` пустой (по умолчанию). `sudo xgw apply --now`.
3. Наблюдение **30 минут** (каждую минуту — `curl -s https://ifconfig.me` с машины, запрос
   с устройства за роутером — хотя бы раз в 5 минут; `sudo xgw status` раз в 5 минут):
   - интернет на машине и у устройства **не пропадает** (допустимы секунды на перезапуск
     Xray при переключении адреса проб);
   - в течение нескольких минут: состояние `PROBE_TARGET_UNREACHABLE` (или `LEAK`, если
     выход в RU, — тогда строка «Внимание: пробы всех серверов падают — вероятно, недоступен
     сам probe.url …» должна быть в статусе всё равно);
   - событие «ядро пробует серверы по https://www.cloudflare.com/cdn-cgi/trace …» и
     `sudo python3 -c "import json;print(json.load(open('/etc/xgw/xray/config.json'))['burstObservatory']['pingConfig']['destination'])"`
     — `trace_url`, а не `127.0.0.1:9999`;
   - **нет** событий `rotation` и перехода в `ALL_DEAD` за всё время (`sudo xgw status` →
     «Последние события», `journalctl -u xgw --since -35min | grep -E "rotation|ALL_DEAD"`);
   - участники через 30 минут — те же, что в п. 1;
   - участники в статусе живы (ядро пробует их по `trace_url`).
4. `sudo xgw probe --all` — в stderr «Внимание: пробы всех серверов падают — вероятно,
   недоступен сам probe.url (… у N из M)» (если одна ошибка у 80 % серверов и ни один не
   получил файл); записать, какие вердикты.
5. `sudo xgw diag` — `FAIL probe.url: Внимание: …` с советом; строка «Трафик проверок» — без
   WARN о превышении лимита, с пометкой, что размер пробы пока неизвестен (F3).
6. Возврат: прежний `url` (из `config.example.toml`), `sudo xgw apply --now`. Ожидается за
   1–2 шага watchdog: событие «probe.url снова отвечает — проверки серверов возобновлены»,
   «ядро снова пробует серверы по probe.url», `destination` — снова прежний адрес,
   `HEALTHY`.
7. Вариант с запасным адресом: `url_fallback` = любой доступный файл (например, тот же
   адрес по умолчанию, но **другой** файл с того же CDN — подобрать и записать), `url` снова
   недоступный. Ожидается: `destination` = `url_fallback`. Вернуть всё как было.

### REAL-13. Утечка: сервер, выходящий в RU (F6)

В прошлый раз балансировщик сам выбрал российский узел (186 мс). Проверить два пути.

1. **Закреплённый вручную** (правило 0.6): найти в `sudo xgw servers` участника, который
   выходит в RU (по имени/флагу; если среди участников такого нет — запасного не трогать,
   отметить «не выполнялся»). `sudo xgw pin <тег> --ttl 15m`. Ждать до 6 минут (проверка утечки —
   раз в 5 минут):
   - состояние `LEAK`; событие «выход в RU: закреплённый вручную сервер <тег> сам выходит в
     RU — снимите закрепление: xgw unpin» — **одно**, а не раз в 20 секунд (посмотреть
     «Последние события» через 5 минут после первого);
   - закреплённый сервер не заменён;
   - `sudo xgw unpin`.
2. **Выбранный балансировщиком** (если такой случай встретится сам за время испытаний — а
   он вероятен, раз в подписке есть быстрый RU-узел): событие «выход в RU: сервер <тег> сам
   выходит в RU — меняю его на запасной», затем `rotation: замена участников: … (сами
   выходят в RU: <тег>)`; через ≤ 6 минут — `HEALTHY`, внешний адрес не RU. Если за время
   испытаний случай не встретился — так и записать.
3. В обоих случаях: в `journalctl -u xgw` за время LEAK нет сообщений о загрузке правил
   перехвата на каждом шаге.

### REAL-14. `xgw status` при остановленном демоне (F5)

1. `sudo systemctl stop xgw`; сразу же `sudo xgw status; echo "код $?"` — первая строка
   «Состояние: СЛУЖБА xgw НЕ РАБОТАЕТ — …», код **3**; `sudo xgw status --json | grep
   daemon_down` → `true`.
2. `sudo systemctl start xgw`; через 30 с — обычный статус, код 0.

### REAL-15. Интерфейс TUN после возврата на TPROXY (F8)

1. `capture.method = "tun"`, `sudo xgw apply --now`, проверить «эта машина через TUN».
2. Вернуть `method = "tproxy"`, `sudo xgw apply --now`; через шаг watchdog:
   - при `containers = true` и запущенном Docker интерфейс `xgwtun0` **остаётся** — он нужен
     контейнерам (это ожидаемо, не дефект); `tun-in` в конфиге есть;
   - при `containers = false` (временно, как в REAL-11 п. 6) — интерфейс пропадает сам,
     в событиях «интерфейс xgwtun0 убран: capture.method больше не tun».
3. Вернуть `containers = true`.

### REAL-16. Стенды на этой машине (F9–F11)

XGW установлен, dnsmasq и Docker стоят — как в прошлый раз, хост не чистить.

```bash
cd <репозиторий>
.venv/bin/python -m pytest tests/ --ignore=tests/stand -q
sudo -E XGW_XRAY_BIN=tools/xray/xray .venv/bin/python -m pytest tests/stand/test_machine.py -q
sudo -E XGW_XRAY_BIN=tools/xray/xray .venv/bin/python -m pytest tests/stand/test_stand_docker.py -q
sudo -E XGW_XRAY_BIN=tools/xray/xray .venv/bin/python -m pytest tests/stand -q \
    --ignore=tests/stand/test_machine.py
```

Ожидается: юнит-тесты — 0 падений; `test_machine.py` — **23 passed** с **относительным**
путём `tools/xray/xray` (F9); `test_stand_docker.py` — 3 passed; остальные стенды — 0
падений. Любое падение — с полным текстом в отчёт (не обрезать до первой строки: в прошлый
раз за причину была принята первая строка вывода, а не настоящая ошибка). После прогона
`test_machine.py` убедиться, что машина не изменилась: `sudo xgw status` — как до прогона,
`systemctl is-active docker` — `active`.

### REAL-17. Повтор прошлых кейсов (регрессия)

Коротко, по программе прошлого раза:

- REAL-01 — предохранитель TUN (`enable` без `tun-in` отказывает, `apply --now`
  перезапускает сразу, самовосстановление демоном);
- REAL-02 — пересечение подсетей (`diag` FAIL, `install` и с `--force` отказывается);
- REAL-05 — устройство в LAN: выход через VPN, перехват DNS, `disable`/`enable`;
- REAL-06 — соседство с Docker: таблицы Docker и XGW не мешают друг другу,
  «Файрвол: ufw и Docker перехвату не мешают; контейнеры Docker — через VPN»;
- REAL-08 — перезагрузка уже сделана в REAL-10, отдельно не нужна.

### REAL-18. Вход в панель без терминала (0.1.3, если есть графический сеанс)

Только если на машине есть рабочий стол и вы можете им управлять; иначе — «не
выполнялся». Правая кнопка по ярлыку «XGW» → «Войти заново»: окно пароля Ubuntu, после
пароля панель открывается в браузере с выполненным входом; повторное открытие той же
одноразовой ссылки — отказ.

## 5. Итоговое состояние машины

После испытаний машина должна остаться в рабочем виде:

- XGW 0.1.4, `capture.method = "tproxy"`, `containers = true`, перехват включён,
  `probe.url` — по умолчанию, `url_fallback` пустой, закреплений нет;
- `/etc/dnsmasq.d/ubuntu-fan` на месте (это файл пакета);
- роутер — в режиме, о котором договорились (WAN по DHCP либо прежний статический адрес);
  если остался ручной адрес 192.168.137.1/24 — указать в отчёте;
- разовых служб и тестовых контейнеров/сетей Docker нет;
- `sudo xgw status` — `HEALTHY`, `sudo xgw diag` — FAIL нет.

## 6. Если что-то пошло не так

| Ситуация | Что делать |
|---|---|
| Нет интернета больше 2 минут | `sudo xgw disable`, снять показания (правило 0.2), дефект |
| Установка 0.1.4 остановилась | вывод целиком в отчёт; сеть установка возвращает сама; повторить после исправления причины либо вернуть 0.1.3 копией из `before/etc-xgw` и `git checkout` прежнего коммита + `sudo xgw install --yes` |
| `xgw-dhcp` не запускается | `journalctl -u xgw-dhcp -b`, `sudo dnsmasq --test --conf-file=/etc/xgw/dnsmasq.conf`, `sudo ss -lunp 'sport = :67'` (кто держит порт) — в отчёт |
| Контейнеры без интернета дольше 2 минут при работающем Docker | `ip rule`, `ip route show table 101`, `ip -br link show xgwtun0`, inbound'ы конфига Xray, `journalctl -u xgw -n 100` — в отчёт; вернуть `containers = false` |
| После `docker`-команд пропал интернет у машины | `sudo xgw disable`, показания, дефект |

## 7. Чего не делать

- не удалять и не переустанавливать Docker, ubuntu-fan, NetworkManager;
- не менять `net.bridge.bridge-nf-call-iptables` и прочие sysctl вручную;
- не править `/etc/xgw/xray/config.json` руками (кроме REAL-01, как в прошлый раз);
- не коммитить ничего, кроме отчёта.

## 8. Отчёт

Файл `docs/TEST-REPORT-REAL-MACHINE-0.1.4-<ГГГГ-ММ-ДД>.md`, структура как у прошлого:

1. **Коротко** — что работает, что нет, сколько дефектов какой важности.
2. **Стенд** — таблица (машина, ядро, Python, WAN, LAN, LAN-клиент, Xray, XGW с хешем
   коммита, dnsmasq, Docker, `bridge-nf-call-iptables`, подписки — без адресов).
3. **Итоги** — таблица кейсов REAL-09…REAL-18 с итогом.
4. **Кейсы** — по разделу 3 этой программы.
5. **Дефекты** — нумерация с G1; для каждого: важность (высокий/средний/мелкий/косметика),
   шаги, ожидание, факт, выводы, предложение (если есть).
6. **Что не проверено и почему.**
7. **Отличия фактического стенда от этой программы.**
8. **Итоговое состояние машины** (раздел 5) и как вернуть временные изменения.

Отчёт закоммитить в `main` отдельным коммитом («Отчёт об испытаниях 0.1.4 на реальной
машине: …») и отправить на GitHub. Перед коммитом — проверка на секреты (правило 0.4).
