# ТЗ: Tailscale на шлюзе, удалённый доступ и Telegram Mini App через Funnel

> **20.10.2026: фазы Т3–Т5 (Mini App) отменены** решением заказчика после испытаний Т2.
> Вместо Mini App — приложение для Android: `ANDROID_APP_PLAN.md`. Т0–Т2 действуют.
> Бот Telegram (в том числе `/panel` из §3.2) убран целиком — ASSUMPTIONS п. 222.

Решение заказчика: Mini App открывается через **Tailscale Funnel**, а не через Cloudflare.
Tailscale уже стоит на шлюзе и на телефоне, но на шлюзе нормально не заработал. Поэтому
работа идёт в два этапа:

1. **Совместимость Tailscale с XGW и удалённый доступ к шлюзу** (Т0–Т2): Tailscale
   работает рядом с XGW в любом режиме перехвата, в том числе в `blocked` и при
   упавшем Xray. По нему с телефона и ноутбука доступны SSH и панель XGW.
2. **Mini App** (Т3–Т5): страница и API на шлюзе, наружу через Funnel; кнопка меню в
   чате с ботом.

XGW сам Tailscale не устанавливает и не удаляет: он работает с уже установленным
`tailscaled`, а если его нет — панель показывает, как поставить.

## 1. Что мешает Tailscale сейчас (по коду)

Как устроен `tailscaled` на Linux (исходники Tailscale, `tsconst/linuxfw.go` и
`wgengine/router/osrouter/router_linux.go`):

- свои сокеты (WireGuard UDP 41641, DERP по HTTPS 443, STUN 3478, управление
  `controlplane.tailscale.com`) он помечает меткой **`0x80000` в маске `0xff0000`**;
- правила маршрутизации: `5210` — помеченные → `main`, `5230` → `default`,
  `5250` → unreachable, `5270` — остальные → таблица **52** (адреса tailnet
  `100.64.0.0/10` и `fd7a:115c:a1e0::/48` → интерфейс `tailscale0`);
- в netfilter он ставит свои цепочки (`ts-input`, `ts-forward`, `ts-postrouting`); в
  `ts-input` отбрасываются пакеты с адресов `100.64.0.0/10`, пришедшие не с
  `tailscale0`;
- MagicDNS: DNS-сервер `100.100.100.100` на `tailscale0` через systemd-resolved.

Метки XGW (1 — перехват, 2 — мимо перехвата, 3 — контейнеры) лежат в младших битах и с
битами Tailscale не пересекаются. Правила `ip rule` XGW (`pref 90/95/100`,
`net/iprule.py:43-45`) сравнивают метку целиком и сокеты Tailscale не задевают.
Конфликты другие:

| # | Где | Что происходит | Последствие |
|---|---|---|---|
| К1 | `net/nft.py:320-334`, цепочка `output` | сокеты `tailscaled` не помечены как «мимо перехвата», и `meta mark set 1` **затирает** их метку `0x80000` | WireGuard, DERP и управление Tailscale уходят в Xray: UDP через VLESS плохо пробивает NAT, STUN видит адрес VPN-сервера, соединение то есть, то нет |
| К2 | там же: `ip daddr @reserved4 th dport != 53 return` | DNS на `100.100.100.100:53` не пропускается мимо, а перехватывается в `dns-out` Xray | имена MagicDNS (`*.ts.net`) на шлюзе не разрешаются |
| К3 | `net/nft.py:416-430`, `block_output` (режим blocked, Ф1) | разрешены только метка 2, loopback и LAN; трафик `tailscaled` и в `tailscale0` получает reject | в `blocked` удалённый доступ пропадает ровно тогда, когда нужен |
| К4 | `net/nft.py:536-555`, `v6_guard` | IPv6 tailnet (`fd7a:…` через `tailscale0`) и IPv6-сокеты `tailscaled` отбиваются | Tailscale по IPv6 не работает, SSH по IPv6-адресу tailnet — тоже |
| К5 | `ts-input` от Tailscale | если провайдер выдаёт WAN-адрес из `100.64.0.0/10` (CGNAT) или его DNS там же — Tailscale отбрасывает эти пакеты на WAN | у шлюза ломается сеть провайдера; XGW это сейчас не замечает |
| К6 | resolved | если в настройках tailnet включено «Override local DNS», `tailscale0` становится DNS по умолчанию, и `tailscaled` пересылает запросы шлюза сам, меткой `0x80000` — мимо VPN | утечка DNS самой машины |
| К7 | `forward` (`policy drop`, `net/nft.py:366-379`) | LAN → `100.64.0.0/10` отбрасывается | устройства дома не видят tailnet через шлюз; это не цель ТЗ (subnet router не делаем) |

К1–К4 исправляются в XGW, К5 и К6 находит `xgw diag` и объясняет, К7 остаётся как есть
и описывается в README.

Синтаксис правил из раздела 2 проверен `nft -f` в одноразовой netns (nft 1.1.6).

## 2. Т1: совместимость — правила

### 2.1. Как ходит сам Tailscale

Настройка `[tailscale] route`:

- `"direct"` (по умолчанию) — соединения `tailscaled` идут напрямую, мимо Xray, в
  любом режиме. Трафик Tailscale и так зашифрован WireGuard, а прямой путь нужен для
  P2P и правильного STUN. Провайдер видит, что на шлюзе работает Tailscale, но не видит,
  что внутри.
- `"vpn"` — если провайдер Tailscale режет: пока Xray здоров, `tailscaled` идёт через
  перехват (DERP по TCP 443 работает, P2P по UDP — как получится). Когда Xray не
  отвечает (`XRAY_DOWN`) или правила в `blocked` — напрямую, как у бота Telegram.
  Иначе Mini App и SSH пропадут вместе с VPN.

### 2.2. Таблица `ip xgw`

```
set ts_direct { type mark; }                    # пусто или { 0x80000 }

chain output {                                    # перед «meta mark set 1»
    ...
    meta mark and 0xff0000 @ts_direct return      # К1: сокеты tailscaled — мимо перехвата
    oifname "tailscale0" return                   # К2: всё внутрь tailnet, в т. ч. 100.100.100.100:53
    ...
}

chain block_output {                              # режим blocked, перед reject
    ...
    meta mark and 0xff0000 == 0x80000 accept      # К3: сам tailscaled
    oifname "tailscale0" accept                   # К3: ответы SSH, панели, Funnel внутри tailnet
    ...
}
```

- Набор `ts_direct` нужен для `route = "vpn"`. Демон кладёт в него `0x80000` при
  `XRAY_DOWN` и в `blocked` и убирает, когда Xray здоров (`nft add/delete element`, без
  перезагрузки таблицы). При `route = "direct"` элемент лежит в наборе всегда, и он
  записан прямо в шаблоне таблицы.
- В `block_output` `tailscaled` пропускается всегда, а не по набору. Иначе в `blocked`
  при `route = "vpn"` (Xray здоров, перехвата нет) Tailscale не ходил бы никуда.
- Правила появляются, только когда `tailscale0` существует или `tailscaled` активен
  (`systemctl is-active tailscaled`). Если `tailscaled` запустится позже, демон
  перезагрузит правила на следующем шаге (а после Ф2 — по событию).

### 2.3. Таблица `ip6 xgw6`

В `v6_guard` перед reject (К4):

```
oifname "tailscale0" accept
meta mark and 0xff0000 == 0x80000 accept
```

В режиме `proxy` (IPv6 машины через Xray) — то же, что в 2.2, для IPv6.

### 2.4. `xgw diag`, раздел «Tailscale»

| Проверка | OK | WARN / FAIL |
|---|---|---|
| служба | `tailscaled` активна, `BackendState = Running` (из `tailscale status --json`) | не установлен — «не используется» (это не ошибка); `NeedsLogin` — WARN со ссылкой входа |
| правила | К1–К4 загружены (как `v6_guard` в Ф1) | FAIL: Tailscale работает, а исключений нет |
| маршрут | `tailscale netcheck`: UDP есть, ближайший DERP с задержкой | WARN: нет UDP — только через DERP |
| К5 | WAN-адрес, шлюз и DNS провайдера вне `100.64.0.0/10` | WARN: «провайдер выдаёт адрес CGNAT — Tailscale отбросит его пакеты; включите `tailscale set --netfilter-mode=off` (XGW держит фаервол сам)» |
| К6 | у `tailscale0` нет `DefaultRoute` в resolved | WARN: «Override local DNS включён — DNS шлюза идёт мимо VPN; выключите его в консоли tailnet или `tailscale set --accept-dns=false`» |
| чужие таблицы | цепочки `ts-*` считаются своими, в список посторонних не попадают | — |

### 2.5. Тесты Т1

- Юнит (FakeKernel): правила 2.2–2.3 появляются при «tailscaled активен» и не
  появляются без него; набор `ts_direct` при `direct`/`vpn`; перекладка при
  `XRAY_DOWN` и `blocked`; diag К5 и К6 по подставным данным.
- Стенд netns (`tests/stand`): в ns `gw` — dummy-интерфейс `tailscale0` с адресом
  `100.64.0.1/10`, таблица 52 и правила `5210/5270` как у Tailscale. Процесс-заглушка
  открывает сокет с `SO_MARK 0x80000` к адресу в `inet`.
  - в режиме `on`: соединение заглушки идёт напрямую (сервер в `inet` видит адрес WAN,
    а не Xray); обычный сокет — через Xray; DNS на `100.100.100.100` уходит в
    `tailscale0`, а не в Xray;
  - в `blocked`: заглушка соединяется, обычный сокет отбит;
  - при `ipv6 = "off"`: IPv6 в `tailscale0` проходит, обычный IPv6 наружу отбит;
  - `route = "vpn"`: при живом Xray заглушка идёт через Xray, при остановленном —
    напрямую.

## 3. Т2: удалённый доступ к шлюзу

### 3.1. SSH

- Основной путь — **Tailscale SSH** (`tailscale set --ssh`): sshd открывать в
  интернет не нужно, вход — по учётной записи tailnet, правила — в консоли tailnet
  (по умолчанию владелец входит не под root, с периодическим повторным входом в
  браузере).
- Если на шлюзе уже работает OpenSSH — он доступен по адресу `100.x` шлюза без
  настройки; XGW его не трогает.
- Ответы SSH проходят и в `blocked` (`ct direction reply` и `oifname "tailscale0"`
  в `block_output`), и при остановленном Xray. Это заодно страхует испытания
  на реальной машине: связь с исполнителем не рвётся окном blocked.

### 3.2. Панель XGW по tailnet

- `tailscale serve --bg --https=8443 http://127.0.0.1:8781` — панель открывается
  **только** с устройств tailnet по `https://<шлюз>.<tailnet>.ts.net:8443/`. Сертификат
  выдаёт Tailscale, из интернета этот адрес недоступен (это Serve, не Funnel).
- Панель (`watch/panel.py:980`, `_hosts`) принимает ещё один `Host` — имя шлюза в
  tailnet с портом 8443, и только когда Serve включён из панели. Вход — как сейчас:
  токен или одноразовый код (`new_login`/`use_login`), cookie `SameSite=Strict`.
- Команда бота `/panel` (только в личном чате) присылает одноразовую ссылку
  `https://…ts.net:8443/?login=КОД` — 15 минут, один вход. Ссылка работает только на
  устройстве с включённым Tailscale.
- На телефоне одновременно работает только один VPN: пока включён Tailscale, другой
  VPN-клиент телефона выключен. Для Mini App (Funnel) Tailscale на телефоне не нужен.

### 3.3. Карточка «Tailscale» в панели

Для заказчика — без терминала:

- состояние: не установлен / нужен вход / работает; имя шлюза в tailnet, адрес `100.x`;
- «Войти в Tailscale» — `tailscale login` в фоне, ссылка из `AuthURL`
  (`tailscale status --json`) показывается кнопкой и QR-кодом;
- переключатели: «SSH через Tailscale» (`tailscale set --ssh` / `--ssh=false`),
  «Панель по tailnet» (`tailscale serve … / serve --https=8443 off`);
- «Маршрут Tailscale»: напрямую / через VPN (2.1);
- предупреждения К5 и К6 с кнопкой исправления (`tailscale set --netfilter-mode=off`,
  `tailscale set --accept-dns=false`) — каждая только по нажатию.

Формат `tailscale status --json` Tailscale не обещает сохранять. Поэтому поля
(`BackendState`, `AuthURL`, `Self.DNSName`, `Self.TailscaleIPs`) читаются
осторожно: если поля нет — «неизвестно», а не сбой. Тесты строятся на настоящем выводе
из Т0.

Демон обращается к `tailscaled` через CLI `tailscale` (сокет
`/run/tailscale/tailscaled.sock`, демон XGW — root). Подключение к сокету из-под
`ProtectSystem=strict` (`packaging/xgw.service`) проверяется на стенде; если не
выйдет — `ReadWritePaths=/run/tailscale`.

### 3.4. Тесты Т2

- Юнит: разбор `tailscale status --json` (Running, NeedsLogin с `AuthURL`, Stopped,
  нет CLI); команды карточки — подставной runner; `Host` панели принимается только
  при включённом Serve; `/panel` — одноразовый код, только из личного чата.
- Стенд: панель отвечает на `Host: gw.example.ts.net:8443` при включённом флаге и
  отказывает без него.

## 4. Т3: Mini App — бэкенд

### 4.1. Как это устроено

```
телефон (Telegram, WebView)
   │  https://<шлюз>.<tailnet>.ts.net/            ← публичный адрес Funnel, порт 443
   ▼
ретранслятор Funnel (Tailscale) — TLS не расшифровывает
   │  через tailnet к шлюзу
   ▼
tailscaled на шлюзе — заканчивает TLS → http://127.0.0.1:8782
   ▼
демон xgw: сервер Mini App (поток, как панель)
   ├─ /           страница (ui/miniapp.*)
   ├─ /api/auth   initData → сессия
   ├─ /api/state  состояние (маскированное)
   └─ /api/act    действие из белого списка
```

- TLS заканчивается на самом шлюзе: ни Tailscale, ни провайдер содержимое не видят.
  Ретранслятор видит только имя (SNI) и объём.
- Адрес постоянный (имя шлюза в tailnet): бот ставит его в кнопку меню чата владельца
  (`setChatMenuButton`, `web_app`) один раз и обновляет при смене имени.
- Порт 443 занят Funnel под Mini App, панель — на 8443 через Serve (Serve и Funnel на
  одном порту одновременно нельзя).

### 4.2. Вход: проверка `initData`

Страница отправляет `Telegram.WebApp.initData` в `POST /api/auth`. Шлюз проверяет:

1. Подпись: `secret = HMAC_SHA256(key="WebAppData", msg=bot_token)`;
   `data_check_string` — все поля кроме `hash`, по алфавиту, `key=value` через `\n`;
   `hex(HMAC_SHA256(key=secret, msg=data_check_string)) == hash`, сравнение
   `hmac.compare_digest`.
2. Свежесть: `now - auth_date ≤ 300 с`, не из будущего больше чем на 60 с.
3. Одноразовость: `hash` запоминается на время окна свежести; повтор отклоняется.
4. Хозяин: `user.id == int(notify.telegram_chat_id)`. Mini App работает **только** при
   подключённом личном чате (id > 0). Если подключена группа — Mini App выключен, и
   панель объясняет почему.
5. Бот подключён и `notify.commands = true`.

Неудачный вход — общий ответ без подробностей, пауза 0,5 с, не больше 10 неудач в
минуту на весь шлюз (дальше 429 на минуту), событие в журнале
(`store.add_event("miniapp", …)`) без самих данных.

### 4.3. Сессия

Случайный токен (`secrets.token_urlsafe(32)`), только в памяти демона: 15 минут без
действий и не больше 2 часов всего. Передаётся заголовком `Authorization: Bearer`,
страница держит его в памяти (не cookie и не `localStorage`), поэтому CSRF невозможен.
Не больше 30 запросов в минуту на сессию. После смены токена бота все сессии
сбрасываются.

### 4.4. Белый список — общий с ботом

Логика `_control` и `_pin` (`watch/telegram.py:542, 569`) переносится в
`src/xgw/remote.py`. Её вызывают и бот, и Mini App, поведение бота не меняется.

| Действие | API | Подтверждение на странице |
|---|---|---|
| состояние | `GET /api/state` | — |
| VPN вкл | `POST /api/act {"name":"enable"}` | — |
| VPN выкл | `{"name":"disable"}` | `showConfirm`: «Интернет пойдёт напрямую, мимо VPN» |
| выбрать сервер | `{"name":"pin","tag":…,"ttl":"10m\|1h\|6h\|24h"}` | — |
| автовыбор | `{"name":"unpin"}` | — |
| подписки / запасные / замер | `refresh` / `scan` / `speed` | — |

Сервер выбирается по `tag`, а не по номеру. Через Mini App **нельзя**: подписки и
ссылки, токен бота, устройства мимо VPN, удаление серверов, установку, логи,
настройки Tailscale. Всё это — только в панели.

### 4.5. Что отдаёт `/api/state`

Только то, что бот уже пишет в `/status` и `/servers`: режим VPN и перехвата,
состояние, основной сервер, ручной выбор и срок, квота, серверы в работе (имя,
задержка, скорость, жив/нет, `tag`), число устройств. Весь текст — через
`masking.mask_text`. Адресов серверов, UUID, ссылок и путей нет; это проверяет
отдельный тест по демо-состоянию.

### 4.6. HTTP-сервер Mini App

- Слушает только `127.0.0.1:8782`. `Host` должен совпадать с именем шлюза в tailnet
  (`Self.DNSName` из `tailscale status --json`, без точки в конце); иначе 421. Прямой
  заход с самой машины отклоняется той же проверкой.
- Заголовки: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, `Content-Security-Policy: default-src 'none';
  script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' data:;
  connect-src 'self'; frame-ancestors https://web.telegram.org`.
  `Access-Control-Allow-Origin` не ставится.
- Тело — не больше 8 КБ, только `application/json`; методы — GET и POST.
- Отдельный класс `watch/miniapp.py`, не наследник панели: токена и cookie панели у
  него нет.

### 4.7. Токен бота — ключ от шлюза

С токеном можно подделать `initData`. Он хранится в `panel.json` (0600) и в журналы не
попадает. README: при подозрении на утечку — `/revoke` в @BotFather и новый токен в
панели.

### 4.8. Тесты Т3

Подпись `initData` (вектор, посчитанный в тесте от известного токена), просрочка,
повтор, чужой `user.id`, группа вместо личного чата, неверный `Host`, лимиты, нет
секретов в `/api/state`, каждое действие белого списка и отказ на остальные; бот после
переноса в `remote.py` — прежние тесты зелёные.

## 5. Т4: Funnel, кнопка меню, страница

- Карточка «Tailscale» → «Mini App в Telegram» → «Включить»: демон выполняет
  `tailscale funnel --bg --https=443 http://127.0.0.1:8782` (`--bg` — Funnel
  переживает перезагрузку и `tailscale down/up`). Если в tailnet не включены HTTPS или
  Funnel, CLI их включает или просит включить в консоли tailnet. Что именно он
  ответит, фиксирует Т0 на настоящей учётной записи; ссылку из ответа панель
  показывает кнопкой («Разрешить Funnel в tailnet», один раз в браузере).
- Окно согласия: «адрес Mini App доступен из интернета, вход — только из вашего чата с
  ботом»; «трафик Mini App проходит через ретранслятор Tailscale, но не
  расшифровывается»; «в режиме blocked дома Mini App откроется только с мобильного
  интернета».
- После включения бот ставит кнопку меню «XGW» в чате владельца; `/app` присылает
  кнопку «Открыть XGW» (`web_app`, только личный чат). При выключении —
  `tailscale funnel --https=443 off` и `setChatMenuButton {"type":"default"}`.
- Страница `ui/miniapp.html`, `miniapp.js`, `miniapp.css`: сверху переключатель VPN,
  состояние и основной сервер; ниже серверы с выбором срока; внизу три кнопки
  действий. Цвета — из `themeParams` (`var(--tg-theme-…)`), опрос состояния раз в 5 с,
  пока страница открыта.
- `xgw diag`: строка «Mini App» — выключен / Funnel работает, адрес / ошибка.
- Тесты: юнит — команды Funnel (подставной runner), `setChatMenuButton` при включении,
  смене имени и выключении (FakeTelegram); демо-сцена `tests/panel_demo` с подставным
  `Telegram.WebApp`, проверка в браузере (светлая и тёмная тема, ширина телефона,
  подтверждение выключения).

## 6. Фазы и файлы

| Фаза | Файлы | Готово, когда |
|---|---|---|
| **Т0** снимок на машине | программа для Kimi, только чтение | известно, почему Tailscale не заработал: `tailscale status`, `ip rule`, имена таблиц и цепочек nft, `resolvectl status tailscale0`, адреса WAN, `xgw diag` — до любого кода |
| **Т1** совместимость | `net/nft.py`, `net/capture.py`, `daemon.py` (набор `ts_direct`), `config.py` (`[tailscale] route`), `diag.py`, `src/xgw/tailscale.py` (новый: CLI, `status --json`) | тесты 2.5 зелёные; Tailscale и SSH живут в `on`, `blocked`, при остановленном Xray |
| **Т2** удалённый доступ | `tailscale.py`, `watch/panel.py` (`_hosts`, карточка), `ui/app.js`, `watch/telegram.py` (`/panel`) | тесты 3.4 зелёные; панель по tailnet и SSH из карточки |
| **Т3** бэкенд Mini App | `remote.py`, `watch/miniapp.py`, `watch/telegram.py`, `daemon.py`, `config.py` (`[miniapp] port = 8782`) | тесты 4.8 зелёные |
| **Т4** Funnel и страница | `tailscale.py`, `watch/telegram.py` (кнопка меню, `/app`), `ui/miniapp.*`, `watch/panel.py`, `diag.py` | тесты раздела 5 зелёные, демо проверено в браузере |
| **Т5** испытания на машине | программа для Kimi | см. ниже |

В каждой фазе — пункт ASSUMPTIONS и README там, где поведение видно заказчику.
`uninstall` убирает правила, Serve и Funnel, включённые XGW, но `tailscaled`, вход в
tailnet и настройку SSH не трогает.

**Т5 — программа испытаний:**

- SSH по tailnet с ноутбука или телефона;
- панель по `:8443` с телефона с включённым Tailscale;
- окно blocked из Ф1 — SSH не рвётся, Mini App открывается с мобильного интернета;
- остановка Xray — Tailscale и Mini App живы;
- Mini App с телефона дома и вне дома, каждое действие;
- выключение Mini App — кнопка меню пропала, Funnel снят.

## 7. Что нужно подтвердить заказчику

1. `route = "direct"` по умолчанию: провайдер видит, что на шлюзе Tailscale (но не
   содержимое). Если Tailscale у провайдера режут — переключить на «через VPN».
2. SSH через Tailscale SSH (вход по учётной записи tailnet), а не открытый OpenSSH.
3. Панель по tailnet (порт 8443, только устройства tailnet) — включать.
4. Выключать VPN из Mini App можно (как `/disable` у бота) — с подтверждением.
5. Начинаем с Т0: снимок на машине только для чтения, ничего не меняет.
