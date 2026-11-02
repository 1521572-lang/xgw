# ADR: host guard после policy reroute

## Актуальное уточнение владельца 02.11.2026 — сохранять рабочий on

Шлюз уже используется по схеме XGW → Wi-Fi-роутер → устройства; владелец возвращает VPN
в on и требует исходить из этой рабочей схемы. Принимаем рабочий on за текущий baseline.
Актуальное ТЗ — TEST-PLAN-REAL-MACHINE-0.2.0-wave3q.md: readonly разбор STOP до запроса P,
без enable/disable/restart/install/faults и без изменения WAN/LAN/Tailscale.
Прежний always_off guardian не применять на рабочем on. Старые сценарии ниже — история;
будущий разрушительный тест требует восстановления исходного on, а не автоматического off.
SSH/sentinel не являются условием признания существующей работоспособности.
Подробно REVIEW-REAL-MACHINE-0.2.0-wave3k.md. Свойства доработок принимаются по фактам;
полнаяwave3 пока открыта, рабочая эксплуатация продолжается.

Wave3o4fbde2e принята как readonly сбор, не SB1PASS/причина. N partial1/2 остаётся.
Две строки широкой TLSкатегории не доказывают handshakefailure; oldscan устарел.
Review-wave3o фиксирует основания и ограничения. P сохраняет закрытый план до одной
попытки того же SB1 при точном O→current SBconfigdigest; N→O только filetime support.
Переходы VPN/узла/WAN/LAN/служб/правил запрещены. Реальнаяwave3p NOT_RUN.

Wave3p08cdf11: STOP_SINGLE_PROBE/rc3/request0/ValueError, контекст сохранён.
Измерения SB1 не было, точный exception site не записан; это пробел диагностики теста.
Актуальный Q — только чтения сохранённых файлов и safe stage/code/currentgateflags,
без curl/journal/GET/сканов/повтораP/переключений. Currentgate не точная старая ветвьP.
Review-wave3p фиксирует вывод из порядка исходников; реальнаяwave3q NOT_RUN.




Статус 02.11.2026: wave3g/h/i/j дали четыре plain HTTPS успеха. В wave3j
loaded=true/measured/complete/rc0 при on, actualguard postrouting10/forward/drop5/reject0.
Короткий host-кейс и измеренное соответствие приняты; полная волна3 открыта.
Точный разбор — REVIEW-REAL-MACHINE-0.2.0-wave3j.md.

Wave3l149ffec принята:608.141с/on bookends,6active/PID same/NRestartsdelta0,
sing-box nonprivileged/caps0×5/NoNewPrivs/DAC подтверждены; настройки прежние.
Отдельное клиентское использование/Tailscale в интервале не наблюдалось; LAN-счётчики
не являются атрибуцией потоку. Review-wave3l содержит точные пределы. Новый продуктовый
patch не требуется. Wave3m проверяет файловые/API/netlink границы отдельными capless
процессами с фактическими UID/GID/Groups; сеть/службы/VPN не изменяются. Исключение только
собственный пустой state-probe, если ошибочно разрешено создание: удалить свой inode,
зафиксировать FAIL, без правок каталога/конфигов. Live ip rule add/del запрещены.
Реальнаяwave3m NOT_RUN; полнаяwave3 открыта.


Wave3m09abf5c принята:6/6 actual permission cases с проверенной identity, root nft-read
control успешен, state-файл не создан, on/PID/настройки сохранены. Review-wave3m фиксирует
scope: отдельные capless UID/GID/Groups, не весь service sandbox; live ipruleadd NOT_RUN.
Новый дефект продукта не найден. Следующий wave3n выполняет небольшие HTTPS GET через
существующие постоянные SOCKS-входы SB, без смены основного pin/ядра/правил/режима VPN.
Это positive compatibility worker, не fault/E4 или все LAN/UDP/IPv6/Tailscale пути.
Реальнаяwave3n NOT_RUN; рабочий on сохраняется, полный wave3 acceptance ещё открыт.


Wave3ne4f6f2d: частичный результат1/2, не общийPASS. SB-2vless/d206/32769/.372с,
ownedlistener/TLS/контекст подтверждены; SB-1двеcurl97/HTTP0/bytes0. УспехSB2 исключает
глобальную неспособность процесса, но не endpoint-specific права/конфиг/маршрут SB1.
Случайнаяпоhealth выборка2из71 не доказывает проблему продукта. On/6PID/settings/pin
сохранены. Новый runtimepatch пока не обоснован. Wave3o читает только существующие
свидетельства/журналы/lastscan, не повторяет запросы и не меняет рабочий шлюз.
Исторический mapping по filetimes не скрывает отсутствие старого configdigest.
Review-wave3n фиксирует пределы; O_NOT_RUN, полнаяwave3 открыта.


## Факты и оставшаяся неопределённость

[Отчёт wave3f](https://github.com/1521572-lang/xgw/blob/221eecb115cfb8629d8c0a6d49fd2212e5fe745b/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3f-2026-11-02.md)
повторил отказ plain TCP за0.065с при успешном marked HTTPS32769/200. Inbound согласован,
IPv4 LISTEN на loopback есть, proxy lookup local/lo/tproxy; effective_mode=on. Enable rc0 за
6.183с, возвратoff25.146с, restore0.146с, WAN6/6True. Loaded on неизвестен: child_deadline4с.
Приёмочные гейты выполнения прошли; работоспособность ordinary host path не подтверждена.
Carrier1 в точках и успех marked не означают непрерывную связь модели; duringon UNKNOWN.

Исторический wave3e JSON содержит loaded неожиданного типа. Это согласуется со строковым
fallback старого sampler; точное значение безопасный фильтр не печатал. Формулировка старого
Markdown «поля нет» неточна. Это не доказательство loadedFalse и не новая неисправность ядра.

## Причина в изолированной фикстуре

Исходный guard проверяет oifname в filter OUTPUT10. Предшествующая route OUTPUT-chain меняет
skb mark и выполняет reroute вlo. Вывод из
[nft_chain_route.c Linux6.18](https://github.com/torvalds/linux/blob/v6.18/net/netfilter/nft_chain_route.c)
и [nft_meta.c](https://github.com/torvalds/linux/blob/v6.18/net/netfilter/nft_meta.c): новое skb dst
не заменяет исходный nf_hook_state.out этого hook; oifname следующего OUTPUT-chain может
показывать WAN. Это объясняет локальный reject при корректном отдельном route-get.

Один ограниченный unshare-netns A/B на WSL6.18.54.1 воспроизвёл именно этот вопрос, без Xray,
внешних сайтов или изменений сети хоста. Listener с IP_TRANSPARENT возвращал разные данные
относительно прямого сервера, поэтому accept проверял действительную доставку в TPROXY.

| Условие | Plain | Bypass-mark |
|---|---|---|
| off | DIRECT | — |
| исходный OUTPUT guard | ConnectionRefusedError | DIRECT |
| тот же guard в POSTROUTING | TPROXY | DIRECT |
| удалён proxy RPDB, новый guard сохранён | TimeoutError | DIRECT |
| удалена capture-table, новый guard сохранён | TimeoutError | DIRECT |

Все результаты получены в одном изолированном опыте. Тело product render_guard AST-совпало с
исполненным кандидатом, кроме поясняющей docstring. Это причинный результат фикстуры;
тождества ядра ThinkCentre/его причины и исправления на реальном шлюзе ещё не доказано.
Это не запуск полной VM suite, проверка VPN-транспорта, LAN, UDP, IPv6 или Tailscale.

## Решение и границы

[Изменён только render_guard](https://github.com/1521572-lang/xgw/blob/573b233bce881349e5ff4654600d3e077a9515f6/src/xgw/net/nft.py#L1052):

- host цепочка с прежним именем output переходит в filter POSTROUTING10, до SNAT;
- первая проверка iif!=0 возвращает пересылаемые пакеты: их защищает прежний scoped forward;
- исключения core/service/утверждённых direct соединений сохраняются;
- host отказ использует drop: reject недопустим в postrouting;
  это ограничение описано в [официальном nft manual](https://www.netfilter.org/projects/nftables/manpage.html);
- forward/transit остаётся на прежнем hook и с reject; guard не выставляет mark/ct approval;
- не добавлены accept поmark_proxy или общий established accept. При потере маршрута поток
  уходит к WAN и отбрасывается по фактическому oif, вместо прямого выпуска.

При отказе host клиент может получить timeout вместо немедленного reset. Это ожидаемая
смена отказа, не успех сети. Нельзя ради быстрого восстановления разрешить mark_proxy на WAN.
Остальные capture rules, RPDB, WAN/LAN profiles, sysctl, Tailscale route/fallback прежние.
Чистая установка всё ещё имеет legacy WAN IPv6-путь; этот PR не завершает его миграцию.

## Реальный следующий шаг

В [отчёте wave3g](https://github.com/1521572-lang/xgw/blob/6c93e22f153617168e8aa77afa2ad3ef7289462f/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3g-2026-11-02.md)
G1 успешно установил новый nft.py с backup/SHA/dry nft-c. Повторная замена не нужна.
Plain приon впервые получил200/32769/0.354с, marked200/32769/0.380с; enable8.801с0,
возврат25.172с/restore0.171с/nft0/WAN6/6True. Guard layout неизвестен: diagnostic4с остановился
на phaseconfig до быстрых фактов. Работоспособность одного host-запроса измерена; полного
доказательства механизма/соответствия/стабильности это не даёт.

Найдено ограничение test helper: inbound_problem вызывает полную rules(on), включая GeoIP,
и стоял ДО чтения actual guard. Старый phaseconfig охватывал несколько операций; нельзя
выдать неизвестную задержку за доказанную медленную config.load/DNS/GeoIP.

Wave3hbc24353 дал повторный plain200/32769/0.466с, enable8.533с0, rollback25.161с/0.161с,
nft0/WAN6/6True. Loadednull/8сdeadline наphase loaded. Guard querydeadline_or_error не
доказывает timeout: catch объединял ошибки процесса/разбора. Внутри loaded вновь вызывается
сборка rules; ранний завершённый inbound не исключает внутренние стадии. Уточнения и точные
permalink: REVIEW-REAL-MACHINE-0.2.0-wave3h.md.

Wave3ib32669a подтвердил actuallayout JSON0.064с икороткий host-кейс: plain200/32769/0.428с,
marked200/32769/0.436с, enable8.524с0, rollback25.126с/0.126с/nft0/WAN6/6True. Fullchild8с
не завершился на method__desired_problem. Новый быстрыйguard не определяет заднимчислом
причину старогоdeadline_or_error. Точные пределы: REVIEW-REAL-MACHINE-0.2.0-wave3i.md.

PurePython профиль мотивировал узкое parser-изменение351fb54. В wave3j новая версия
NFT10c1 установлена с backup и SHA, dry nft-c успешен; render/guard прежние. Loaded приon
впервые measured true/complete/rc0 в8с child-бюджете, _desired_problem returned1.099с.
Actualguard JSON0.025с подтвердил postrouting10/forward/drop5/reject0 при capture=true
до/после. Plain200/32769/0.307с, marked0.290с, enable8.034с0, rollback25.130с/0.130с,
nft0/WAN6/6True. Trace truncated48 не отменяет complete verdict. Это не A/B benchmark
и не определение исторической причины дедлайнов. Переменные и пределы — review wave3j.

Исторический протокол wave3k (до нового указания владельца): только read-only опись
предпосылок при off. Без установки/G1/enable/таймеров/захвата и без изменения адаптеров,
правил, конфигурации, ядер или Tailscale. Новый продуктовый PR по отчёту j не требуется.

Layout/checkpoint/loaded — разные наблюдения; layout считает правила, не пакеты.
Короткий host-кейс и его measured соответствие приняты, но LAN/UDP/IPv6/DNS/Tailscale/E4,
D1-on/D2/scoped faults и полная волна3 открыты. Возврат в подготовленный off — механизм
согласованного опыта; непрерывная связь вon UNKNOWN. Следующий активный опыт требует
независимой локальной страховки, не следующей команды Flash.
