# Разбор wave3n: один положительный путь, один неразобранный отказ

[Фактический отчёт Flash](https://github.com/1521572-lang/xgw/blob/e4f6f2d2f8ae8cf6148a624f5231c4107bd7f225/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3n-2026-11-02.md), commite4f6f2d2f8ae8cf6148a624f5231c4107bd7f225,
FF merged. TestedHEAD7d2344c618237627276555c2caee312aea4c1ea2,
tree4378599f67e0ca31addcaee6fc79c9f23923ac45. Product pin351fb54e074f4a7b497a8a4244fc74c6088788d7,
runtime diffempty, installed4equal, frozen2SHA совпали. Продукт не устанавливался.

## Решение по матрице

| Case | Факт | Принимаемый scope |
|---|---|---|
| SB-1 vless/d, target1 | curl97/HTTP0/bytes0/1.599с, socketownertrue до/после | Отрицательный запрос, причина неизвестна |
| SB-1 vless/d, target2 | curl97/HTTP0/bytes0/0.709с, socketownertrue до/после | Второй отрицательный запрос, не заменяет первый |
| SB-2 vless/d, target1 | rc0/HTTP206/32769байт/0.372с/TLSverify0/identity, socketownertrue | Scoped HTTPS compatibility этого постоянного входа подтверждена |

[Таблица и сохранённый контекст](https://github.com/1521572-lang/xgw/blob/e4f6f2d2f8ae8cf6148a624f5231c4107bd7f225/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3n-2026-11-02.md#L21-L51). Listener inode принадлежал конкретному
PID sing-box, в том же netns; тело получил именно этот постоянный worker. Это полезное
доказательство работоспособности capless SB для одного входа. Прямого fallback не было.
Один и тот же процесс/6PID/on/settings3/SBconfig/pinrecord/boot сохранены, связь жива.
Curl8.5.0 пригоден, routing_mark_key_count0. Дополнительных попыток/действий владельца нет.

**Общий wave3n PASS не достигнут:** markerBRIDGE_PROBES_RECORDED/exit3, body_ok1из2.
Принять положительный SB-2, сохранить отрицательный SB-1. Не повторять N в новых каталогах,
не брать следующий узел ради зелёного отчёта и не менять main pin.

## Коррекция причинной интерпретации

По [документации libcurl](https://curl.se/libcurl/c/libcurl-errors.html) код97 означает
ошибку proxy handshake; сам код не определяет, что именно отказало. При HTTP0/bytes0
нулевой tls_verify_result не доказывает успешный TLS к HTTPS-цели: итоговый критерий
запроса не выполнен. Не записывать SB-1 как TLS PASS.

Успех SB-2 на том же процессе исключает глобальную неспособность worker передать HTTPS.
Он **не исключает** специфический для SB-1 дефект конфигурации, прав, маршрута, совместимости
или upstream. Поэтому фразу отчёта «не дефект изоляции (SB-2 … прошёл)» принимаем только
в первом, узком смысле. Категорически исключать изоляцию для всех endpoint-путей нельзя.
[Итоговая формулировка исходного отчёта](https://github.com/1521572-lang/xgw/blob/e4f6f2d2f8ae8cf6148a624f5231c4107bd7f225/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3n-2026-11-02.md#L54-L64).

Сборщик выбрал первые2из71 базовых входов по fingerprint, без health-filter. Он мог взять
ранее плохой сервер. Это ограничение выборки, а не доказанная неисправность продукта.
Продуктовый patch по одному rc97 пока не обоснован. И «сервер мёртв», и «это ТСПУ», и
«виноват sandbox» остаются неподтверждёнными объяснениями.

## Пробелы свидетельств и следующий шаг

N не сохранял детальный curlstderr, выбранные fingerprints и исходный configSHA/PID
как отдельный privateplan. Его нельзя получить задним числом повтором и выдать за старое
измерение. Последний persisted scan может быть позднее N; статус сейчас не прошлый факт.

[ТЗ wave3o](TEST-PLAN-REAL-MACHINE-0.2.0-wave3o.md),
[шаблон](TEST-REPORT-REAL-MACHINE-0.2.0-wave3o-TEMPLATE.md): только сохранённые данные,
без новых GET/CONNECT/DNS/rescan. Читаются rootNsummary, journal реального окна±2с,
безопасные текущие признаки SB-1/SB-2 и latest scan relation/age. Сопоставление случаев
разрешается лишь с временным основанием конфигурации; отсутствие старого digest не скрывается.
Без подтверждённого соответствия нет per-case attribution, только общие counts/UNKNOWN.
Rawстроки/адреса/ключи/теги не публикуются, новый privateplan остаётся root600 на машине.

O — диагностический сбор, не проверка исправления. Ни VPN/ядра/правила, ни WAN/LAN/
Tailscale/main pin не меняются. Старый guardian/off-rollback и реконфигурация по догадке
запрещены. По результатам O выбирается одна следующая проверяемая гипотеза.

Реальная wave3o **NOT_RUN**. Ждём docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3o-ДАТА.md.
N остаётся частичным; D1-on/E4/faults/специальные LANUDP/IPv6/DNS/allTS и всяwave3
ещё не приняты. Рабочая эксплуатация сохраняется; wave4/DAE не активируются.
