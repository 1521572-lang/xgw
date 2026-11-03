# Отчёт: XGW wave3v — закрытие локальных пробелов evidence

Дата/время MSK: 2026-11-03, 08:51:43–08:55+03 (сбор 1.747 с). Модель GLM-5.3-Flash
(ZCode), терминал владельца; Ubuntu 24.04.5 LTS, systemd 255, nftables v1.0.9 (Old Doc
Yak #3) (S1.3, записано буквально; не обновлялся). Ядра: Xray 26.10.31 / sing-box 1.14.4.
Tested HEAD e8151bce2006a434f2c217ae838467bd4f4a51c6 / tree
4331a5b76b78e3b4f19e13ec9969d2096e8b4934. Product pin
351fb54e074f4a7b497a8a4244fc74c6088788d7. Runtime diff (src, packaging,
tests/stand/wave3_safety.py, tests/stand/wave3_enable_probe.py, config.example.toml,
pyproject.toml) пуст; новые файлы — только тестовый пакет (wave3_evidence_closure.py +
unit-тест); продукт не устанавливался и не менялся. Installed4: True ×4
(INSTALLED_SOURCE_OK); полное .py-дерево: equal=True, 110=110 (INSTALLED_PARSER_TREE_OK).
8 frozen SHA (EVIDENCE_CLOSURE_FROZEN; /run/xgw-w3v 0700, файлы root600):
wave3_evidence_closure.py be906a5278ce677f7f053ee0f272b2580b8b2f8f2e2287aa2bebd7307f3852f8
(единственный CLI start/status/show; _worker вручную не вызывался); wave3_coverage_batch.py
f3c45a1f…; wave3_extended_batch.py 9e467188…; wave3_reality_contract.py 3fbc8fdd…;
wave3_single_bridge.py 66128dda…; wave3_bridge_diagnostic.py e77d441e…;
wave3_bridge_probe.py 2f023032…; wave3_on_observer.py 0db2acf6… — библиотеки.
Executor_NoNewPrivs=0 (S1.2a, EXECUTOR_NNP_OK); sudo rc 0; действий владельца не
требовалось. Начало/конец: HEALTHY с 02.11 19:56; перехват ВКЛЮЧЁН (рабочий on);
pool «выключен»; Tailscale route=vpn; связь владельца и модели живая.
Start rc 0/маркер EVIDENCE_CLOSURE_STARTED; monitor: BATCH_FINISHED (бюджет 120 с не
исчерпан); show rc 0, wrapper.file=**summary.json**; финальный маркер
**EVIDENCE_CLOSURE_RECORDED**; elapsed 1.747 с; network_requests=**0**;
executor_scope=THINKCENTRE_ONLY_CONFIRMED_BY_OWNER.

| Этап | collection | Данные bool/count/fixed enum | Semantic decision | limits |
|---|---|---|---|---|
| V1_U_identity | RECORDED | U_scope_accepted=true; Usource SHA сверен; **current_sb_matches_U=true**; current_xray_matches_U=**false** | SB-байты неизменны с U (08:05→08:52); Xray-байты изменились между U и V; время/автор/причина не следуют; «ночная регенерация» и действие владельца НЕ назначаются; одинаковая дата HEALTHY не доказывает непрерывность работы ночью | Только bools; не исторический R-endpoint |
| V2_contract_gap_classification | RECORDED | 3 источника прочитаны (101 supported: 46/47/8; unsupported 7/21/9; limits не достигнуты); **same_cache_digests_as_U=true**; counts: default_vless=67, equal=66, mismatched=0, ambiguous_contracts=0, **missing_identity=1**; уравнение 67=66+0+0+1 сходится; ambiguous_field_counts все 0; mismatch_field_counts все 0; missing_identity_reason=UNDETERMINED_NOT_AUTOMATIC_RUNTIME_BUG | Оставшийся gap классифицирован: **missing_identity** — ровно один default-VLESS outbound не имеет точной тройки server/port/uuid среди 101 supported record; это НЕ ambiguity и НЕ mismatch. Так как cache и SB совпадают с U — классифицирован именно прежний единственный gap U (стабильное состояние); причина (формат записи/неполнота кэша/иная baseline) не установлена и по коду не объявляется runtime-багом | Current supported cache only; не все протоколы/не health; native SB — общий extractor; absent fp=chrome-конвенция |
| V3_generation_object_categories | RECORDED | last_good available, bytes≠current; **shared_objects_changed=44; current_type_counts: VLESS=44, GROUP=0, SERVICE=0, OTHER=0; field_groups (overlap): tls=44, identity=0, transport=0, multiplex=0, detour=0, group_members=0, other_fields=0, type=0**; added=0/removed=0; теги 0/0; dns/log/route/experimental не менялись; pending ABSENT; writer NOT_ATTRIBUTED; matches_T_digest=null (в V не определялся) | Дрейф затронул **ровно TLS-слой полей всех 44 VLESS-объектов**; identity (server/port/uuid/password) НЕ менялся; группы/службы не менялись — смена группы исключена как объяснение дрейфа; суммой overlap-категорий «число серверов» не выдаётся; writer/время не атрибутированы | Не «44 сервера обновились» в смысле события; peer может быть другим поколением; файлы не применялись |
| V4_bounded_writer_journal | RECORDED | **query_ok=true, stop_reason=EOF, child_rc=0**; window=7200с, byte_limit=1048576, raw_bytes_read=364930, rows_analyzed=708, row_limit_hit=false, incomplete_last_line=false, parse_errors=0; literals: **reloaded=1, systemd_reload_word=2**, started=0, deferred=0, rejected=0, rollback=0, unchanged=0 | В 2-часовом окне двух служб — ровно одна reload-класс фраза и два слова systemd-reload; слов rollback/deferred/rejected/unchanged нет; это ограниченное word-counts evidence, НЕ proof writer'а/причины/истории T/R; в отличие от U8 (TimeoutExpired) выборка завершена полностью в пределах окна | Окно только 2ч/две службы; row_limit_hit=false не доказывает отсутствие событий вне выборки; фразы могут пересекаться/быть цитатой |

Before/after сняты (оба конца): capture true; guard query=ok, postrouting/10/forward/
drop=5/reject=0; службы active ×6; caps 0×5+NoNewPrivs; DAC expected ×4; pool off/
router ap/tailscale vpn/derp true; interfaces distinct, carrier 1/1.
on_context_preserved=true; settings_unchanged=true ×3; SB/Xray config unchanged внутри V;
same_singbox_process/same_boot=true; service_pid_same=true ×6;
pin readable [true,true]/unchanged=true; **cache_inputs_read=3, cache_unchanged=true;
generation_inputs_read=1, local_generation_files_unchanged=true**; all_context_checks_ok=true.
Global stop/after stop — нет; локальных ошибок нет (U8-подобного сбоя не повторилось).
NOT_RUN/UNKNOWN по этапам: нет (все 4 collection=RECORDED с полными данными). Сборщик
RECORDED ≠ semantic PASS — трактовка выше построчная. After не подменялся before;
private baseline U не cat/не публиковалась. Сетевых запросов 0; мутаций 0; helper при
необходимости завершал бы только собственного ребёнка journalctl — завершения не
потребовалось (EOF сам); off-rollback/таймер не запускались.

## Консолидированное решение

1. **Исторический U 66/67 vs V**: same_cache_digests_as_U=true и current_sb_matches_U=true —
   V классифицировал то же стабильное состояние, что и U: прежний единственный gap U
   = **missing_identity** (не ambiguity, не mismatch). Историческая связь с R/N endpoint
   по-прежнему не доказана (короткий ключ ≠ идентичность), U 66/67 остаётся историческим
   фактом, не переписан.
2. **Роли/поля дрейфа**: изменение между поколениями — TLS-слой 44 VLESS-объектов,
   identity/группы/службы не затронуты; writer остаётся неатрибутированным; точные
   пределы journal: окно 2ч/две службы/708 строк/EOF/child_rc=0 — одна reload-класс
   фраза, причин дрейфа она не устанавливает.
3. **Atomic fixspecs**: конкретного mismatch НЕТ (mismatch_field_counts все 0);
   missing_identity имеет причину UNDETERMINED — **runtime fix не обоснован**; продуктовый
   код и сеть в этом прогоне не менялись. Тестовый инструментарий дефектов не выявил.
4. **Единый приоритетный backlog** (будущие отдельные решения разработчика, без микроТЗ-циклов):
   (a) установить происхождение missing_identity-записи — например, helper'ная сверка
   этого outbound с источниками по расширенному соответствию (fingerprint-only/manual
   источники) — read-only, отдельное ТЗ; (b) атрибуция writer'а требует журнала вне 2ч
   окна или кода — вне текущего evidence; (c) reference/R: текущая консистентность
   (reference 12/12 из U, скан OK из U6) не реабилитирует R-отказ — вопрос решается
   одним активным запросом по отдельному ТЗ либо проверкой владельцем свежести подписки/
   сервера вне теста; (d) journal-предел зафиксирован успешной выборкой 2ч — повторов не требуется.
5. **Принятые факты не переписаны**: M 6/6 / J / L 608с / N partial 1/2 / P blocked 0 /
   Q readonly / R negative (curl97, своё время) / S consistency / T / U — сохранены.
   Текущие 66/67 и короткий saved OK не отменяют отрицательного R; доказанной причины
   «ТСПУ/мёртвый сервер» нет.
6. **Только ThinkCentre** (подтверждение владельца); host-пробы не выдаются за клиентские;
   клиентские проверки/D1-on/faults/E4/LAN UDP/IPv6/DNS/performance/all Tailscale —
   открыты (нет независимого возврата on/клиентского пути); full wave3 не закрыта;
   wave4/DAE не начинались. Работающая LAN считается работающей и из NOT_RUN не следует
   её неисправность.

Privacy review до gitadd выполнен: только этот Markdown; private cache/config/logs/
значения полей/дайджесты планов/сырые ошибки/screenshots не включены (в отчёте только
bool/counts/fixed enums/counts категорий без значений). Конечный режим: HEALTHY с
02.11 19:56, перехват ВКЛЮЧЁН, pool прежний; связь живая; действий владельца в прогоне
не было. Публикация: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3v-2026-11-03.md, коммит
«Отчёт: XGW 0.2.0, wave3v — закрытие локальных пробелов evidence», push в freepool
(REPORT_PUBLISHED в финальном сообщении). При блокировке публикации — точная причина
без секретов в финальном сообщении.
