# Разбор wave3l: наблюдение рабочего on принято

[Фактический отчёт Flash](https://github.com/1521572-lang/xgw/blob/149ffecefb966b9f33d69b58868d270a3fc93ec9/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3l-2026-11-02.md), commit149ffecefb966b9f33d69b58868d270a3fc93ec9,
получен через Git FF. TestedHEADfe5348ef9af9d3f4bb2992e8143a37a90bd81e60,
tree96a9e57f2283cc0fb0c435d7f2f2c18d45b4c6cc. Product pin351fb54e074f4a7b497a8a4244fc74c6088788d7;
runtime diff пуст, installed4equal. Observer SHA0db2acf6fa27632ccbdd6294b44f3e20fecd14805a1a1ac6dcf56d153f1f1d46
совпал с frozen root600. Продукт не обновлялся, сеть не переключалась.

## Принятый измеренный результат

| Часть | Факт | Решение |
|---|---|---|
| Интервал | 608.141с, start/end rc0; существующий on сохранён | Наблюдение двух границ принято, повтор не нужен |
| Службы | active6/6; PID same6/6; NRestarts delta0×6 | Неизменные измеренные идентификаторы/счётчики |
| Sing-box | Один process identity; UID/GID match, аккаунт nonprivileged, forbidden groups absent, CapInh/Prm/Eff/Bnd/Amb0, NoNewPrivs1 | Процессные свойства подтверждены на обеих границах |
| DAC | Ожидаемые directory/file owner/group/modes для обоих ядер,4true | Метаданные подтверждены; actual denied attempts ещё не выполнялись |
| Guard | JSONok, postrouting10/forward/drop5/reject0 в обоих снимках | Ожидаемый layout подтверждён |
| Настройки/режим | Три файла прежние; pooloff, router_modeap, Tailscale routevpn; same interfaces/carrier1; clockstepfalse | Измеренное состояние сохранено |
| Журналы | Queryok,0rows, not truncated,0parseerrors | В выбранном ответе journal нет строк; не глобальное доказательство отсутствия всех ошибок |
| Итог | HEALTHY/on, ядра26.10.31/1.14.4, модель не переключала режим | Рабочая эксплуатация продолжается |

Точные места: [гейты](https://github.com/1521572-lang/xgw/blob/149ffecefb966b9f33d69b58868d270a3fc93ec9/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3l-2026-11-02.md#L22-L28), [свойства процесса/DAC/guard](https://github.com/1521572-lang/xgw/blob/149ffecefb966b9f33d69b58868d270a3fc93ec9/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3l-2026-11-02.md#L30-L47),
[счётчики и журнал](https://github.com/1521572-lang/xgw/blob/149ffecefb966b9f33d69b58868d270a3fc93ec9/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3l-2026-11-02.md#L48-L53), [ограничения и итог](https://github.com/1521572-lang/xgw/blob/149ffecefb966b9f33d69b58868d270a3fc93ec9/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3l-2026-11-02.md#L55-L76).

Новый дефект продукта из этого отчёта не следует; продуктовый patch/рестарт не нужен.
Повторять установку, G1, wave3j или десятиминутное наблюдение не требуется.
Включённый VPN и схема XGW → роутер → устройства остаются исходным рабочим состоянием.

## Пределы результата

Два снимка не дают непрерывной трассы capture или всех процессов. PID/счётчики в точках
не заменяют полную историю ручных действий. Для SB additionally process start identity
совпал — это сильнее одного числового PID, но не наблюдение всех сетевых операций.

WAN RX/TX выросли на24971138/40816905байт; LAN на4780/3410байт. Это счётчики интерфейсов,
не атрибуция клиентскому потоку. Малый LAN-трафик не доказывает неисправность LAN.
Владелец не сообщал об использовании устройств в этом интервале; пути клиентов и
Tailscale отдельно не измерялись. Существующая работа шлюза принята как baseline,
отсутствие специальных тестов не является заявлением о её неработоспособности.

Пустой journal-ответ не доказывает глобальную полноту логирования или отсутствие
ошибок в других журналах/интервалах. Нулевые capabilities и ожидаемый DAC ещё не равны
фактическим negative access attempts. Счёт правил guard не является счётом утечек.

## Следующий атомарный пакет wave3m

[ТЗ](TEST-PLAN-REAL-MACHINE-0.2.0-wave3m.md), [шаблон](TEST-REPORT-REAL-MACHINE-0.2.0-wave3m-TEMPLATE.md).
Отдельные capless/NoNewPrivs дочерние процессы воспроизводят UID/GID/Groups реальных ядер.
Внутри child идентичность проверяется до операции. Положительный контроль — open собственного
конфига SB; ожидаемые отказы — SB к конфигу/API Xray, созданию пустого собственного файла
в состоянии XGW, read-only nft; Xray к конфигу SB. Содержимое конфигов не читается и не
печатается, UNIX API не получает RPC. Новые helpers не устанавливают продукт.

Тест создания файла ожидает DENIED. Если неожиданно разрешён, создаётся только один
уникальный пустой файл без overwrite, worker удаляет собственный inode; ALLOWED остаётся
FAIL границы. Cleanup failure явно фиксируется, права/каталоги массово не исправляются.
Все изменения сетевых правил/служб запрещены, включая старый ip rule add/del pref49.
Рабочий on сохраняется; off-guardian не применяется. На первом несовпадении остальные
попытки NOT_RUN. Смена/ошибка контекста не скрывается за PASS дочерней попытки.

Это проверка UID/DAC/netlink boundaries вне полного постоянного service sandbox,
а не всех seccomp/mount/AppArmor ограничений. Непроверенное не приписывается результату.
D1-on reinstall/scopedfaults/E4 actual packets/специальные LAN UDP/IPv6/DNS/allTailscale
пути ещё не приняты; всяwave3 остаётся открытой, wave4/DAE не активируются.

Реальная wave3m **NOT_RUN**. Ожидается docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3m-ДАТА.md.
