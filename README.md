# XGW — шлюз Ubuntu 26.04 на Xray-core с автопереключением VPN-серверов

XGW превращает машину с Ubuntu 26.04 в шлюз для всей Wi-Fi-сети: nftables
(TPROXY) перехватывает трафик устройств и самой машины и отдаёт его Xray-core,
а Xray сам выбирает живой сервер.

## Зачем

Провайдер (ТСПУ) не рвёт соединение с VPN-сервером, а «замораживает» его: после
15–20 КБ данных в одной TCP-сессии пакеты перестают приходить. ICMP-пинг,
TCP-рукопожатие и HTTP HEAD проходят, поэтому клиенты считают сервер живым и не
переключаются. Счётчик байтов работает на каждое соединение отдельно — находит
«заморозку» только скачивание тела больше порога.

Поэтому проверка в Xray — `burstObservatory` с `httpMethod: "GET"` (ядро
скачивает тело целиком; поле и дочитывание тела появились в v25.7.23). Проба
падает по таймауту на «замороженном» сервере, и балансировщик исключает узел —
новые соединения уходят через рабочий не позже чем за 1–2 цикла
`interval × sampling`. У sing-box (urltest) и mihomo (url-test) проверка —
зашитый в код HEAD-запрос, они «заморозку» не видят.

```
Устройства Wi-Fi ──► Wi-Fi-роутер (точка доступа) ──► LAN Ubuntu-шлюза
                                                          │
   Приложения Ubuntu ──► nftables output ─┐              │
                                           ▼              ▼
                              nftables prerouting (TPROXY, метка 1)
                                           │
                                     Xray (tunnel-in)
                              DNS→dns-out, RU→direct,
                        прочее → балансировщик auto (leastPing)
                     GET-пробы burstObservatory ──► VPN-серверы
                                           │
                              сокеты Xray и прямые запросы XGW
                              уходят в WAN с меткой 2 (мимо перехвата)
```

Переключением управляет только Xray. XGW работает рядом: тянет подписки,
генерирует конфиг, применяет изменения на лету через API (`xray api ado/rmo/
adrules` — Xray не умеет перечитывать конфиг), следит за состоянием (watchdog,
скан запасных, утечки), уведомляет и показывает статус.

## Статус реализации

| Этап | Содержание | Статус |
|---|---|---|
| 1 | Конфиг, подписки, парсеры ссылок, генератор, загрузка Xray, `xgw generate`, `xray run -test` | ✅ готов |
| 2 | API (ado/rmo/adi/rmi/adrules/bi), diff, применение без разрыва, метрики, watchdog-состояния, скан запасных, замена участников | ✅ код и тесты (включая живые API-тесты); стендовые проверки — на Linux-машине |
| 3 | nftables/TPROXY, dnsmasq, перехват DNS, fail-closed, enable/disable, стенд | план |
| 4 | install/uninstall, systemd, NetworkManager, сон, ufw, diag, уведомления, страница статуса | план |
| 5 | IPv6, TUN-inbound, Telegram-бот, правила per-device | опционально |

Сеть хоста не меняется до прохождения стенда из раздела 9 ТЗ (network
namespaces); изменения сети — только командами XGW с проверкой и откатом.

## Требования

- Ubuntu 26.04 x86_64 (arm64 — желательно), Python 3.11+ (в 26.04 — 3.14).
- Только стандартная библиотека Python; внешние программы: `nft`, `ip`,
  `nmcli`, `systemctl`, `dnsmasq`, `xray`.
- Xray-core ≥ 25.7.23 (официальный бинарник; SHA-256 сверяется с `.dgst`).

## Установка (после завершения этапов 2–4)

```bash
sudo xgw install     # проверки diag, пакеты, профиль LAN, службы, первая генерация
```

Подготовка роутера, проверка, аварийное отключение и удаление описаны в
разделах ниже — они активируются на этапе 4.

### Подготовка Wi-Fi-роутера (режим точки доступа, рекомендуется)

1. Переведите роутер в режим точки доступа (Access Point): DHCP на нём выключить.
2. Кабель из LAN-карты шлюза — в **LAN-порт** роутера.
3. Wi-Fi devices получают адреса от dnsmasq шлюза (192.168.50.x) и видны
   шлюзу по отдельности (bypass_hosts, статика).

Альтернатива — режим `router_mode = "router"`: кабель в WAN-порт роутера,
dnsmasq выдаёт один адрес самому роутеру (двойной NAT, обход VPN только для
роутера целиком).

## Разработка и тесты

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"   # Windows: .venv\Scripts\python
.venv/bin/python -m pytest tests/ -q          # юнит-тесты (без root)
.venv/bin/python -m ruff check src tests      # линтер
```

- Golden-файлы пересоздаются `XGW_REGEN_GOLDEN=1 pytest tests/ -q`
  (используйте только после осознанного изменения генератора).
- Скачивание Xray для локальной проверки: см. `xgw.xraycore.binary`
  (`download_release`), кладётся в `tools/xray` (gitignored).
- Стенд на network namespaces (раздел 9 ТЗ) требует Linux и root — в репозитории
  появится в `tests/stand/`; без root тесты пропускаются.

### Проверка конфига вручную

```bash
xgw generate --config config.example.toml --out /tmp/config.json
xray run -test -c /tmp/config.json
```

## Структура

```
src/xgw/
  cli.py config.py paths.py log.py masking.py model.py store.py
  fetch.py marknet.py            # HTTP- и DoH-клиент с SO_MARK
  parsers/    common.py vless.py vmess.py trojan.py ss.py hysteria2.py xray_json.py
  xraycore/   binary.py (api.py metrics.py service.py — этап 2)
  generator/  builder.py validate.py (diff.py — этап 2)
  apply/ applier.py rotation.py (этап 2)   net/ nft.py … (этап 3)
  watch/ checks.py states.py … (этап 2)    diag.py install.py uninstall.py (этап 4)
tests/       fixtures/ golden/ test_parsers.py test_generator.py …
```

## Безопасность

- Конфиг `/etc/xgw/config.toml` — 0600; конфиг Xray — 0640 root:xray.
- Ни один секрет (UUID, пароли, ключи, токены) не попадает в логи, статус и
  экспорт: всё проходит через `xgw.masking` (UUID → последние 4 символа,
  секреты → `***`, URL подписок → только домен).
- Служебные порты слушают только 127.0.0.1 (кроме DHCP на LAN и, по желанию,
  страницы статуса). Телеметрии нет; внешние запросы — только к URL из
  конфигурации и к GitHub за Xray.
- Временные JSON для API-вызовов — 0600, удаляются сразу после вызова.

## Частые проблемы

- **Подписка отдаёт не то** — панели выбирают формат по User-Agent; задайте
  `user_agent` в `[[subscriptions]]` (например, `v2rayN/6.0`).
- **Clash/sing-box подписки не поддерживаются** — это ограничение по ТЗ
  (проверка «заморозки» — только Xray GET-пробами).
- **hysteria2-ссылки пропускаются с предупреждением** — поля
  hysteria2-outbound не описаны в документации; включается после проверки
  установленной версии (см. ASSUMPTIONS.md).

## Удаление

`sudo xgw uninstall` возвращает систему в исходное состояние (таблица nftables,
маршруты, профиль NetworkManager, dnsmasq, sysctl, службы) — реализуется на
этапе 4 вместе с install.
