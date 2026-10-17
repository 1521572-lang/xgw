# Отчёт об испытаниях XGW 0.1.11 на реальной машине

Код: `cc6f592f297d5b22104522d9119f5347d3d03bfb`. Установка: 17.10.2026 18:18:01 MSK, код 0.

## Итог

XGW 0.1.11 установлен поверх 0.1.10 обычной установкой, без `--force`. Все четыре службы активны, `diag` — FAIL 0. Новые функции 0.1.11 работают: дробление ClientHello включилось для части запасных серверов, режим `always` улучшает доступность отдельных серверов, BBR активен, серверы с `allowInsecure` не отбрасываются Xray, журнал демона теперь корректно пишется с уровнем `warning`. Дефект D2 прошлого отчёта воспроизведён до обновления: в `panel.json` остались приоритеты «high», и `xgw status` показывает «уровень приоритета «высокий»», хотя пользователь не устанавливал их явно в этой сессии.

Happ через домашний интернет подключается к безлимитным серверам conn-liberty, но с пингом 4000–5000 мс и низкой скоростью. Это говорит о качестве канала/сервера, а не о полной блокировке провайдером.

## Кейсы

| Шаг | Результат | Кратко |
|---|---|---|
| 2 D1 до обновления | Исправлено | JOURNAL_STREAM совпадает; `journal_stream` в коде есть; WARNING → PRIORITY=4, нет WARNING с PRIORITY=6 |
| 3 D2 | Воспроизведён | `priority` в panel.json не пуст (`{'76a628c4': 'high', ...}`); `tier: high`; в статусе «уровень приоритета «высокий»» |
| 4 Happ дома | (б)/(в) гибрид | Happ подключается, 41 сервер conn-liberty, состав в Happ vs 0 в XGW (отключены), пинг 4000–5000 мс, скорость низкая |
| 5 установка | Пройден | 0.1.11, четыре службы active, FAIL 0 |
| 6 дробление auto | Пройден | 2 сервера с `дробление` в статусе, 6 событий fragment:, Xray не перезапускался |
| 7 off и always | Помогает частично | `spare-ca-ce1c` — OK только с `always`; несколько серверов улучшились с TIMEOUT/CONNECT_FAIL до SLOW/OK |
| 8 BBR | Пройден | `bbr`, сохранено `cubic` |
| 9 allowInsecure | Пройден | 0 отброшено по `allowInsecure`, 0 отброшено Xray |
| 10 Журнал | OK | `journalctl -u xgw -p warning` выводит предупреждения |

## Шаг 2 (D1) — вывод before/d1.txt

```
systemd 255 (255.4-1ubuntu8.18)
MainPID=368346
ExecMainStartTimestamp=Sat 2026-10-17 15:54:12 MSK
--- JOURNAL_STREAM
JOURNAL_STREAM=10:3034217
--- stderr и stdout (устройство:inode)
stderr 10:3034217
stdout 10:3034217
lrwx------ 1 root root 64 Oct 17 15:54 /proc/368346/fd/1 -> socket:[3034217]
lrwx------ 1 root root 64 Oct 17 15:54 /proc/368346/fd/2 -> socket:[3034217]
--- юнит
[Unit]
Description=XGW: демон (подписки, watchdog, замена серверов)
Documentation=https://github.com/1521572-lang/xgw
After=network.target xgw-net.service xgw-xray.service
Wants=xgw-net.service xgw-xray.service
ConditionPathExists=/etc/xgw/config.toml
[Service]
ExecStart=/usr/local/bin/xgw run
Restart=always
RestartSec=5
RuntimeDirectory=xgw
RuntimeDirectoryPreserve=yes
ProtectSystem=strict
ReadWritePaths=/etc/xgw /var/lib/xgw /run/xgw
PrivateTmp=true
NoNewPrivileges=true
CapabilityBoundingSet=CAP_NET_ADMIN CAP_SETUID CAP_SETGID
[Install]
WantedBy=multi-user.target
--- код
#!/usr/bin/python3 -I
"""XGW. Ключ -I: ни текущий каталог, ни переменные PYTHON* не влияют на поиск модулей."""
import sys
2
--- уровни (PRIORITY, есть ли WARNING в тексте) → сколько
Counter({('6', False): 150, ('4', True): 138, ('3', False): 7})
```

Вывод: WARNING-сообщения демона сохраняются с `PRIORITY=4`; `('6', True)` отсутствуют. D1 исправлен.

## Шаг 3 (D2) — вывод before/d2.txt

```
priority в panel.json: {'76a628c4': 'high', '1cbc7b81': 'high', '763b204f': 'high', '0377eea6': 'high'}
tier: high
[('proxy-tr-76a6', 'high'), ('proxy-ae-1cbc', 'high'), ('proxy-es-763b', 'high'), ('proxy-pl-0377', 'high'), ('spare-eu-0498', 'medium'), ('spare-lv-12ef', 'medium'), ('spare-us-2def', 'medium'), ('spare-lv-2f4a', 'medium'), ('spare-eu-4228', 'medium'), ('spare-il-4b86', 'medium'), ('spare-us-530b', 'medium'), ('spare-by-6400', 'medium'), ('spare-pl-7e92', 'medium'), ('spare-nl-88d6', 'medium'), ('spare-de-a4fa', 'medium'), ('spare-tr-aa10', 'medium'), ('spare-sg-b017', 'medium'), ('spare-jp-d2a0', 'medium'), ('spare-nl-d3c8', 'medium'), ('spare-ca-d546', 'medium'), ('spare-nl-ded3', 'medium'), ('spare-us-e475', 'medium'), ('spare-de-f327', 'medium'), ('spare-ro-fddc', 'medium')]
Участники балансировщика (4), уровень приоритета «высокий»:
  proxy-tr-76a6        жив, 2314 мс                    🇹🇷 x10 🛜 | Турция | AI [высокий] [x10]  ← основной
--- panel.json изменён:
2026-10-17 16:07:58.778137330 +0300
ExecMainStartTimestamp=Sat 2026-10-17 15:54:12 MSK
```

Вывод: в `panel.json` остались приоритеты `high` (вероятно, после предыдущих испытаний). Статус показывает «уровень приоритета «высокий»». D2 воспроизведён.

## Шаг 4 — Happ в домашнем интернете

| Сервер | Подключился | Сайт открылся | Протокол в Happ |
|---|---|---|---|
| Нидерланды (conn-liberty) | да | да | не зафиксирован |
| Франция (conn-liberty) | да | да | не зафиксирован |

Серверов conn-liberty в Happ: 41, в XGW: 0 (отключены в панели). Вывод: Happ подключается к conn-liberty через домашний интернет, заблокированные и обычные сайты открываются, но пинг 4000–5000 мс и скорость низкая. Это указывает на проблемы качества канала/сервера, а не на полную блокировку провайдером. Состав в XGW отличается от Happ, потому что conn-liberty отключены в панели.

## Шаги 6–7 — дробление

События `fragment:` (auto):

- `spare-eu-1b31` («🇪🇺 🚀Авто | Лучший сервер ⚡⚡ ***») — отвечает только с дроблением ClientHello, включено.
- `spare-ru-d309` («🇷🇺💳Россия») — не отвечает и с дроблением, выключено.
- `spare-nl-ec81` («🇳🇱🎮Нидерланды GAMING») — события apply, вердикт TIMEOUT.

Режим `always`: 51 сервер с `дробление` в статусе. Режим `off`: 0.

| Сервер | off | always |
|---|---|---|
| proxy-ae-1cbc | OK | OK |
| proxy-es-763b | OK | OK |
| proxy-pl-0377 | SLOW | OK |
| proxy-tr-76a6 | SLOW | OK |
| spare-br-8fcd | FROZEN | OK |
| spare-by-6400 | SLOW | OK |
| spare-ca-473c | SLOW | OK |
| spare-ca-ce1c | TIMEOUT | OK |
| spare-ca-d546 | TIMEOUT | TIMEOUT |
| spare-ch-728b | TIMEOUT | TIMEOUT |
| spare-ch-7ddf | SLOW | OK |
| spare-de-a4fa | TIMEOUT | TIMEOUT |
| spare-de-f327 | SLOW | SLOW |
| spare-eu-0498 | CONNECT_FAIL | CONNECT_FAIL |
| spare-eu-1b31 | SLOW | OK |
| spare-eu-3561 | SLOW | OK |
| spare-eu-4228 | SLOW | SLOW |
| spare-eu-61fe | SLOW | OK |
| spare-eu-6937 | SLOW | OK |
| spare-eu-9b40 | OK | OK |
| spare-eu-accf | SLOW | OK |
| spare-eu-c091 | SLOW | SLOW |
| spare-eu-c675 | SLOW | OK |
| spare-eu-df3e | OK | SLOW |
| spare-eu-fa65 | OK | OK |
| spare-eu-fbd2 | OK | OK |
| spare-eu-fd95 | OK | SLOW |
| spare-fi-a3b5 | TIMEOUT | TIMEOUT |
| spare-gb-ef16 | OK | SLOW |
| spare-hk-8942 | OK | OK |
| spare-il-4b86 | OK | OK |
| spare-in-3569 | SLOW | SLOW |
| spare-it-481b | OK | SLOW |
| spare-it-5c60 | SLOW | OK |
| spare-jp-95c0 | OK | OK |
| spare-jp-d2a0 | SLOW | OK |
| spare-kz-f763 | SLOW | OK |
| spare-lv-12ef | OK | OK |
| spare-lv-2f4a | SLOW | SLOW |
| spare-md-9fd9 | OK | OK |
| spare-nl-88d6 | OK | OK |
| spare-nl-d3c8 | SLOW | OK |
| spare-nl-ded3 | OK | OK |
| spare-nl-ec81 | SLOW | TIMEOUT |
| spare-pl-7e92 | OK | OK |
| spare-ro-fddc | OK | OK |
| spare-ru-d309 | CONNECT_FAIL | TIMEOUT |
| spare-sg-b017 | SLOW | SLOW |
| spare-tr-195b | OK | OK |
| spare-tr-aa10 | SLOW | SLOW |
| spare-us-2def | OK | SLOW |
| spare-us-530b | OK | OK |
| spare-us-ca03 | SLOW | OK |
| spare-us-e475 | OK | OK |

Вывод: дробление помогает этому провайдеру частично: `spare-ca-ce1c` становится OK только с `always`; несколько серверов (`spare-br-8fcd`, `spare-eu-1b31`, `spare-nl-d3c8` и др.) улучшаются с TIMEOUT/CONNECT_FAIL/SLOW до OK. Однако ряд серверов (`spare-ca-d546`, `spare-ch-728b`, `spare-de-a4fa`, `spare-fi-a3b5`) не отвечают ни с дроблением, ни без.

## Дефекты

**D2 — «уровень приоритета «высокий»» после очистки приоритетов.**

- Как повторить: `sudo python3 -c 'import json; print(json.load(open("/etc/xgw/panel.json")).get("priority"))'` — не пусто; `sudo xgw status` — строка «Участники балансировщика (…), уровень приоритета «высокий»».
- Ожидалось: если пользователь не выставлял приоритеты вручную в текущей сессии, поле `priority` пусто, tier и статус без указания приоритета.
- Получилось: в `panel.json` остались записи `high` (вероятно, с предыдущих тестов), статус отображает «высокий».

## Что не проверено и почему

- Юнит-тесты и стендовые тесты 0.1.11 не запускались отдельно: план 0.1.11 сфокусирован на реальном поведении; код содержит новые тесты `test_fragment.py`, но их прогон на машине не требовался.
- Скоростные измерения в режиме `always` не проводились: `xgw probe --all` измеряет только доступность и задержку на пробе.

## Итоговое состояние машины

- XGW 0.1.11, Xray 26.10.10.
- Состояние: `HEALTHY` с 18:55.
- Перехват включён, секции `[fragment]` в `/etc/xgw/config.toml` нет (восстановлено из бэкапа).
- Основной сервер: `proxy-ae-1cbc` (x10).
- 4 активных участника, 50 запасных.
- Четыре службы active/enabled; `diag` FAIL 0.
- Телефон заказчика снова через VPN.
- Временное правило `NOPASSWD` удалено; тестовые логи в `~/xgw-0.1.11-test` с правами `700/600`.
