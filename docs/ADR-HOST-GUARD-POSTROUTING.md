# ADR: host guard после policy reroute

Статус 02.11.2026: wave3g/h дали два функциональных plain HTTPS успеха на ThinkCentre;
фактический on-hook/полное соответствие политики ещё не подтверждены.

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

Единственный текущий протокол — TEST-PLAN-REAL-MACHINE-0.2.0-wave3i.md. Runtime573b233 прежний;
4 installed сверки, off-preflight25с, freshbaseline и один enable25с. Guard читается отдельным
worker: JSON3с, при неуспехеon один native3с, точные классы ошибок/rc/elapsed, private raw.
Полный diagnostic8с параллелен, до48 read_trace границ/active stack локального Capture.
Off diagnostic4с/guardJSON3с; общий25с не меняется. Partial при долгом enable остаётсяpartial.
G1/full installer/ядра/scoped faults запрещены, WAN/Tailscale/config не меняются.

Приon ожидается postrouting10/forward/drop>=1/reject0, capture state читается отдельно.
Loaded checkpoint и независимый guard-event не являются одним снимком. Contexton —
запрошенная фаза, не самостоятельное доказательство перехвата;
off checkpoint не переносить вon. Layout не заменяет loaded и не считает пакеты.
Plain/marked prefix_ok с новым layout и успешным возвратом закрывает только короткий host-кейс.
Loadedunknown остаётся неизвестностью соответствия; D1-on/D2/E4/LAN/UDP/IPv6/Tailscale/волна3
открыты. Guardian возвращает подготовленный сетевойoff, не версию файла.
