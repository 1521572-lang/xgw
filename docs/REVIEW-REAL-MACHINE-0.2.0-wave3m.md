# Разбор wave3m: шесть проверок доступа приняты

[Фактический отчёт Flash](https://github.com/1521572-lang/xgw/blob/09abf5c46101cf69783dce447d759a416bf8403f/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3m-2026-11-02.md), commit09abf5c46101cf69783dce447d759a416bf8403f,
FF merged. TestedHEAD ea199673039da61e87123bad1cdd5db7d1b36d43,
treea1cae09d551ba0bb85c1bccfd429749158c88d3b. Product pin351fb54e074f4a7b497a8a4244fc74c6088788d7;
runtime diffempty, installed4equal, оба frozen helper SHA совпали. Runtime не устанавливался.

## Принимаемые результаты

| Case | Результат | Решение |
|---|---|---|
| SB_OWN_CONFIG | ALLOWED/open+close без чтения содержимого | Положительный контроль доступа к своему конфигу |
| SB_XRAY_CONFIG | DENIED_PERMISSION | Отказ файлового доступа подтверждён |
| SB_XRAY_API | DENIED_PERMISSION при существующем UNIX socket | Отказ connect подтверждён; RPC не отправлялся |
| SB_STATE_CREATE | DENIED_PERMISSION | Пустой тестовый файл не создан, cleanup не нужен |
| SB_NFT_READ | DENIED_PERMISSION, root-контроль успешен | Отказ прав при исправной read-only команде |
| XRAY_SB_CONFIG | DENIED_PERMISSION | Обратная файловая граница подтверждена |

[Все шесть попыток и проверка identity](https://github.com/1521572-lang/xgw/blob/09abf5c46101cf69783dce447d759a416bf8403f/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3m-2026-11-02.md#L24-L36) согласованы с ТЗ.
Внутри child совпали UID/GID/дополнительные группы, CapInh/Prm/Eff/Bnd/Amb0 и NoNewPrivs1.
У Xray дополнительно проверено отсутствие эффективных DAC-bypass capabilities.
Это устраняет ложный PASS из ENOENT/неисправного setpriv/недоступной команды.

[До/после](https://github.com/1521572-lang/xgw/blob/09abf5c46101cf69783dce447d759a416bf8403f/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3m-2026-11-02.md#L38-L49): рабочий HEALTHY/on, guardpostrouting10/forward/drop5/reject0,
6службactive/6PID прежние, settings3unchanged/sameboot, процессные свойства/DAC сохранены.
Пробы не меняли VPN/адаптеры/правила/конфиги; связь жива. Неожиданного allow не было,
артефакта state-probe нет. Отклонений и повторов нет. Новый дефект продукта не выявлен;
product patch, рестарт и повтор M не требуются.

## Границы вывода

Подтверждены перечисленные UID/DAC/netlink границы вне полного service sandbox.
Свой конфиг доступен и конкретные чужие конфиги недоступны — это не утверждение,
что процесс может читать только один файл во всей системе. Не проверялись все seccomp/
AppArmor/mount namespace ограничения. Live ip rule add/del намеренно NOT_RUN, а не
«выполнено с отказом». Нулевая capability-маска измерена отдельно.

Scoped faults, D1-on reinstall, E4actualWAN packets, специальные LAN UDP/IPv6/DNS leak/
все Tailscale-пути остаются открытыми. [Scope отчёта](https://github.com/1521572-lang/xgw/blob/09abf5c46101cf69783dce447d759a416bf8403f/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3m-2026-11-02.md#L51-L63).
Это не означает неисправность принятой рабочей схемы XGW → роутер → устройства.
Полнаяwave3 ещё не принята, wave4/DAE не включаются. Рабочий on сохраняется.

## Следующий пакет: совместимость постоянного capless sing-box

[ТЗ wave3n](TEST-PLAN-REAL-MACHINE-0.2.0-wave3n.md),
[шаблон](TEST-REPORT-REAL-MACHINE-0.2.0-wave3n-TEMPLATE.md).
Максимум2существующих базовых SOCKS-входа постоянного SB, только настроенные HTTPS-цели,
ограниченные GET без смены main pin, без API мутаций/правил/перезапуска ядер. Владение LISTEN
портом проверяется по socket inode/fd конкретного процесса. Условия TLS/body/контекста
проверяются раздельно; пароли/URL/curlJSON не публикуются. Pin читается только SELECT mode=ro,
Store не используется. Новый helpers-only пакет, runtime продукта прежний.

Это scoped проверка полезной передачи HTTPS постоянным worker, а не все профили,
полная Xray/TPROXY цепочка, LAN/UDP/IPv6 или E4. Нет прямого fallback при отказе proxy.
Не создавать новые узлы/подписки/ключи и не отключать VPN ради результата.
Реальная wave3n **NOT_RUN**. Ожидаемый артефакт:
docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3n-ДАТА.md.
