# XGW: архитектурный аудит и план доработок (Blueprint)

Основа — код 0.1.15 (`05a8c68`). Аудит идёт по пяти точкам отказа на Ubuntu 24.04 (ядро 6.8+,
nftables, systemd-resolved, cgroup2) и сверяется с эталонными клиентами: Mullvad (`talpid-core`),
Proton VPN, Tailscale (`net/netcheck`) и Amnezia VPN.

XGW — не настольный VPN-клиент, а **шлюз для всей сети**. Через него в интернет ходят LAN за
`lan_if`, сама машина и её контейнеры Docker. Поэтому каждый паттерн эталонов здесь переложен на
устройство шлюза. Что к шлюзу неприменимо, сказано прямо, с причиной (§1.3).

Документ самодостаточен: по нему каждая фаза (§3) пишется в один проход. Ссылки `файл:строка`
даны по `05a8c68`, пути — от корня репозитория (`src/xgw/…`).

---

## 1. Диагноз

### 1.1 Таблица

| Узел | Как сейчас | Проблема на Ubuntu 24.04 | Риск |
|---|---|---|---|
| Привилегии | Все внешние команды получают список аргументов, `shell=True` нет (`net/cmd.py:19-41`). pkexec вызывается только в `xgw panel --login` (`cli.py:889-934`, `desktop.py:118-134`). `xgw.service` работает от root с `CapabilityBoundingSet=CAP_NET_ADMIN CAP_SETUID CAP_SETGID`, `NoNewPrivileges` и `ProtectSystem=strict`; Xray и sing-box — от пользователя `xray`. | У `xgw-net.service` и `xgw-dhcp.service` нет ни одной защитной опции systemd: они root с полным набором возможностей. | низкий |
| IPC | Отдельного канала нет: CLI и демон делят файлы — `panel.json` (с блокировкой), `status.json`, `state.db` и `apply.lock`. Правки из CLI демон находит по mtime (`cli.py:619,698`). Панель и бот работают потоками демона и зовут его методы напрямую (`daemon.poke`, `daemon.py:378`). | Правка `xgw priority` или `xgw core` доходит до демона только на следующем шаге (до `watchdog.interval_s`). `xgw status` читает снимок, а не живое состояние. | средний |
| Состояние | Перечисление `State` (`watch/states.py:25-33`) пересчитывается из сигналов на каждом шаге (`states.py:78-106`, `daemon.py:510`). Ядра и демон перезапускает systemd (`Restart=always`), `_handle_xray_down` откатывает конфиг (`daemon.py:976-998`). `xgw-net` поднимает правила до `network-pre.target`. | Событий сети и сна демон не слушает. Смену WAN или Wi-Fi он заметит на следующем шаге, а при WAN_DOWN — только через 60 с (`daemon.py:396`). Пробуждение не обрабатывается: `net/sleep.py:25-47` лишь маскирует сон, и только когда настроен LAN. Жизненного цикла перехвата (подключается / работает / заблокирован) в состоянии нет: его приходится восстанавливать из `capture_info` и `held`. | средний |
| Фаервол | Только nftables. Таблицы `ip xgw` и `ip6 xgw6` заменяются атомарно (`table`/`delete table`/`table {…}`, `net/nft.py:363,429`), с проверкой `nft -c` (`nft.py:446-449`). `fail_mode = "closed"` по умолчанию, forward — `policy drop` (`nft.py:353`). | **(а)** Когда в применённом конфиге Xray нет `tproxy-in`/`tun-in` или нет интерфейса TUN, `Capture._load` загружает режим «off» (`capture.py:345-365`, `effective_mode` — `286-290`): трафик идёт **напрямую, мимо VPN, даже при `fail_mode = "closed"`**. **(б)** v4 и v6 загружаются двумя вызовами `nft -f` (`nft.py:457-463`): между ними правила обеих семей не согласованы. **(в)** После чужого `flush ruleset` (`nftables.service`, ручной `nft flush`) трафик течёт мимо VPN до ближайшего шага демона (`daemon.py:1085-1092`). | **высокий** (а), средний (б, в) |
| IPv6 | v6 из LAN и в LAN отбрасывается всегда (`nft.py:421-428`), RA и DHCPv6 в LAN нет. При `network.ipv6 = "off"` v6 самой машины выключается через NetworkManager (`ipv6.method disabled`) или sysctl (`nm.py:273-316`). | Когда WAN не под NetworkManager (или профиль netplan не `ignore`), v6 машины **остаётся включённым и не перехватывается**: XGW только предупреждает (`nm.py:283-303`). Защита держится на чужой настройке, а не на фаерволе. При `"proxy"` трафик на ULA (`fc00::/7`) уходит напрямую (`reserved6`). | средний |
| DNS | `/etc/resolv.conf`, systemd-resolved и `resolvectl` не трогаются. LAN получает от dnsmasq адрес шлюза (`dnsmasq.py:176,198`); любой порт 53 из LAN — TPROXY в Xray `dns-out` (`nft.py:283-284`, `builder.py:718`). Запросы самого resolved наружу помечаются в output и тоже попадают в `dns-out` (`nft.py:295-306`). | Утечки в текущей схеме нет, но **нет проверки**, что её нет. В режиме TUN (`capture.method = "tun"`) DNS машины держится только на перехвате порта 53; resolved о туннеле не знает. | низкий |
| Тесты | Стенд в двух режимах: loopback и netns (`tests/stand/stand.py:1-13`). Пространства `inet 5.5.5.1 ⇄ gw ⇄ lan 192.168.50.100`; veth создаются внутри них, forwarding выключен (`tests/stand/netns.py:8-61`), у стенда своя метка `0x5E` (`stand.py:46-49`). Одноразовая машина systemd-nspawn гоняет настоящие install и uninstall (`tests/stand/machine.py`). | Интернет хоста тесты не трогают — уровень эталонов уже есть. | — |
| Диагностика | `xgw diag` (`diag.py:125-158`): правила TPROXY проверяются в одноразовой netns (`unshare -n`), есть проверки ufw, Docker (DOCKER-USER), rp_filter, IPv6, служб, `probe.url`, bootstrap DNS. Watchdog собирает метрики observatory, сквозную загрузку, связь с провайдером и выход в «домашнюю» страну (`daemon.py:686-833`). | Нет проверок PMTU (PPPoE), проходимости UDP (нужна hysteria2 и TUIC), утечек DNS и IPv6. | средний |
| Протоколы | Интерфейса ядра нет. `parse_link` выбирает парсер цепочкой if/elif (`parsers/common.py:272-303`). Ядро сервера задаёт `ServerNode.capability` (`model.py:56-79`). Лестница обхода блокировок — `generator/profiles.py`: `xray:default → xray:fragment → singbox:default → singbox:tls_fragment → singbox:mux_padded`. | Ссылки AmneziaWG отклоняются (`parsers/wireguard.py:1-19`): sing-box 1.14.3 не знает `jc`/`s1`/`h1`. Третье ядро добавить некуда: знание о Xray и sing-box разбросано по `builder.py`, `singbox.py` и `profiles.py`. | средний |

### 1.2 Что уже на уровне эталонов — не трогать

- Атомарная замена своей таблицы: `table X` / `delete table X` / `table X {…}`, предварительная
  проверка `nft -c`, `flush ruleset` нигде не используется.
- Fail-closed при загрузке: `xgw-net.service` (`DefaultDependencies=no`, `Before=network-pre.target`)
  загружает правила раньше сети.
- Fail-closed при падении Xray: TPROXY не находит сокета, пакет LAN доходит до forward с
  `policy drop`, пакет машины остаётся без ответа (ASSUMPTIONS п. 75). Контейнеры при пропавшем TUN
  уходят в blackhole таблицы 101 (`net/iprule.py:208-220`).
- Привилегированные команды — только списком аргументов; панель защищена токеном, cookie HMAC,
  проверкой `Host`, `Origin`, `Sec-Fetch-Site` и заголовком `X-XGW-Panel` (`watch/panel.py:999-1095`).
- Изолированный netns-стенд и одноразовая машина.

### 1.3 Что к шлюзу неприменимо (и почему)

| Паттерн эталона | Почему не переносится |
|---|---|
| Тумблер Allow LAN (Mullvad) | LAN — это клиенты шлюза, им шлюз и так отвечает. Частные сети (`reserved4`: RFC1918, link-local, multicast) у машины всегда идут мимо Xray (`nft.py:283-284,300`). Свой тумблер нужен только в режиме blocked (§2.1), и там он включён всегда. |
| Отдельный привилегированный помощник с IPC и pkexec на каждую операцию (Mullvad, Proton) | Демон XGW уже сам root-служба с урезанными возможностями, GUI — страница в браузере на 127.0.0.1. pkexec нужен ровно в одном месте (вход в панель), так и сделано. Нужен лишь канал CLI → демон (§3, Ф2б). |
| DNS LAN-клиентов через systemd-resolved (Proton, Mullvad) | Клиенты LAN resolved шлюза не используют: их DNS — адрес шлюза (dnsmasq с `port=0`) и TPROXY порта 53 в Xray. resolved касается только DNS самой машины и только в режиме TUN (§2.2). |
| Split tunneling по приложениям на устройствах LAN | Шлюз не видит процессов на чужих устройствах — только адреса. Для LAN разделение идёт по адресам и подсетям (`network.bypass_hosts` уже принимает CIDR: `lan.py:234-258`, set `bypass4` с `flags interval` — `nft.py:227-232`). По приложениям — только для программ самой машины шлюза (§2.4б). |
| MSS clamp для TUN | TUN-вход Xray завершает TCP в своём стеке, и наружу идёт новое соединение Xray со своим MSS. Clamp нужен только трафику, который форвардится как есть (обход VPN), и он есть (`nft.py:343`). |
| WireGuard-ядро как основной туннель (Mullvad) | Основное ядро XGW — Xray (VLESS/REALITY и др.) с sing-box в помощь. AmneziaWG добавляется третьим ядром за Xray (§2.4в), а не вместо него. |

---

## 2. Спецификации

### 2.1 nftables: режим blocked, одна транзакция, IPv6 kill switch

**Решение заказчика перед Ф1.** Сейчас при отсутствии нужного inbound сеть работает напрямую: так
выбрано сознательно, чтобы шлюз «не остался без интернета» (`capture.py:348-353`). Предлагается
новая настройка `[capture] hold = "block" | "direct"`:
- `"block"` (рекомендуется, по умолчанию при `fail_mode = "closed"`): режим **blocked** — мимо VPN
  не уходит ничего. Обычно это секунды: демон тут же перезапускает Xray с новым конфигом.
- `"direct"`: прежнее поведение. При `fail_mode = "open"` всегда `"direct"`.

**Режимы `Capture`:** `on` (перехват), `off` (`xgw disable` — напрямую, с маскарадингом), `none`
(без LAN и без перехвата) и новый **`blocked`**. Blocked сохраняет связь с самим шлюзом (SSH, панель,
DHCP, NTP) и выход Xray (метка 2), а всё остальное отбивает с ответом — без таймаутов.

**Одна транзакция.** `nft.apply` склеивает текст обеих таблиц и подаёт его в один `nft -f -`.
Если в ядре нет IPv6 (`/proc/sys/net/ipv6` отсутствует, загрузка с `ipv6.disable=1`), загружается
только v4 и выдаётся предупреждение, как сейчас (`nft.py:458-463`).

Шаблон blocked (значения подставляет `Rules`: `lan0`, метки `0x1`/`0x2`, uid служб времени;
`reserved4` — тот же set, что в режиме on):

```nft
table ip xgw
delete table ip xgw
table ip xgw {
    set reserved4 {
        type ipv4_addr
        flags interval
        elements = { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16,
                     172.16.0.0/12, 192.168.0.0/16, 224.0.0.0/4, 240.0.0.0/4 }
    }
    set bypass4 {
        type ipv4_addr
        flags interval
    }
    set bypass_containers {                       # [capture] containers_bypass (Ф4)
        type ipv4_addr
        flags interval
    }

    # Машина: наружу — только Xray (метка 2) и служебное; остальное отбивается.
    chain block_output {
        type filter hook output priority filter; policy accept;
        oifname "lo" accept
        meta mark 0x2 accept                      # сокеты Xray/sing-box и прямые запросы XGW
        ct direction reply accept                 # ответы на входящие (SSH на шлюз, панель)
        fib daddr type local accept
        ip daddr @reserved4 meta l4proto != { tcp, udp } accept   # ping в LAN и т. п.
        ip daddr @reserved4 th dport != 53 accept # LAN, link-local, multicast (Allow LAN)
        udp sport 68 udp dport 67 accept          # DHCP-клиент WAN
        meta skuid 104 udp dport 123 accept       # chrony / timesyncd (Rules.time_uids)
        meta skuid 104 tcp dport 4460 accept      # NTS-KE
        meta l4proto tcp counter reject with tcp reset
        counter reject with icmp type admin-prohibited
    }

    # LAN и контейнеры: мимо VPN — только bypass4 и bypass_containers, как в режиме on.
    chain forward {
        type filter hook forward priority filter; policy drop;
        # Контейнеры: в режиме on их уводит в TUN цепочка containers (метка 3), а здесь её нет —
        # без этих правил docker0 → WAN прошёл бы правилом «чужой форвардинг» ниже. Между
        # мостами и внутри моста — можно. Список мостов — nft.CONTAINER_IFS (nft.py:62).
        iifname "docker0" oifname != "docker0" oifname != "br-*" ip saddr != @bypass_containers counter reject with icmp type admin-prohibited
        iifname "br-*" oifname != "docker0" oifname != "br-*" ip saddr != @bypass_containers counter reject with icmp type admin-prohibited
        iifname != "lan0" oifname != "lan0" accept      # чужой форвардинг (libvirt, контейнеры между собой)
        tcp flags syn tcp option maxseg size set rt mtu
        # Установленные соединения — только у тех, кому обход разрешён: сессии, открытые в
        # режиме off/open, в blocked не доживают по записи conntrack.
        iifname "lan0" ip saddr @bypass4 ct state established,related accept
        oifname "lan0" ip daddr @bypass4 ct state established,related accept
        iifname "lan0" oifname != "lan0" ip saddr @bypass4 counter accept
        iifname "lan0" counter reject with icmp type admin-prohibited
    }

    # DNS к шлюзу: устройства в обход — на прямой резолвер; остальным отвечает reject.
    chain dns_direct {
        type nat hook prerouting priority dstnat; policy accept;
        iifname "lan0" ip saddr @bypass4 meta l4proto { tcp, udp } th dport 53 fib daddr type local counter dnat to 77.88.8.8
    }
    chain postrouting {
        type nat hook postrouting priority srcnat; policy accept;
        iifname "lan0" oifname != "lan0" counter masquerade
    }
}

table ip6 xgw6
delete table ip6 xgw6
table ip6 xgw6 {
    # IPv6 kill switch машины: при network.ipv6 = "off" наружу не уходит ничего, что бы ни
    # решили NetworkManager и netplan. Тот же chain ставится и в режимах on и off.
    chain v6_guard {
        type filter hook output priority filter; policy accept;
        oifname "lo" accept
        meta mark 0x2 accept                        # сокеты Xray к серверам с адресом IPv6
        # Служебный ICMPv6, который шлёт само ядро (без метки и бывает на глобальный адрес):
        # ответы ND соседу, ошибки (packet-too-big и др.) — без них ломаются ND и PMTU.
        icmpv6 type { destination-unreachable, packet-too-big, time-exceeded, parameter-problem, nd-router-solicit, nd-router-advert, nd-neighbor-solicit, nd-neighbor-advert } accept
        ip6 daddr { fe80::/10, ff00::/8 } accept   # ND, RA, DHCPv6-клиент (ff02::1:2)
        ct direction reply accept
        meta l4proto tcp counter reject with tcp reset
        counter reject with icmpv6 type admin-prohibited
    }
    chain forward {
        type filter hook forward priority filter; policy accept;
        iifname "lan0" drop
        oifname "lan0" drop
    }
}
```

Правила:
- `v6_guard` загружается во всех режимах при `network.ipv6 = "off"`; при `"proxy"` его нет (v6
  перехватывается). При `"proxy"` в `reserved6` по умолчанию остаются только `fe80::/10` и
  `ff00::/8`, а ULA `fc00::/7` перехватывается, если не указан в `capture.exclude_cidrs`.
- В режиме blocked нет ни `prerouting`, ни `output` с меткой 1: маршрут `fwmark 1 → table 100`
  остаётся (`iprule.py:127-135`) и вреда не делает.
- DNS в blocked: самому XGW он не нужен. Адреса серверов Xray разрешает своим DNS
  (`sockopt.domainStrategy = "UseIPv4"`, `builder.py:516`), служебные запросы XGW — свой
  резолвер с меткой 2, `getaddrinfo` в коде нет. Остальные программы машины в blocked остаются
  без DNS: запросы resolved наружу идут без метки и отбиваются. Так и задумано — это утечка, а
  не служебный трафик. Инвариант для Ф1 — юнит-тест, который ищет по исходникам `src/xgw`
  вызовы `getaddrinfo`/`gethostbyname` и падает, если они появились.
- Уведомления в blocked доходят. Бот Telegram и уведомления ходят через `http-in` Xray, если тот
  жив, иначе напрямую с меткой 2 и своим резолвером (`watch/telegram.py:276-280`). Оба пути
  `block_output` пропускает: loopback и `meta mark 0x2`. Ф1 закрепляет это тестом: уведомление
  «перехват заблокирован» уходит в режиме blocked.
- Сессии, открытые до перехода: в forward установленные соединения пропускаются только для
  `@bypass4` (шаблон выше), у машины — только ответы (`ct direction reply`). Поэтому после
  перехода из off/open в blocked старые соединения обрываются с ICMP admin-prohibited. В
  режиме on этого не нужно: TPROXY в prerouting стоит раньше forward и уводит пакеты старых
  соединений в Xray. Сброс conntrack не используется: утилиты `conntrack` в Ubuntu по умолчанию
  нет.
- Проверка шаблона без ядра хоста: `unshare -n nft -c -f blocked.nft`. Тест — `nft.check` в
  `tests/test_nft.py` на FakeKernel и стенд (§3, Ф1).

Почему не `table inet` (Mullvad). TPROXY, FakeKernel (`tests/fakenet.py`) и все тесты написаны под
`ip`/`ip6`. Атомарность даёт и одна транзакция с двумя таблицами. Переход на `inet` переписал бы
всё это и ничего не добавил.

### 2.2 DNS: systemd-resolved только для TUN-режима машины

В режиме TPROXY ничего не меняется: перехват порта 53 в output уже закрывает утечку DNS машины.

В режиме `capture.method = "tun"` DNS машины привязывается к интерфейсу TUN — как Proton и
Mullvad привязывают его к своему интерфейсу. Тогда resolved отправляет все запросы в туннель и сам
откатывает настройку, когда интерфейс исчезает (Xray остановлен, `xgw disable`). Скрипты очистки
не нужны.

Новый модуль `src/xgw/net/resolved.py`; вызовы — через `busctl` (входит в systemd, без новых
зависимостей) и раннер `net/cmd.py`:

```python
RESOLVE1 = ("org.freedesktop.resolve1", "/org/freedesktop/resolve1",
            "org.freedesktop.resolve1.Manager")

def bind_link(ifname: str, dns_ip: str, runner: Runner) -> None:
    """DNS машины — через TUN: сервер dns_ip на линке, маршрутный домен «~.», линк по умолчанию."""
    index = socket.if_nametoindex(ifname)
    octets = [str(b) for b in ipaddress.IPv4Address(dns_ip).packed]
    runner(["busctl", "call", *RESOLVE1, "SetLinkDNS", "ia(iay)", str(index), "1",
            str(socket.AF_INET), "4", *octets])
    runner(["busctl", "call", *RESOLVE1, "SetLinkDomains", "ia(sb)", str(index), "1", "~.", "true"])
    runner(["busctl", "call", *RESOLVE1, "SetLinkDefaultRoute", "ib", str(index), "true"])
    runner(["busctl", "call", *RESOLVE1, "SetLinkDNSOverTLS", "is", str(index), "no"])

def revert_link(ifname: str, runner: Runner) -> None:
    runner(["busctl", "call", *RESOLVE1, "RevertLink", "i",
            str(socket.if_nametoindex(ifname))])

def available(runner: Runner) -> bool:
    """resolved запущен: `busctl status org.freedesktop.resolve1` без ошибки."""
```

- `dns_ip` — первый IPv4 из `dns.proxy_servers` (1.1.1.1). resolved шлёт запросы к серверу линка
  через этот интерфейс (`SO_BINDTOIFINDEX`), TUN-вход Xray принимает их, и правило
  `port 53 → dns-out` (`builder.py:718`) обрабатывает их как сейчас.
- Где вызывается: `Capture.restore_tun()` (`capture.py:408-432`, после каждого запуска Xray) и
  `_load("on")` при `rules.tun` — `bind_link`; `_load("off"|"blocked")` и `down()` —
  `revert_link` (ошибки глушатся: линка может уже не быть).
- Если resolved не запущен (`available` = False) — ничего не делается: остаётся перехват порта 53.
- В режиме TUN в цепочку `output` (`nft.py:295`) первым правилом ставится
  `oifname "<tun_name>" return`. Тогда запрос, который resolved уже отправил в TUN
  (`SO_BINDTOIFINDEX`), не получает метку 1 и не маршрутизируется второй раз по таблице 100.
  Доставку это не меняет (таблица 100 ведёт в тот же TUN), а лишний проход убирает.
- Ни `/etc/resolv.conf`, ни `/etc/systemd/resolved.conf` не меняются.

### 2.3 Жизненный цикл перехвата и события

**Две оси состояния.** Существующий `State` (HEALTHY … XRAY_DOWN) остаётся — это здоровье
выходов. Поверх него добавляется **жизненный цикл перехвата** (как туннель Mullvad):

```
             enable              Xray готов, inbound есть
   off ───────────────▶ connecting ─────────────────────▶ connected
    ▲                       │  ▲                              │
    │ disable               │  │ Xray снова готов              │ Xray down / нет inbound /
    │                       ▼  │                              ▼ правила пропали
    └──────────────────── blocked ◀───────────────────────────┘
                              │  fail_mode = "open", Xray down ≥ 60 с
                              ▼
                             open ──(Xray готов)──▶ connected
```

- **off** — `xgw disable`: сеть напрямую.
- **connecting** — правила on загружены, Xray только запускается (observatory ещё ничего не
  сообщил): трафик ждёт, наружу ничего.
- **connected** — правила on, `xray_ok`; дальше работает `State`.
- **blocked** — `hold = "block"` и нет inbound/TUN, либо XRAY_DOWN при `fail_mode = "closed"`:
  правила blocked (§2.1).
- **open** — `fail_mode = "open"`: временно напрямую (метка `/run/xgw/capture-open`, как сейчас).

Состояние вычисляет `Daemon._lifecycle()` на каждом шаге. Переход пишется в журнал и в `events`
SQLite (уведомление — только для `blocked` и `open`). Текущее значение кладётся в `status.json`
полем `capture.lifecycle`, его показывают `xgw status` и панель. Новых файлов состояния не
появляется.

**События, которые будят демон.** Сейчас пауза между шагами прерывается только `daemon.poke`
(`daemon.py:378,403-411`). Новый модуль `src/xgw/watch/events.py` слушает три потока, без
библиотек — через подпроцессы:

```python
class NetEvents:
    """Будит демон на событиях сети, сна и правил; сам ничего не меняет."""
    def __init__(self, wake: Callable[[str], None], runner_popen=subprocess.Popen) -> None: ...
    def start(self) -> None: ...   # три потока-читателя, перезапуск подпроцесса при выходе
    def stop(self) -> None: ...

SOURCES = {
    "net":   ["ip", "-o", "monitor", "link", "address", "route"],   # текст: -j здесь не действует
    "sleep": ["busctl", "--system", "monitor", "--json=short",
              "--match=type='signal',interface='org.freedesktop.login1.Manager',"
              "member='PrepareForSleep'"],
    "rules": ["nft", "monitor"],   # без фильтра: `monitor tables` не видит flush table и правил
}
```

- Чтение — обычный пайп (`stdout=subprocess.PIPE`, построчно). Проверено в одноразовой netns на
  Ubuntu 26.04 (nftables 1.1.6, iproute2, systemd `busctl`): все три программы отдают каждое
  событие сразу, без буферизации, так что псевдотерминал и `stdbuf` не нужны. Тест Ф2 закрепляет
  это: событие доходит до читателя ≤ 1 с, пока подпроцесс ещё работает.
- `wake(reason)` выставляет `Daemon.wake_reason` и `poke.set()`. Повторы гасятся окном 2 с
  (debounce: смена Wi-Fi даёт десятки строк `ip monitor`).
- `ip -o monitor` печатает по строке на событие. В разбор идут строки с `Deleted`, `state DOWN`,
  `state UP`, а также добавление и удаление маршрута `default`. Строки по `lo`, `xgwtun0` и мостам
  контейнеров не учитываются.
- **net** — внеочередной шаг: `_check_provider`, `_guard_capture`, `restore_tun`. При выходе из
  WAN_DOWN — сразу e2e, а не через 60 с.
- **sleep** — `PrepareForSleep false` (пробуждение): внеочередной шаг. На нём — `capture.up()`
  (правила и маршруты TUN), e2e, затем скан запасных (`scan_queue` целиком — auto-reconnect после
  сна) и обновление подписок, если `refresh_minutes` прошли во сне.
- **rules** — строка `nft monitor`, которая начинается с `delete` или `flush` и касается таблиц
  `ip xgw` / `ip6 xgw6`: `delete table`, `flush table`, `delete chain`, `delete rule`, а также
  `flush ruleset`. На неё — внеочередной `_guard_capture`. Окно утечки после чужого
  `flush ruleset` сжимается с `interval_s` до долей секунды.
  Свои загрузки не должны будить демон зря. Булев флаг не годится: события netlink приходят
  асинхронно, уже после того как `nft -f` вернулся, и флаг успеет сброситься. Поэтому
  `Capture` после каждого `nft.apply` ставит `ignore_rules_until = time.monotonic() + 1.0`.
  Событие в этом окне пропускается, а вне окна перед перезагрузкой всё равно проверяется
  `capture.loaded()`: если правила на месте, ничего не делается.
- Если программы нет (`busctl`, `nft` и `ip` есть в любой установке), источник пропускается с
  предупреждением в журнале.

**Проверка с учётом трафика (ложные падения под нагрузкой).** Когда LAN качает на всю ширину
канала, очередь растёт, и сквозная проба (`_check_e2e`, `daemon.py:770`) может опоздать. Демон
тогда засчитывает провал работающему туннелю. XRAY_DOWN это не касается: он ставится по API и
метрикам, а не по пробам (`daemon.py:686-760`). Но DEGRADED и ALL_DEAD при этом возможны.
- Счётчики уже есть: в конфиге Xray включены `statsOutboundUplink`/`statsOutboundDownlink`
  (`builder.py:779-782`).
- Перед тем как засчитать провал e2e (`e2e_fail_streak += 1`) или «мёртвого» по observatory
  **выбранному сейчас** участнику, демон берёт `outbound>>><tag>>>>traffic>>>downlink` этого
  участника через API (`statsquery`, без сброса) и сравнивает с прошлым шагом.
- Если за последние `watchdog.busy_window_s = 10` секунд через него пришло
  ≥ `watchdog.busy_bytes = 1 MiB`, провал не засчитывается: туннель заведомо жив. Пишется DEBUG
  «проба опоздала под нагрузкой: N МБ за 10 с». Счётчик провалов не растёт, но и не
  обнуляется.
- Запасных и скан это не касается: у них нет пользовательского трафика. Не касается и
  «заморозки» (FROZEN), когда трафика нет вовсе.
- Код: `Daemon._busy(tag) -> bool` (API `xraycore/api.py`), вызов в `_check_e2e` и при подсчёте
  мёртвых в `_signals`.

**Ф2б (можно отложить): канал CLI → демон.** `/run/xgw/control.sock` (`AF_UNIX`, `SOCK_STREAM`,
права 0600, проверка `SO_PEERCRED`: uid 0), по строке JSON на запрос:
`{"cmd": "state"} | {"cmd": "poke", "why": "priority"} | {"cmd": "refresh"}`. `xgw priority`,
`xgw core` и `xgw pin` после записи `panel.json` или базы шлют `poke`, `xgw status --live` берёт
`state`. Без сокета (демон остановлен) всё работает как сейчас — через файлы.

### 2.4 Три доработки

#### (а) netcheck: самодиагностика сети

`xgw diag --netcheck` (вместе с `--json`) добавляет группу «Сеть»; без флага diag работает как
сейчас. Модуль `src/xgw/netcheck.py`:

```python
def run(cfg: Config, paths: Paths, runner: Runner = cmd.run) -> list[diag.Check]: ...
```

`diag.Check` и уровни OK/WARN/FAIL — из `diag.py:53`. Проверки (каждая ≤ 5 с, независимы):

| Проверка | Как | FAIL / WARN |
|---|---|---|
| PMTU до сервера | Сначала контрольный `ping -m 0x2 -c 2 -W 2 -s 56 <адрес основного сервера>`: не прошёл — сервер не отвечает на ICMP, проверка пропускается (OK «ICMP на сервере закрыт, PMTU не проверен»). Прошёл — `ping -M do -m 0x2 -c 1 -W 2 -s N` для N = 1472, 1464, 1452, 1412 (`-m` — метка мимо VPN) | WARN, только если контрольный прошёл, а 1472 — нет: «путь до сервера меньше 1500 (PPPoE?) — …» |
| UDP напрямую | STUN Binding Request на `stun.l.google.com:19302` из сокета с `SO_MARK = mark_bypass` | WARN: «провайдер режет UDP — hysteria2 и TUIC работать не будут» |
| UDP через VPN | тот же запрос без метки, если `capture.local`; иначе через `socks-in` (UDP ASSOCIATE) | FAIL при on/connected |
| Утечка DNS | A-запрос `example.com` без метки на заведомо недостижимый адрес `192.0.2.53:53` (TEST-NET-1). Перехват порта 53 уводит его в Xray `dns-out`, и тот отвечает своим DNS; ушедший мимо запрос до TEST-NET не дойдёт. Только тип A: TXT-проверки вроде `o-o.myaddr.l.google.com` не годятся — `dns-out` по умолчанию отбрасывает запросы не A/AAAA (`nonIPQuery`; на Xray 26.10.10 проверить до кода) | ответ пришёл — OK; тайм-аут при connected — FAIL «DNS машины уходит мимо Xray» |
| Утечка IPv6 | при `network.ipv6 = "off"` — TCP-connect к `[2606:4700:4700::1111]:443` без метки | FAIL, если соединение установилось |
| Чужие правила | `nft -j list ruleset`: таблицы с `policy drop` в forward (Docker без `DOCKER-USER`), включённый `nftables.service` с `flush ruleset` в `/etc/nftables.conf`, цепочки ufw | WARN с готовой командой |
| rp_filter | `net.ipv4.conf.{all,<wan>,<tun>}.rp_filter` | перенести из `diag.py:425-433` |

Watchdog ничего из этого не запускает: это разовая проверка по запросу. В панели — кнопка
«Проверить сеть» на вкладке диагностики (действие `diag/netcheck`).

#### (б) Split tunneling

1. **LAN по адресам и подсетям** — уже есть: `network.bypass_hosts` принимает IPv4, CIDR и MAC со
   статической арендой (`lan.py:234-258`), панель — кнопку «мимо VPN». Доработка: тот же set для
   контейнеров. Новый `[capture] containers_bypass = ["172.18.0.0/16"]` → в цепочке `containers`
   правило `ip saddr @bypass_containers return` (`nft.py:256-265`).
2. **Программы самой машины — через cgroup2.** Unit `packaging/xgwdirect.slice` (без дефиса в
   имени: дефис в systemd означает вложенность), запускается при установке. В цепочку `output`
   (`nft.py:295`), вторым правилом после метки 2:

   ```nft
   socket cgroupv2 level 1 "xgwdirect.slice" counter return
   ```

   В `block_output` (§2.1) это правило не ставится: в blocked мимо VPN не уходит и `xgw direct-run`.
   Команда:

   ```
   sudo xgw direct-run -- <программа> [аргументы]
     → systemd-run --scope --slice=xgwdirect.slice --uid=$SUDO_UID --gid=$SUDO_GID --same-dir --collect -- …
   ```

   nft переводит путь cgroup в inode при загрузке: если slice нет, вся транзакция падает. Отсюда
   три правила.
   - **Правило только при существующем slice.** `Rules.direct_slice` заполняется, лишь когда
     есть `/sys/fs/cgroup/xgwdirect.slice`; иначе правила нет, и программы из `direct-run` идут
     через VPN. Это безопасная сторона.
   - **Slice запускает демон, а не `xgw-net`.** `xgw-net.service` работает до `network-pre.target`
     и slice не запускает вовсе. Запуск — в `xgw.service` при старте:
     `systemctl start --no-block xgwdirect.slice`; затем внеочередной `capture.up()` добавляет
     правило. Значит, при загрузке машины правило появляется через секунды после `xgw-net`.
   - **Unit `packaging/xgwdirect.slice`:**

     ```ini
     [Unit]
     Description=XGW: программы мимо VPN (xgw direct-run)
     DefaultDependencies=no
     Before=shutdown.target
     Conflicts=shutdown.target
     ```

     У slice-юнитов и с зависимостями по умолчанию ожидания `sysinit`/`basic` нет, поэтому
     взаимоблокировки с ранней загрузкой не возникает. `DefaultDependencies=no` здесь —
     страховка. Запущенный slice systemd не выгружает ни пустым, ни после `daemon-reload`.
     Создавать каталог в `/sys/fs/cgroup` напрямую (`os.mkdir`) нельзя: этим деревом владеет
     systemd.
   Выражение `socket cgroupv2` требует модуля ядра `nft_socket`. В штатных ядрах Ubuntu он есть,
   но в урезанных ядрах встречается его отсутствие: `nft` тогда отвечает «Could not process
   rule: No such file or directory», хотя путь существует. Поэтому `_ensure_slice` сначала
   проверяет правило в одноразовой netns (`unshare -n nft -c -f`, как `diag.py:370-395`); при
   отказе правило не ставится, `xgw diag` пишет WARN «ядро без nft_socket», а стенд пропускает
   тест.
   Конфиг: `[capture] direct_slice = true` (по умолчанию false).
3. **По назначению** — уже есть: `routing.direct_domains`, `direct_ips`, `proxy_domains`
   (`builder.py:712-747`). Разгрузка этого трафика в ядро — §2.6.
4. **Устройство LAN → свой сервер** (как профили Firewalla и Keenetic). TPROXY сохраняет адрес
   источника, поэтому nftables менять не нужно — достаточно правила маршрутизации Xray.
   - `panel.json`: `device_routes: {"<IPv4 устройства>": "<отпечаток сервера>"}`. Устройство,
     как и для обхода, нужно со статической арендой — иначе адрес достанется другому.
   - `builder.py`: для каждого устройства — balancer `dev-<ip>` с `selector = [тег сервера]` и
     `fallbackTag` = основной балансировщик. Если выбранный сервер мёртв, устройство не
     остаётся без сети.
   - Правило `{"type": "field", "source": ["<ip>"], "balancerTag": "dev-<ip>"}` ставится
     **после** правил DNS, `geoip:private` и `direct_*`: российские сайты у устройства по-прежнему
     идут напрямую. Ставится **до** общего балансировщика.
   - Панель: в строке устройства — «Сервер: авто / <сервер>».
   - После Ф5 тем же способом устройство привязывается к серверу AmneziaWG (UDP для игровой
     приставки).
   - Устройство из `bypass_hosts` в Xray не попадает вовсе, поэтому вместе с маршрутом его
     держать нельзя — панель не даёт поставить то и другое.
5. **DoT и QUIC из LAN** — две опции, обе по умолчанию выключены, в панели переключатели.
   Правила стоят в `prerouting` раньше `tproxy` (`nft.py:281-285`); `reject` в prerouting
   загружается — проверено (nftables 1.1.6), на 6.8 проверить стендом.
   - `[capture] reject_dot = false`. При `true` —
     `iifname "<lan>" meta l4proto { tcp, udp } th dport 853 counter reject`: телефоны с
     «Частным DNS» в автоматическом режиме возвращаются на порт 53, а его DNS решает шлюз
     (`direct_domains` разрешаются российскими резолверами).
     Утечки сейчас нет и так: порт 853 уходит в туннель как обычный TCP. Поэтому опция — ради
     единого DNS, а не ради безопасности.
     Минус: в **строгом** режиме («имя провайдера DNS») устройство на 53 не вернётся и
     останется без DNS. Об этом панель пишет рядом с переключателем.
   - `[capture] block_quic = "off" | "on" | "auto"`. Правило —
     `iifname "<lan>" udp dport 443 counter reject with icmp type port-unreachable`: браузер
     сразу переходит на TCP/443, без UDP поверх TCP-туннеля (VLESS-TCP/REALITY), и Xray меньше
     нагружает процессор.
     `"auto"` — правило стоит, только когда трафик LAN идёт через сервер без своего UDP: не
     hysteria2, не TUIC, не WireGuard и не AWG. Демон перегружает правила при смене основного
     сервера — это одна атомарная транзакция. Сначала делается `"on"`, `"auto"` — вторым
     шагом.

#### (в) Anti-DPI: интерфейс ядра и AmneziaWG

**Интерфейс** `src/xgw/generator/backends.py` — то, что сейчас разбросано по `builder.py`,
`singbox.py` и `profiles.py`:

```python
class CoreBackend(Protocol):
    name: str                                    # "xray" | "sing-box" | "awg"
    def supports(self, node: ServerNode) -> bool: ...
    def profiles(self, node: ServerNode) -> tuple[str, ...]: ...   # ступени лестницы
    def outbound(self, node: ServerNode, profile: str) -> dict: ...  # outbound Xray к серверу
    def sidecar(self, nodes: Sequence[ServerNode]) -> SidecarPlan | None: ...  # конфиг/интерфейсы
    def validate(self, plan: SidecarPlan, runner: Runner) -> list[str]: ...

BACKENDS: tuple[CoreBackend, ...] = (XrayBackend(), SingboxBackend(), AwgBackend())
```

Вход у всех один — Xray (как сейчас: sing-box стоит за ним, `singbox.py:213-291`). Лестница
`profiles.ladder()` спрашивает ступени у backend'а, а не у списка в `profiles.py`.

**AwgBackend:**
- Ссылка: `wireguard://…&jc=4&jmin=40&jmax=70&s1=0&s2=0&h1=…&h4=…` (то, что сейчас отклоняет
  `parsers/wireguard.py:16-19`), а также `awg://` и конфиг `[Interface]` с теми же ключами.
  `RawServer.awg = AwgSpec(private_key, address, peer_key, endpoint, jc, jmin, jmax, s1, s2, h1..h4,
  mtu, psk)`.
- Ядро: интерфейс `awg-<fp6>` на каждый сервер (не больше 16). Два способа, выбирается при
  установке:
  - **модуль ядра** (DKMS): `ip link add awg-<fp6> type amneziawg`;
  - **userspace `amneziawg-go`**: создаёт обычный TUN-интерфейс с тем же именем; модуль и его
    подпись не нужны.
  Дальше в обоих случаях `awg setconf awg-<fp6> <файл>` с `FwMark = mark_bypass`: UDP самого
  AmneziaWG не попадает под перехват.
- **Secure Boot.** На Ubuntu 24.04 с включённым UEFI Secure Boot модуль DKMS соберётся, но
  `modprobe amneziawg` откажет («Key was rejected by service»), пока ключ MOK не записан при
  перезагрузке. Поэтому `xgw install-awg` и `xgw diag` смотрят `mokutil --sb-state` и пробуют
  `modprobe amneziawg`. При отказе используется `amneziawg-go` — заказчику не нужно подписывать
  модуль из консоли. Diag пишет, какой способ работает и почему.
- Xray выходит в него outbound'ом `freedom` с `streamSettings.sockopt.interface = "awg-<fp6>"`
  (SO_BINDTODEVICE) и `settings.domainStrategy = "UseIPv4"`, как у outbound `direct`
  (`builder.py:622`): имена назначения разрешает DNS Xray, а не системный резолвер.
  Пробы и сканы идут через существующие probe-inbound'ы сервера без изменений.
- **Маршрут для привязанного сокета.** `awg setconf` настраивает только AllowedIPs внутри
  WireGuard, маршрутов в ядре не создаёт. Когда для интерфейса, к которому привязан сокет,
  маршрута нет, ядро считает адрес назначения доступным напрямую через этот интерфейс, поэтому
  маршрут не нужен.
  Проверено опытом в одноразовой netns: в main только `default via … dev veth0`, интерфейс TUN
  `awgt` с адресом `10.8.1.2/32` и без маршрутов. Сокет с `SO_BINDTODEVICE = awgt` к
  `203.0.113.7:443` подключается: UDP — сразу, TCP — начинает соединение. ENETUNREACH нет,
  источник `10.8.1.2`. Опыт шёл на ядре новее 6.8, так что первый тест стенда Ф5 перепроверяет
  это на 6.8. Если всё же будет ENETUNREACH, маршрут ставится **в отдельной таблице** (`ip route replace default dev
  awg-<fp6> table <200+idx>` плюс `ip rule oif awg-<fp6> lookup <200+idx>`), но **не** в main с
  высокой метрикой: туда при пропавшем WAN ушёл бы весь трафик машины.
- Пакеты (PPA Amnezia для Ubuntu: модуль и `awg`; либо бинарь `amneziawg-go` с проверкой
  SHA-256, как в `xraycore/binary.py`) ставятся **только с согласия заказчика**, отдельной
  командой `sudo xgw install-awg`, как `update-singbox`. Без них ссылки по-прежнему
  пропускаются с пояснением. Перед Ф5 проверить: имя PPA и пакетов для 24.04 и 26.04, тип линка
  (`amneziawg`), сборку модуля на ядре 6.8, откуда брать `amneziawg-go` для amd64.
- Лестница профилей к AWG не применяется (это UDP со своей обфускацией): `profiles()` возвращает
  `("awg:default",)`.

**Ручки Xray для уже поддержанных протоколов** (каждую до кода проверить на Xray 26.10.10):
- uTLS fingerprint на сервер: сейчас берётся из ссылки, а без него — `chrome`
  (`parsers/convert.py:25-27`). Добавить замену по отпечатку сервера в `panel.json` (ключ
  `fingerprint`, как `core`), в панели — выбор `chrome / firefox / safari / random`;
- `freedom.settings.noises` для UDP-протоколов через Xray — ступень `xray:noise` в лестнице для
  серверов с verdict CONNECT_FAIL/TIMEOUT на UDP-транспортах (mKCP, QUIC-xhttp).

### 2.5 Чего не добавляем: уже есть

- **Порог «заморозки» ТСПУ (16–32 КБ).** Сквозная проба по умолчанию качает 57 620 байт
  (`config.py:31`, файл шрифта с jsDelivr). Детектор тишины 5 с отмечает соединение,
  замолчавшее посреди тела (`watch/checks.py:44-240`). Скан выносит вердикты FROZEN и
  STALL_BEFORE_BODY, и они запускают лестницу профилей (`generator/profiles.py`, ступени до
  `singbox:mux_padded`). На стенде это проверено моделью ТСПУ `freeze_relay.py` с
  `freeze_after=16384` (README, раздел проверок стенда). Отдельная проверка «64 КБ» в
  netcheck продублировала бы e2e.
- **Гистерезис смены сервера.** Основной сервер меняется по замеру скорости, только если
  другой быстрее на `speed.gain_pct = 30` % (`config.py:150`, `watch/speed.py:109-116`).
  Между раундами выбор закреплён (`xray api bo`), а не прыгает за задержкой, как у leastPing.

### 2.6 Разгрузка прямого трафика в ядро (Ф6)

Сейчас трафик из LAN на `routing.direct_ips` (по умолчанию `geoip:ru`) проходит TPROXY →
Xray → outbound `direct`: процессор и сокеты тратятся на трафик, которому VPN не нужен.

- Схема с `dnsmasq --nftset` к XGW не подходит: dnsmasq здесь только раздаёт адреса
  (`port=0`), DNS отвечает Xray.
- **Доменов в ядре нет — только IP-списки.** Set `direct4` (`type ipv4_addr; flags interval`)
  собирается из CIDR в `direct_ips` и из `geoip:ru`. Последний разворачивается из `geoip.dat`
  самого Xray (`/opt/xgw/xray/geoip.dat`) небольшим читателем protobuf — новый модуль
  `src/xgw/geodat.py`, `cidrs(path, code) -> list[str]`, без зависимостей. Это порядка 10–15
  тыс. сетей; set с `flags interval` это выдерживает.
- Правила:
  - prerouting: `ip daddr @direct4 return` (после `@bypass4`, до `tproxy`);
  - forward: `iifname "<lan>" {out} ip daddr @direct4 accept`;
  - postrouting: masquerade для `ip daddr @direct4`;
  - output машины: `ip daddr @direct4 return`.
  DNS (порт 53) по-прежнему перехватывается: правило про `direct4` стоит после правил DNS.
- **Где смысл меняется.** В Xray доменные правила проверяются раньше IP
  (`domainStrategy = "IPIfNonMatch"`, `builder.py:794`). Поэтому домен из `proxy_domains` с
  российским адресом сейчас идёт через VPN, а в ядре пошёл бы напрямую. Отсюда: при
  непустом `proxy_domains` разгрузка не включается, `xgw diag` объясняет почему. С
  `device_routes` (§2.4б, п. 4) противоречия нет: правило устройства стоит после `direct_*`,
  так что прямой трафик устройства и сейчас идёт напрямую. Опция `[routing] kernel_direct = false` по умолчанию.
- Обновление: set пересобирается при смене `geoip.dat` (`update-xray`) и `direct_ips` — тем же
  атомарным `nft -f`.

### 2.7 Очередь на WAN: sch_cake (Ф7, по желанию)

Без шейпера тяжёлая загрузка у одного клиента поднимает задержку туннеля у всех.
- `tc qdisc replace dev <wan> root cake bandwidth <N>mbit nat diffserv4`. **Без `bandwidth`
  cake не помогает**: очередь копится в модеме провайдера, а не на шлюзе. Поэтому опция —
  `[network] sqm_up_mbit = 0` (0 — выключено), задаётся вручную: 90–95 % скорости отдачи
  тарифа.
- Входящее направление (через `ifb`) — не в этой фазе.
- `xgw diag`: есть ли модуль `sch_cake` (`modinfo sch_cake`). В урезанных ядрах его нет — в
  одноразовой netns проверки его не нашлось. Для 24.04 до кода выяснить, в каком пакете он
  лежит: `linux-modules` или `linux-modules-extra`.
- Снимается при `xgw net down` и удалении; прежний qdisc запоминается в журнале установки.

---

## 3. Roadmap: семь атомарных фаз (Ф6 и Ф7 — по желанию)

У каждой фазы — свой коммит. Пункт ASSUMPTIONS (следующий номер после 213); README — только где
поведение видно пользователю. Юнит-тесты — на `tests/fakenet.py` и `tests/fakesys.py`. Стенд —
под root, netns-режим включается сам:

```
XGW_XRAY_BIN=/path/xray XGW_SINGBOX_BIN=/path/sing-box .venv/bin/python -m pytest tests/stand -k <имя>
```

Линт: `ruff check src tests`. Новый тест обязан падать на коде до фазы.

### Ф1. Фаервол fail-closed (§2.1)

| Файл | Что |
|---|---|
| `src/xgw/config.py` | `CaptureConfig.hold: Literal["block", "direct"] = "block"`; при `fail_mode = "open"` — всегда `"direct"` |
| `src/xgw/net/nft.py` | `Rules.blocked: bool`, `Rules.v6_guard: bool`; `render_blocked(rules) -> str` — `block_output`, forward с отказом для мостов контейнеров (`CONTAINER_IFS`, кроме `bypass_containers`) и установленными соединениями только для `@bypass4`; блок `v6_guard` (с `meta mark 0x2 accept`) в `render6`; `apply(rules, runner)` — один `nft -f` с текстом обеих таблиц, при `not ipv6_available()` — только v4 |
| `src/xgw/net/capture.py` | `_load("on")` при `reason` → `mode = "blocked" if self.cfg.capture.hold == "block" else "off"` (`capture.py:358-365`); `effective_mode()` возвращает `"blocked"`; `loaded()` и `describe()` знают о blocked |
| `src/xgw/daemon.py` | `_guard_capture` при XRAY_DOWN и `fail_mode = "closed"`, `hold = "block"`, если Xray недоступен дольше `FAIL_OPEN_AFTER` — `capture.block()`; возврат в on — после `xray_ok` |
| `src/xgw/diag.py` | группа «IPv6»: FAIL вместо WARN, если `v6_guard` не загружен при `ipv6 = "off"` |

Тесты:
- `tests/test_nft.py::test_blocked_mode_lets_only_xray_and_service_traffic_out`;
- `::test_both_families_load_in_one_transaction` — один вызов `nft -f`;
- `::test_v6_guard_with_ipv6_off_regardless_of_networkmanager`;
- `::test_blocked_rejects_containers_except_bypass_subnets`;
- `::test_blocked_keeps_established_only_for_bypass_devices`;
- `::test_v6_guard_lets_xray_sockets_out` (метка 2) и
  `::test_v6_guard_keeps_kernel_icmpv6` (ND и packet-too-big на глобальный адрес);
- `tests/test_daemon.py::test_blocked_notification_is_sent` — уведомление уходит через
  `http-in` или напрямую с меткой 2;
- `tests/test_net.py::test_missing_inbound_blocks_when_hold_is_block` (там же, где тесты
  `Capture`); `test_enable_refuses_without_applied_tproxy_inbound` (`test_net.py:291`) проверяет
  прежнее «напрямую» — перевести его на `hold = "direct"`;
- `tests/test_paths.py::test_no_system_resolver_calls_in_xgw` — поиск `getaddrinfo` /
  `gethostbyname` по `src/xgw`.

Стенд, `tests/stand/test_stand.py`:
- `test_lan_is_blocked_without_capture_inbound` — конфиг Xray без `tproxy-in`, `ip netns exec lan
  curl -m 5 http://5.5.5.1:8080/` не проходит, `curl http://192.168.50.1:<порт панели>` из ns gw
  проходит;
- `test_host_ipv6_never_leaks_with_ipv6_off` — `ip netns exec gw curl -6 -m 5
  http://[2001:db8:5::1]:8080/` → отказ, при `ipv6 = "proxy"` — через Xray;
- `test_containers_do_not_leak_in_blocked_mode` — мост контейнеров стенда (netns-режим): curl
  из контейнера к 5.5.5.1 в blocked не проходит;
- `test_direct_session_is_cut_when_blocked` — `xgw disable`, из ns lan открыть долгое соединение
  к `5.5.5.1:8080/slow`, перевести шлюз в blocked → соединение рвётся ≤ 2 с, origin не получает
  остаток.

### Ф2. События и жизненный цикл (§2.3) + защита служб

| Файл | Что |
|---|---|
| `src/xgw/watch/events.py` (новый) | `class NetEvents` (выше), разбор строк `ip -o monitor` (текст), `busctl monitor --json=short`, `nft monitor` (без фильтра) — функции `parse_net(line) -> str \| None`, `parse_sleep(line) -> bool \| None`, `parse_rules(line) -> bool` (delete/flush по `xgw`, `xgw6` и `flush ruleset`) |
| `src/xgw/net/capture.py` | `ignore_rules_until: float` — ставится после каждого `nft.apply`; `NetEvents` пропускает события rules в этом окне, вне окна демон всё равно сверяет `loaded()` |
| `src/xgw/daemon.py` | `Lifecycle(StrEnum)`: OFF, CONNECTING, CONNECTED, BLOCKED, OPEN; `_lifecycle() -> Lifecycle`; `wake(reason: str)`; ветки `wake_reason` в `tick()`; поле `capture.lifecycle` в status.json |
| `src/xgw/cli.py` | `_cmd_run` запускает `NetEvents(daemon.wake)` рядом с панелью и ботом (`_cmd_run`, `cli.py:662`) |
| `src/xgw/daemon.py`, `src/xgw/config.py` | проверка с учётом трафика: `Daemon._busy(tag) -> bool`, `watchdog.busy_window_s = 10`, `watchdog.busy_bytes = 1048576`; вызов в `_check_e2e` и при подсчёте мёртвых участников (§2.3) |
| `src/xgw/watch/panel.py`, `src/xgw/ui/app.js` | строка «Перехват: работает / подключается / заблокирован — …» |
| `packaging/xgw-net.service` | `ProtectSystem=strict`, `ReadWritePaths=/var/lib/xgw /run/xgw`, `ProtectHome=yes`, `PrivateTmp=yes`, `NoNewPrivileges=yes`, `CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW` (запись в `/proc/sys/net` — нужен `ProtectKernelTunables=no`, по умолчанию так и есть) |
| `packaging/xgw-dhcp.service` | `ProtectSystem=strict`, `ReadWritePaths=/var/lib/xgw` (аренды уже в `/var/lib/xgw/dhcp.leases`, `dnsmasq.py:30` — `/var/lib/misc` не нужен), `ProtectHome=yes`, `PrivateTmp=yes`, `CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW CAP_SETUID CAP_SETGID CAP_CHOWN` |

Ф2б (отдельный коммит, можно позже): `src/xgw/control.py` — `serve(daemon, path)` и
`request(path, payload, timeout=2.0) -> dict | None`; `xgw priority/core/pin` шлют `poke`.

Тесты:
- `tests/test_events.py` — разбор строк каждого источника (образцы — настоящий вывод `ip -o
  monitor`, `nft monitor`, `busctl monitor --json=short`), debounce, перезапуск подпроцесса,
  окно `ignore_rules_until`;
- `tests/test_events.py::test_monitor_events_arrive_while_process_runs` (под root, в
  `unshare -n`): событие `nft add table` и `ip link add dummy` доходит до читателя ≤ 1 с —
  страховка от буферизации пайпа в будущих версиях программ;
- `tests/test_daemon.py::test_wake_after_resume_reloads_rules_and_scans`;
- `tests/test_daemon.py::test_late_probe_under_load_is_not_a_failure` (счётчик downlink выбранного
  растёт на 5 МБ за окно → `e2e_fail_streak` не растёт) и
  `::test_late_probe_without_traffic_still_counts`.

Стенд:
- `test_wan_flap_wakes_daemon` — `ip netns exec gw ip link set <wan> down; sleep 3; … up` →
  внеочередной шаг ≤ 2 с после `up` (по журналу);
- `test_foreign_flush_is_restored_quickly` — по очереди `nft flush ruleset`,
  `nft flush table ip xgw`, `nft delete chain ip xgw output` в ns gw → правила снова на месте
  ≤ 2 с, а своя загрузка XGW внеочередного шага не вызывает.

Машинный стенд (`tests/stand/test_machine.py`): `systemd-analyze security xgw-net.service
xgw-dhcp.service` — оценка не хуже 6.0, после установки обе службы активны.

### Ф3. netcheck и DNS через resolved (§2.2, §2.4а)

| Файл | Что |
|---|---|
| `src/xgw/netcheck.py` (новый) | `run(cfg, paths, runner) -> list[diag.Check]`; `pmtu(host, mark) -> int \| None` (None — ICMP закрыт, контрольный ping не прошёл); `stun(addr, mark: int \| None) -> str \| None`; `dns_captured(timeout=3.0) -> bool` (A-запрос на `192.0.2.53:53` без метки); `v6_connect(addr) -> bool` |
| `src/xgw/diag.py`, `src/xgw/cli.py` | флаг `--netcheck` (`cli.py:138-140`), группа «Сеть» в `Diag.run` |
| `src/xgw/net/resolved.py` (новый) | `available`, `bind_link`, `revert_link` |
| `src/xgw/net/capture.py`, `src/xgw/net/nft.py` | вызовы `bind_link`/`revert_link` (§2.2); в режиме TUN первое правило `output` — `oifname "<tun_name>" return` |
| `src/xgw/watch/panel.py`, `src/xgw/ui/` | действие `diag/netcheck` и кнопка |

Тесты:
- `tests/test_netcheck.py` — каждая проверка на подменённом раннере и сокетах; отдельно —
  `test_pmtu_skipped_when_server_drops_icmp` (контрольный ping не прошёл → OK «не проверен», а
  не WARN);
- до кода Ф3 — проверить на Xray 26.10.10, что `dns-out` отвечает на A-запрос к `192.0.2.53` и
  отбрасывает TXT (`nonIPQuery`); итог записать в ASSUMPTIONS;
- `tests/test_resolved.py` — точные argv `busctl` (сигнатуры `ia(iay)`, `ia(sb)`, `ib`, `is`, `i`).

Стенд:
- `test_netcheck_finds_dns_and_v6_leaks_only_without_rules` — `xgw net down` → FAIL «утечка
  DNS»; `xgw net up` → OK. STUN-сервер — заглушка на `5.5.5.1:3478` в `tests/stand/origin.py`;
- `test_resolved_link_follows_tun` — на машинном стенде (там есть resolved):
  `resolvectl status xgwtun0` показывает `DNS Servers: 1.1.1.1`, `DNS Domain: ~.`; после
  `xgw disable` линка нет.

### Ф4. Split tunneling (§2.4б)

| Файл | Что |
|---|---|
| `src/xgw/config.py` | `CaptureConfig.direct_slice: bool = False`, `containers_bypass: list[str]` |
| `src/xgw/net/nft.py` | `Rules.direct_slice: str` ("" — нет), `Rules.containers_bypass`; правило cgroup в `output`; set `bypass_containers` |
| `src/xgw/net/capture.py` | `direct_slice_ready() -> bool`: каталог `/sys/fs/cgroup/xgwdirect.slice` есть и правило проходит `unshare -n nft -c -f` (модуль `nft_socket`); только тогда `Rules.direct_slice` заполняется. Сам slice здесь не запускается |
| `src/xgw/cli.py` (`_cmd_run`), `src/xgw/daemon.py` | при старте `xgw.service`: `systemctl start --no-block xgwdirect.slice`, затем внеочередной `capture.up()` |
| `packaging/xgwdirect.slice` (новый, `DefaultDependencies=no`), `src/xgw/install.py`, `src/xgw/uninstall.py` | установка, удаление, `UNIT_FILES` |
| `src/xgw/managed.py` | `set_device_route(path, ip, fingerprint \| None)` через `_update` (как остальные правки `panel.json`); проверка, что устройство не в обходе |
| `src/xgw/generator/builder.py` | balancer `dev-<ip>` (selector — тег сервера, `fallbackTag` — основной) и правило `source` после `direct_*` (§2.4б, п. 4) |
| `src/xgw/net/nft.py`, `src/xgw/config.py` | `reject_dot`, `block_quic` — правила в `prerouting` до `tproxy` (§2.4б, п. 5); `"auto"` — вторым коммитом |
| `src/xgw/watch/panel.py`, `src/xgw/ui/` | «Сервер устройства»; переключатели DoT/QUIC с предупреждением про строгий «Частный DNS» |
| `src/xgw/cli.py` | `xgw direct-run -- …` → `os.execvp("systemd-run", […])` |

Тесты:
- `tests/test_nft.py::test_direct_slice_rule_only_when_slice_exists`;
- `tests/test_net.py::test_xgw_net_up_never_starts_the_slice` (ранняя загрузка: только проверка
  наличия);
- `tests/test_cli_commands.py::test_direct_run_builds_systemd_run_argv`;
- `tests/test_generator.py::test_device_route_goes_after_direct_rules_with_fallback`;
- `tests/test_managed.py::test_device_route_refused_for_bypassed_device`;
- `tests/test_nft.py::test_dot_and_quic_rules_precede_tproxy`.

Стенд:
- `test_cgroup_bypass_goes_direct` — `systemd-run --scope --slice=xgwdirect.slice ip netns exec
  gw curl http://5.5.5.1:8080/trace` доходит напрямую (лог origin: адрес источника — gw, а не
  сервер Xray); тот же curl без `systemd-run` — через Xray. Каталог cgroup создаёт systemd, не
  тест. Если ядро без `nft_socket`, тест пропускается;
- `test_container_subnet_bypass` (netns + мост `br-test`);
- `test_device_route_uses_its_server` — в стенде два сервера; `192.168.50.100` привязан ко
  второму. Лог origin показывает выход второго сервера, второй LAN-адрес стенда идёт через
  основной. При «замороженном» втором трафик устройства уходит на основной (`fallbackTag`);
- `test_quic_rejected_and_tcp_works` — `block_quic = "on"`: UDP/443 из ns lan получает ICMP
  port-unreachable, TCP/443 проходит.

Машинный стенд:
- `xgw direct-run -- curl …` идёт в обход;
- после перезагрузки контейнера правило cgroup появляется через секунды после старта
  `xgw.service`, а `xgw-net` отрабатывает без ожидания slice.

### Ф5. Интерфейс ядер и AmneziaWG (§2.4в)

| Файл | Что |
|---|---|
| `src/xgw/generator/backends.py` (новый) | `CoreBackend`, `XrayBackend`, `SingboxBackend`, `AwgBackend`, `SidecarPlan` |
| `src/xgw/generator/builder.py`, `singbox.py`, `profiles.py` | перевод на `BACKENDS` без изменения выдаваемых конфигов (golden-тесты `tests/fixtures/golden` не меняются — проверка рефакторинга) |
| `src/xgw/parsers/wireguard.py`, `parsers/common.py` | `AwgSpec`; ссылка с параметрами awg больше не `UnsupportedLink`, если `AwgBackend` доступен |
| `src/xgw/net/awg.py` (новый) | `ensure(spec, ifname, mark, runner, *, method: Literal["kernel","go"])`, `remove(ifname, runner)`, `present(ifname, runner)`, `kernel_usable(runner) -> tuple[bool, str]` (`mokutil --sb-state` и `modprobe amneziawg`; причина отказа — текстом) |
| `src/xgw/awgcore/install.py` (новый), `src/xgw/cli.py` | `xgw install-awg`: модуль из PPA, а при Secure Boot без ключа — `amneziawg-go` (SHA-256); выбранный способ — в `/var/lib/xgw` |
| `src/xgw/generator/builder.py` | outbound AWG: `freedom` с `sockopt.interface` и `domainStrategy = "UseIPv4"` |
| `src/xgw/diag.py` | группа «AmneziaWG»: способ, Secure Boot, модуль |

Тесты:
- golden-тесты генератора без изменений;
- `tests/test_parsers.py::test_amnezia_link_parses_into_awg_spec`;
- `tests/test_awg.py` — argv `ip link` / `awg setconf` для обоих способов, выбор `go` при отказе
  `modprobe` («Key was rejected by service»), отсутствие маршрута в main.

Стенд (только где есть модуль или `amneziawg-go`):
- `tests/stand/test_stand_awg.py::test_bound_socket_reaches_server_without_routes` — первым:
  сокет Xray с `sockopt.interface` доходит до сервера без маршрутов через `awg-<fp6>`. Если
  ENETUNREACH — переход на отдельную таблицу (§2.4в), не на main;
- сервер AmneziaWG в ns inet (`awg-quick` с теми же `jc/s1/h1`), LAN → curl → 5.5.5.1 через
  `awg-<fp6>`;
- контроль: сервер с другим `h1` — CONNECT_FAIL, лестница не запускается;
- при пропавшем WAN (`ip link set wan down` в ns gw) трафик машины не уходит в `awg-<fp6>`.

### Ф6. Разгрузка прямого трафика в ядро (§2.6, по желанию)

| Файл | Что |
|---|---|
| `src/xgw/geodat.py` (новый) | `cidrs(path: Path, code: str) -> list[str]` — читатель `geoip.dat` (protobuf: `GeoIPList → GeoIP{country_code, cidr[]}`), только IPv4 |
| `src/xgw/config.py` | `[routing] kernel_direct = false` |
| `src/xgw/net/nft.py` | set `direct4`; правила в prerouting, forward, postrouting, output; `Rules.direct4` |
| `src/xgw/net/capture.py`, `src/xgw/xraycore/update.py` | пересборка set при `update-xray` и смене `direct_ips` |
| `src/xgw/diag.py` | «разгрузка выключена: есть proxy_domains» и число сетей в set |

Тесты:
- `tests/test_geodat.py` — разбор маленького `geoip.dat`, собранного в тесте; сверка с выводом
  `xray`, где он есть;
- `tests/test_nft.py::test_kernel_direct_off_with_proxy_domains`.

Стенд:
- `test_kernel_direct_bypasses_xray` — сеть origin внесена в `direct_ips`. curl из ns lan
  доходит до неё, счётчик правила `direct4` растёт, а счётчик правила `tproxy` — нет; лог origin
  показывает адрес шлюза, а не сервера.

### Ф7. sch_cake на WAN (§2.7, по желанию)

| Файл | Что |
|---|---|
| `src/xgw/net/sqm.py` (новый) | `apply(wan, up_mbit, runner)`, `remove(wan, runner)`, `available(runner) -> bool` |
| `src/xgw/config.py`, `src/xgw/net/capture.py`, `src/xgw/uninstall.py` | `[network] sqm_up_mbit = 0`; применение в `net up`, снятие в `net down` и при удалении |
| `src/xgw/diag.py` | модуль `sch_cake` и текущий qdisc на WAN |

Тесты: argv `tc` на FakeKernel. Стенд — где модуль есть: при загрузке канала стенда
задержка ping через туннель растёт меньше, чем без cake (порог с запасом).

---

## 4. Порядок и зависимости

- **Ф1** — первой: закрывает единственный высокий риск. Нужно решение заказчика по
  `hold = "block"` (§2.1).
- **Ф2** — после Ф1: жизненный цикл опирается на режим blocked.
- **Ф3** и **Ф4** не зависят друг от друга. Обе требуют Ф1: `v6_guard` нужен проверке утечки IPv6,
  а правило cgroup не должно действовать в режиме blocked.
- **Ф5** — независима от Ф2–Ф4. AmneziaWG ставит сторонние пакеты — только с согласия заказчика.
  Привязка устройства к серверу AWG — после Ф4 и Ф5.
- **Ф6** — после Ф1 (новый set входит в ту же транзакцию). **Ф7** — независима. Обе по
  желанию заказчика.

---

## 5. Учтённые замечания рецензии

План пересмотрен по внешней рецензии. Каждое замечание перед правкой проверено по коду, а
спорные — опытом в одноразовой netns.

| Замечание | Итог | Где в плане |
|---|---|---|
| Контейнеры выходят наружу в режиме blocked (нет цепочки `containers`, правило «чужой форвардинг» их пропускает) | принято | §2.1 forward, Ф1 тесты |
| Сессии, открытые в off/open, переживают переход в blocked через `ct state established` | принято (сужение до `@bypass4`; `conntrack` в Ubuntu по умолчанию нет) | §2.1, Ф1 стенд |
| DNS демона в blocked заблокирован | частично: XGW системный резолвер не использует (`builder.py:516`, свой резолвер с меткой 2); добавлен тест-инвариант. В `v6_guard` добавлено `meta mark 0x2 accept` | §2.1, Ф1 |
| `nft monitor tables` не видит `flush table` / `delete chain` | принято (проверено: `flush table` событий таблиц не даёт) | §2.3, Ф2 |
| Булев флаг своей загрузки сбросится раньше события | принято: `ignore_rules_until` и сверка `loaded()` | §2.3, Ф2 |
| Буфер пайпа 4 КБ у `nft`/`ip`/`busctl monitor` | отклонено: проверено, все три отдают события сразу; добавлен тест-страховка | §2.3, Ф2 |
| PMTU: сервер без ICMP даёт ложный WARN | принято: контрольный ping | §2.4а, Ф3 |
| Утечка DNS через `o-o.myaddr`: совпадение пулов Google | довод отклонён (имя отдаёт адрес спросившего), но проверка всё равно заменена: `dns-out` отбрасывает TXT — теперь A-запрос на `192.0.2.53` | §2.4а, Ф3 |
| Двойная маршрутизация DNS resolved в TUN | принято как оптимизация: `oifname "<tun>" return` | §2.2, Ф3 |
| slice: взаимоблокировка при загрузке и выгрузка пустого slice | взаимоблокировки нет (у slice нет ожидания `sysinit`), запущенный slice не выгружается. Принято другое: `xgw-net` slice не трогает, его запускает `xgw.service` (`--no-block`), unit с `DefaultDependencies=no`. `os.mkdir` в `/sys/fs/cgroup` отклонён | §2.4б, Ф4 |
| `SO_BINDTODEVICE` без маршрута → ENETUNREACH | не принято как факт: ядро для привязанного сокета без маршрута считает адрес доступным напрямую через интерфейс. Проверяется первым тестом Ф5; маршрут в main с высокой метрикой отклонён (при пропавшем WAN туда ушёл бы трафик машины) — если нужен, то в отдельной таблице | §2.4в, Ф5 |
| `freedom` без `domainStrategy` | принято: `UseIPv4`, как у `direct` | §2.4в, Ф5 |
| Secure Boot ломает модуль DKMS | принято: `mokutil --sb-state`, запасной способ `amneziawg-go` | §2.4в, Ф5 |
| `xgw-dhcp` и `/var/lib/misc/dnsmasq.leases` | уже не нужно: аренды в `/var/lib/xgw/dhcp.leases` (`dnsmasq.py:30`) | Ф2 |
| `ip -j monitor` (ошибка самого плана) | исправлено: `ip monitor` с `-j` печатает текст | §2.3, Ф2 |

Вторая рецензия:

| Предложение | Итог | Где в плане |
|---|---|---|
| ICMPv6 ядра (ND, packet-too-big) в `v6_guard` | принято; правило загружается | §2.1, Ф1 |
| `SO_BINDTODEVICE` к `awg-*` без маршрута → ENETUNREACH | отклонено опытом: в netns сокет, привязанный к TUN с `/32` и без маршрутов, подключается (UDP и TCP), источник — адрес TUN. Первый тест стенда Ф5 перепроверяет на 6.8; запасной путь — отдельная таблица | §2.4в, Ф5 |
| Бот и уведомления в blocked без метки 2 | уже так: `http-in` либо прямой путь с меткой 2 (`watch/telegram.py:276-280`); добавлен тест | §2.1, Ф1 |
| Проба не засчитывается, если туннель качает (Traffic-Aware Healthcheck) | принято; счётчики Xray уже включены (`builder.py:779-782`) | §2.3, Ф2 |
| Детект «16 КБ»-блокировки ТСПУ | уже есть: проба 57 620 байт, детектор тишины, FROZEN, лестница профилей, стенд `freeze_after=16384` | §2.5 |
| Отбой DoT (853) и QUIC (UDP/443) из LAN | принято как опции, по умолчанию выключены. DoT — с предупреждением про строгий «Частный DNS»; утечки и сейчас нет. QUIC: сначала `on`, потом `auto` | §2.4б п. 5, Ф4 |
| Разгрузка `direct_domains` в ядро через `dnsmasq --nftset` | в таком виде неприменимо: dnsmasq у XGW без DNS (`port=0`). Принято для IP-списков (`direct_ips`, `geoip:ru` из `geoip.dat`); не включается при `proxy_domains` | §2.6, Ф6 |
| Устройство LAN → свой сервер | принято: правило `source` в Xray с balancer и `fallbackTag`, после `direct_*` | §2.4б п. 4, Ф4 |
| Гистерезис смены сервера | уже есть: `speed.gain_pct = 30`, закрепление основного | §2.5 |
| `sch_cake` на WAN | принято по желанию: без `bandwidth` пользы нет, поэтому скорость задаётся вручную | §2.7, Ф7 |
