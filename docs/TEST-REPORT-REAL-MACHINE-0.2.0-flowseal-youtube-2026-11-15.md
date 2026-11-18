# TEST-REPORT-REAL-MACHINE-0.2.0-flowseal-youtube-2026-11-15

Уточнение ОС ThinkCentre по [проверке `/etc/os-release`](reports/2026-11-15_desync-batch1.md).

Дата: прогон 2026-11-14 19:40 — 2026-11-15 00:45 UTC (§1 ориентир 6–10 ч выдержан).
PLAN = ebbb051, BASE = c411689 (установленный пакет соответствует BASE: nfqws2.py 278a5371…
= ad76983, net/nft.py 3060a07f… = фикс recapture 956db75 — сверены SHA), ветка gui-light.
Исполнитель GLM-5.3-Flash, сам на ThinkCentre (Ubuntu 24.04 LTS, Python 3.12.3, Xray 26.11.19
после перезагрузки машины 14.11, nfqws2 v1.0.7 038c97e5). Root — один systemd-run юнит с
FIFO + таймер-восстановления (keepalive). Источник Flowseal `2401b7a` (1.10.4): 37 файлов
скачаны и сверены (SHA-256 + git blob SHA-1) по [JSON каталогу](helpers/flowseal-youtube-source.json).

## Прямой ответ на вопрос §0

- **Всё, что проверено, — через лабораторный launcher (UTILITY=LAB), штатного перевода в продукт нет.**
- **PASS_1080_SHORT:** G12 (ALT9: hostfakesplit, host=www.google.com, ts, repeats=4, ip-id=zero)
  и оба штатных профиля XGW — hostfakesplit-md5 (A1) и fakedsplit-md5 (A2): 1080p держался 5+ минут
  с ровным продвижением и мгновенным seek (окно 19:46–20:22 UTC).
- **FAIL_PLAYBACK (×2 каждый):** G04, G05, G09, G10, G06 — при повторных пробах плеер не собирался;
  при этом curl-мелкие CH иногда проходили (page 200/api 405), а в худший момент (00:33 UTC) TLS
  к YouTube резался полностью у всех (5×000) при живом VPN-контроле.
- **CAUSE_UNRESOLVED→частично установлено:** тот же штатный hostfakesplit-md5 дал PASS в 19:50 и
  FAIL в 00:08 — условия линии меняются по часам и доминируют; отличить «метод слабее» от «окно
  хуже» на этой паре проб невозможно. Столл r3 остаётся необъяснённым.
- **1080p/1440p/2160p у лучших:** PASS_1080_SHORT есть только в окне 19:46–20:22; длинные 15+5 и
  1440p/2160p — NOT_RUN (см. ниже).

## Перевод (§5): 22/22 конфигураций, 0 потерянных опций

Генератор [make_flowseal.py](helpers/make_flowseal.py) из закреплённого JSON строит
[translation.json](helpers/flowseal-translation.json) и launcher
[flowseal_lab.py](helpers/flowseal_lab.py) (контракт nfq_lab.py: qnum/fwmark/lua от XGW,
замена профилей, execv реального BIN, DATA root 0755/файлы 0644, `--intercept=0` префлайт).
Каждая опция каждого профиля либо переведена, либо профиль исключён с причиной
(Discord/STUN-порты, hostlist discord.media, GameFilter=12); непереводимое прерывает сборку.
Блоб-декларации `--blob` вставляются перед первым использованием, каждая по одному разу.
Соответствие (§5): **все строки ADAPTED** — перечисленные отличия:
ts-default (подставлен справочный −600000 zapret1 1e1d1e2; версия bundled winws Flowseal
не сопоставлена), badseq-ACK default (−66000 справочный; явные +2/+1000/+10000000 перенесены
в SEQ), altorder=1 отсутствует в pinned Lua (G07/H07/S05/S07 — без altorder),
fake-http выделен в отдельный блок payload=http_req (одна стадия nfqws2 не выбирает blob по
типу payload), fake-tls=! заменён builtin fake_default_tls (680 байт, побайтово не доказан),
S09 multidisorder без split-pos — подставлен pos=midsld (исторический default zapret1).
Ближайшие к PARAMETER_MATCH — G06/G09/G10 (явные pos/seqovl/pattern, ip-id=zero, repeats default).
Открытый вопрос к разработчику: AltOrder-адаптер и/или список `host=`-шаблона в Lua.

Префлайт: **22/22 PASS** (`--intercept=0`, таймаут 15 с), после исправлений launcher-а:
/run смонтирован noexec → LAB перенесён в /opt/xgw/lib/xgw-flowseal.* (отклонение от §6.1,
зафиксировано); `--hostlist` без `@` (синтаксис nfqws2 ≠ winws); secure_file валидирует
resolve()-путь (установленный bundle — symlink) и допускает цель-каталог; декларации блобов.

## Живая матрица (§7.2) и контроли (§7.1)

Маршрут §4: 6 доменов (youtube, googlevideo, youtubei.googleapis, youtube-nocookie, ytimg, ggpht)
→ direct (freedom mark_bypass), applied JSON проверен, `xgw apply --now` (рестарт Xray штатный).
Движок: launcher в `zapret2.binary`, engine=auto, engine_offload=false, acct=1; worker/argv/очередь
сверялись по /proc/cmdline перед каждой пробой (например G12:
`hostfakesplit:host=www.google.com:repeats=4:ip_id=zero:tcp_ts=-600000`).

| ID | Проба | Результат |
|---|---|---|
| A0 (off) | 19:44 | FAIL — контроль воспроизведён (страница недоступна без движка) |
| A1 (hostfakesplit-md5) | 19:46–19:55 | **PASS_1080_SHORT** — 1080p 5+ мин (72.7→378.3, буфер 101→406), seek<5 с |
| A2 (fakedsplit-md5) | 19:55–20:02 | **PASS_1080_SHORT** — 1080p 5 мин (58.1→378.7), seek восстановился |
| A3 | — | NOT_RUN (интеграция launcher подтверждена префлайтом и argv) |
| G12 (ALT9) | 20:05 и 20:15 | **PASS_1080_SHORT** (повтор): 1080p 5+ мин (53.7→364.3), seek ок; первый старт — каркас страницы без плеера |
| G04 (ALT12) | 23:20, 23:24 | **FAIL_PLAYBACK ×2** — pлеер не собрался; debug-журнал показал живой hostfakesplit (fake-хост `*.www.google.com`, до/фейк/реал/фейк/после на Kyber-CH 1967 байт) |
| G05 (ALT13) | 23:50, 23:56 | **FAIL_PLAYBACK ×2** (curl page/api проходили — линии вероятностные) |
| G09 (general) | 23:59, 00:04 | **FAIL_PLAYBACK ×2** (page curl 000 — TLS режется) |
| G10 (ALT7) | 00:14, 00:20 | **FAIL_PLAYBACK ×2** |
| G06 (ALT2) | 00:36, 00:41 | **FAIL_PLAYBACK ×2** |
| A1-повтор (§8) | 00:08 | **FAIL** — тот же профиль, что и PASS в 19:50: доказательство изменения условий линии |
| G01, G02, G03, G07, G08, G11, G13–G17, S09 | — | **NOT_RUN** (окно 00:45 UTC: 5×000 подряд на page TLS при живом VPN; измерение не информативно) |
| H01–H21, S01–S22 (кроме S09), Q01–Q03, I01–I02 | — | **NOT_RUN** — обязательная TCP-матрица не завершена |
| H/S/Q/I NO_MATCH-анализ | — | Выполнен по спискам: list-general/ipset-all(заглушка 203.0.113.113) не содержат YouTube-имён — по источнику эти профили не должны выбирать YouTube-потоки; живой выбор не проверялся (worker не запускался в этой фазе) |

Вердикты: TRANSLATION=ADAPTED (все строки), DIRECT=PASS, NFQ_VIDEO=NOT_RUN (trace/pcap для
победителей не собирались), BENEFIT=NOT_ESTABLISHED (off-отказ и on-успех — в разные окна;
в одной фазе оба fail), UTILITY=LAB (штатные A1/A2 при этом NATIVE-профили, уже в продукте),
PLAYBACK=PARTIAL_720-уровень недостижим как вывод — только PASS_1080_SHORT у G12/A1/A2,
RESTORE=PASS.

## Главный опыт раунда

1. Линия меняется по часам: PASS_1080_SHORT в 19:46–20:22 у трёх методов, FAIL у всех в 00:08+
   — «причина столла r3» частично объясняется этим, но CAUSE_UNRESOLVED остаётся (механизм
   ночной фазы не вскрыт; утром 14.11 линия также отличалась).
2. hostfakesplit с host-шаблоном реально генерирует fake-хосты `…*.www.google.com` (genhost:
   «правая часть = шаблон») — семантика nfqws1 сохранена в nfqws2 Lua.
3. Launcher-контракт nfq_lab работает под управлением XGW: смена ID = off → JSON → preflight →
   auto → argv-сверка; все 22 конфигурации проходят сборку и разбор nfqws2.

## Возврат (§11)

Браузеры остановлены; config.toml **байтово идентичен** (youtube-домены и [zapret2] сняты),
ethtool идентичен, acct=0, LAB/DATA удалены, свои nft-объекты отсутствуют, применён штатный
`xgw apply --now` (Xray перезапущен штатно, PID зафиксирован), youtube-правил в applied JSON
нет, worker inactive, очередь отсутствует, HTTPS 200, панель 200. Watchdog и root-канал
остановлены. Установленный код не менялся (BASE: nfqws2 278a5371…, nft.py 3060a07f… — фикс
CODE сохранён). Вне git: freepool-пакет сохранён в /opt/xgw/lib/xgw.freepool-tip-20261114
(эксперимент с GUI по запросу владельца), приватные материалы прогона в /home/xxx/xgw-flowseal.AxjsOXXY
(0700): pcap/trace не собирались, есть логи префлайтов и результатов.

## Остаточные сомнения и следующий шаг

- Матрица неполна: G01–G03, G07, G08, G11, G13–G17, S09 и все H/S/Q/I — NOT_RUN.
- PASS_1080_SHORT не равен PASS_1080_LONG: 15+5 не проведены ни для одного метода.
- Для честного сравнения методов нужна фаза линии, где A1-контроль проходит; предложить
  повтор раунда в «хорошее» окно (утро/день) с уже исправленным launcher.
- Рекомендация по продукту: G12/ALT9 как дополнительный профиль не предлагать до PASS_1080_LONG
  в независимом окне; A1/A2 (штатные hostfakesplit-md5/fakedsplit-md5) уже присутствуют.
