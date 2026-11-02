# WAN, LAN и условный маршрут Tailscale

## Актуальное уточнение владельца 02.11.2026 — сохранять рабочий on

Шлюз уже используется по схеме XGW → Wi-Fi-роутер → устройства; владелец возвращает VPN
в on и требует исходить из этой рабочей схемы. Принимаем рабочий on за текущий baseline.
Актуальное ТЗ — TEST-PLAN-REAL-MACHINE-0.2.0-wave3r.md: один запрос с новой текущей базой,
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

Qe768971 принята: readonly/context сохранён; единственный false — O→currentconfigdigest.
Pblocked/request0 остаётся; точная старая ветвь UNRECORDED, filetime support не digestproof.
R вводит новую baseline, один текущий uniquevless/d по referencekeyO; historicalidentity
UNPROVEN (короткийключ не неизменность endpoint). Полный currentconfigdigest/identity
фиксируются ДО однойпопытки, любое изменение внутри R→STOP. Нет отката кO/переключений.
Review-wave3q содержит решение; реальнаяwave3r NOT_RUN. Npartial не переписывается вPASS.





Статус: требование о сохранении входящего подключения принято как ограничение.
В wave3d реализовано сохранение текущего WAN при повторной/частичной установке:
без NM modify/reapply, переключения IPv6 и повторного применения старых WAN sysctl.
Boot-ключи и журнал сохраняются без автоматической обратной миграции. Чистая установка,
явная миграция старого WAN и отдельный канал Flash — следующие задачи; их не считать готовыми.
Основание: уточнение владельца02.11.2026 — два физических адаптера, WAN к провайдеру,
LAN раздаёт сеть, Tailscale в некоторых случаях должен работать через VPN.

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


## Что показал реальный прогон

[Отчёт wave3b](https://github.com/1521572-lang/xgw/blob/cc0b021a9204a1238903628fb8766af5e47519f6/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3b-2026-11-02.md#L23-L42):
три восстановления off успешны, связь модели/владельца сохранилась, оба carrier1 в точках
измерения.0.137–1.018с — только выполнение restore после истечения15с lease. Это не полный
срок от последнего pulse и не доказательство поведения при enable. Установка дважды прервана
из-за ритма оператора; rc0 нет, enable/on-reinstall/D1/D2 не проверены. Доказательств физического
отключения WAN-порта нет; непрерывного carrier-мониторинга также не было.

## Граница ответственности

WAN несёт двунаправленный транспорт к провайдеру и VPN-серверу. LAN получает обычный трафик
клиентов и возвращает ответы. У XGW по TPROXY пользовательский поток приходит с LAN в локальный
Xray, а внешнее соединение к VPN-серверу создаёт процесс ядра и отправляет через WAN. Поэтому
«управлять профилем WAN» и «участвовать в маршрутизации через WAN» — разные действия.
Разделение локальных output и транзитных forward-путей описано в
[Netfilter hooks](https://wiki.nftables.org/wiki-nftables/index.php/Netfilter_hooks);
TPROXY требует локальной доставки по policy routing
([документация ядра](https://docs.kernel.org/networking/tproxy.html)).

Для VPN только клиентов LAN достаточно перехватывать входящие с LAN потоки и обеспечивать
маршруты/обратный путь. Но требования этого шлюза шире: есть трафик самой Ubuntu и Tailscale.
Автоматическое `capture.local=false` уберёт существующий путь tailscaled через Xray. Поэтому
его не принимать как исправление потери связи. Сохранять route/fallback Tailscale и различать
соединения самого tailscaled и трафик устройств tailnet через exit-node.

В коде уже разграничены:
- [LAN/lo ingress и host output](https://github.com/1521572-lang/xgw/blob/f4a27b7f0893e78f44481087d9fd64e2fd01654f/src/xgw/net/nft.py#L645-L705): входящий WAN в TPROXY не направляется;
- [политика Tailscale](https://github.com/1521572-lang/xgw/blob/f4a27b7f0893e78f44481087d9fd64e2fd01654f/src/xgw/config.py#L123-L133): route и автоматический DERP fallback;
- [независимый guard](https://github.com/1521572-lang/xgw/blob/f4a27b7f0893e78f44481087d9fd64e2fd01654f/src/xgw/net/nft.py#L1052-L1115): host output и выбранные forward ingress, не выключение NIC.

Чистая установка пока имеет отдельное legacy-изменение WAN:
[wan_ipv6_off](https://github.com/1521572-lang/xgw/blob/f4a27b7f0893e78f44481087d9fd64e2fd01654f/src/xgw/net/nm.py#L273-L316)
может изменить ipv6.method профиля и вызвать device reapply; для netplan используется
sysctl disable_ipv6. Это существующий код, не новый вызов отключения карты в guard. Наличие
такого пути не доказывает, что он вызвал D2. Обычное включение перехвата и повторная установка
должны рассматриваться отдельно.

## Доработки для отдельного PR

1. **Явное владение профилем WAN.** В обычном цикле VPN сохранять адреса, DHCP/PPPoE,
   default route, DNS, MTU, IPv6 и активность профиля WAN. Не выполнять device disconnect,
   connection up/down, reapply/перезапуск NetworkManager ради enable/disable/failover.
   Установку физической LAN-сети отделить от обновления runtime-кода и политики VPN.
2. **Миграция старого IPv6 без автоматического переподключения.** Проверить journal nm_wan
   и sysctl: переключение новой политики не должно незаметно ни повторно выключить IPv6,
   ни вернуть старый профиль. Сохранить фактическую текущую настройку до отдельной операции
   миграции. IPv6 не должен получить прямой обход защиты LAN/host: существующие nft v6_guard,
   перехват и исключения внешних VPN/Tailscale-соединений проверить до удаления legacy writes.
   Просто удалить wan_ipv6_off без этой проверки недостаточно.
3. **Разделить политику клиента и управления.** LAN/host VPN и условный Tailscale сохранить.
   Для Flash выделить проверяемый служебный путь по отдельному процессу/cgroup/netns, с явным
   DNS и маршрутами. Не разрешать весь трафик пользователя/root, не делать общий established
   accept: это может открыть обход VPN. Связь Flash, Tailscale и пользовательский VPN проверять
   раздельно; исправность Tailscale сама по себе не доказывает доступность модели.
4. **Реальная приёмка.** До/после enable, disable, смены узла и сбоя ядра сравнить хеши
   разрешённого набора свойств WAN-профиля, IP/default route/DNS/MTU и наблюдать carrier.
   Проверить новые LAN TCP+UDP, IPv6-политику, прямой/черезVPN/DERP-fallback Tailscale и канал
   Flash. До этого независимая локальная страховка обязательна. Не считать socket.connect
   через TPROXY доказательством внешнего TLS/получения тела.

## Следующий безопасный опыт

Отчёт b7be627 подтвердил автономные окна25/45с и сохранение WAN через прерванную установку.
Затем по отдельной команде владельца установка завершилась с rc0 вне окна; это не PASS
45-секундного бюджета. Дальнейшая переустановка ради завершения не нужна.

Отчёт wave3e9677cb9 подтвердил enable rc0 за9.279с и возвратoff за25.167с (restore0.167с),
WAN6/6True, carrier1 в точках. Во времяon plain TCP получил ConnectionRefusedError за0.089с,
а marked-проба того же этапа прочитала32769байт/HTTP200. Вoff обе пробы успешны. Причина
различия путей не установлена; ни физическое отключение WAN, ни ТСПУ этим не доказаны.
Связь во времяon UNKNOWN; loaded в Markdown UNKNOWN без значения, нужен исходный артефакт.

Отчёт wave3f221eecb повторил plainTCPrefused0.065с при исправных inbound/listener/proxy lookup;
loadednull/child_deadline4с. Один изолированный netns A/B воспроизвёл отказ host guard вOUTPUT
после reroute: hook видит прежний WAN oif. Новый host guard проверяет фактический oif в
POSTROUTING, при неразрешённом выходе drop. Forward guard прежний. Никакого нового accept
поproxy mark нет. Причина ThinkCentre ещё требует подтверждения; факты и границы в
`ADR-HOST-GUARD-POSTROUTING.md`.

Wave3g6c93e22 успешно установил nft.py; plainon впервые200/32769/0.354с, marked тоже успешен,
rollback25.172с/restore0.171с/nft0/WAN6/6True. Повторять обновление не нужно. Фактический
on-hook и loaded не получены: test child4с остановился до layout. Его ранняя стадия включала
тяжёлый inbound_problem/rules(on), поэтому сборщик переставлен, без нового продуктового PR.

Wave3hbc24353 повторил plainHTTPS успех0.466с, restore25.161с/0.161с/nft0/WAN6/6True.
Loaded8сdeadline иguard deadline_or_error остаются неизвестностями. Последнее не является
доказанным timeout, подробнее в REVIEW-REAL-MACHINE-0.2.0-wave3h.md.

Wave3ib32669a впервые подтвердил actualpostrouting10/forward/drop5/reject0, plainтретий
успех0.428с, rollback25.126с/WAN6/6True. Короткийhost-кейс принят; loadedchild8состановился
на_desired_problem. Историческаяпричинаh остаётсянеизвестной. Подробно REVIEW-REAL-MACHINE-0.2.0-wave3i.md.

Wave3j8cdf9bc подтвердил loaded=true/measured/complete/rc0 приon в8с child-бюджете,
actualguard JSON0.025с postrouting10/forward/drop5/reject0, plain0.307с/marked0.290с
с HTTP200/32769 байт. Enable8.034с0, rollback25.130с/restore0.130с/nft0/WAN6/6True.
Новая parser-версия NFT10c1 установлена один раз, четыре файла совпали, dry nft-c успешен.
Принят короткий host-кейс и его измеренное соответствие. Состояние после HEALTHY/off/
pooloff; непрерывная связь вon, LAN/UDP/IPv6/DNS/Tailscale/E4/D1-on ещё не доказаны.

Исторический протокол wave3k (до нового указания владельца): только чтение приoff для
получения предпосылок независимой LAN/E4/Tailscale приёмки. Не повторять G1/установку/enable,
не запускать захват, не менять WAN/LAN/sysctl/config/Tailscale/ядра. Наличие инструмента,
lease или neighbour не закрывает гейт. Отсутствующие ответы владельца — UNKNOWN.
При следующем активном опыте независимый локальный возврат обязателен; incoming outage
>1 минуты нельзя восстанавливать следующей командой модели. Полная волна3 остаётся открыта.
