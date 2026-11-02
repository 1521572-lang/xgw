# ADR: host guard после policy reroute

Статус 02.11.2026: принято для кандидата wave3g; приёмка ThinkCentre NOT_RUN.

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

Единственный текущий протокол — TEST-PLAN-REAL-MACHINE-0.2.0-wave3g.md. Mandatory off-preflight
25с, затем при остановленных xgw/xgw-net атомарно заменить только installed net/nft.py по
old/new SHA с root0600 backup. Dry nft-c проверяет новый on guard без применения. После
проверки4 installed файлов стартовать контроллер вoff. Только затем один enable25с с
независимым неизменным rollback. Полный installer/обновление ядер/scoped faults запрещены.

Новый sampler сохраняет фактические hook/priority/drop-rule counts перед bounded loaded:
приon ожидается postrouting10, forward, host_drop>=1, host_reject0. Layout не заменяет
Capture.loaded и не является счётчиком пакетов. Plain/marked prefix_ok с новым layout и
успешным возвратом закрывает только этот короткий host-кейс. Loadedunknown остаётся
неизвестностью соответствия; D1-on/D2/E4/LAN/UDP/IPv6/Tailscale и полная волна3 открыты.
Guardian возвращает подготовленный сетевойoff; новый файл после опыта остаётся установленным.
