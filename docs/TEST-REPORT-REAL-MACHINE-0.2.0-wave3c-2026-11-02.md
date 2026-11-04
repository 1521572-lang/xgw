# Отчёт: XGW 0.2.0 — wave3c, ритм Flash

Дата/время/часовой пояс: 2026-11-02, 00:20–00:26 MSK (+03). Модель: GLM-5.3-Flash (ZCode,
терминал владельца). ОС/systemd: Ubuntu 24.04.5 LTS, systemd 255, ThinkCentre.
HEAD/tree: 0f9b70d37c7f03eac65fc51429f83771dc1e1e78 / 9523d03d87f834a3358ad4162a9d1cb42fc9b182.
Helper cc126060a478ed30550ad6bac4f82d37a02b9668, фактическая SHA256 замороженного safety.py:
013be016c64162104dca7d0368736652902e79c5f4bead2a373ddc14c4b25041 (совпала).
Согласие владельца на автономный возврат к off и краткую остановку контроллера — подтверждено
владельцем перед прогоном («Подтверждаю»). Исходные: VPN off («Перехват: СНЯТ (xgw disable)»),
pool off, ядра Xray 26.10.31 / sing-box 1.14.4, ручной выбор spare-de-0b0e — держится, связь
владельца и модели — живые.

| Проверка | Результат | Факт |
|---|---|---|
| Чистая freepool / identity | PASS | ff-only cc0b021→0f9b70d; cc12606 — предок; runtime diff (src, packaging, tests/stand/wave3_safety.py, config.example.toml, pyproject.toml) пуст |
| Старые safety/job inactive | PASS | xgw-w3b-safety.service: inactive; xgw-w3b-job.service: inactive |
| Dry pulse1 / gap seconds | PASS | LEASE_OK; previous_gap_seconds 12.569 (lease 25.0) |
| Dry pulse2 / gap seconds | PASS | LEASE_OK; previous_gap_seconds 17.588 (lease 25.0) |
| Dry pulse3 / gap seconds | **INCONCLUSIVE** | юнит к третьему вызову завершился — lease истёк (разрыв >25 с); третье значение не получено |
| Максимальный gap≤20с | **FAIL** | наблюдённые 12.569 и 17.588 с в пределах 20 с, но следующий разрыв превысил окно 25 с → DRY_EXPIRED |
| Dry disarm | NOT_RUN | юнит уже завершился (DRY_EXPIRED); disarm не требовался и не проводился |
| Off snapshot / автономное истечение 25 с | NOT_RUN | §3 не выполнялся (план: INCONCLUSIVE ритма → §3 NOT_RUN) |
| RESTORED_OFF / nft_rc | NOT_RUN | см. выше |
| seconds_since_last_pulse (ожидание включено) | NOT_RUN | см. выше |
| recovery_seconds (ожидание исключено) | NOT_RUN | см. выше |
| WAN/LAN carrier/operstate в точках замера | NOT_RUN | замеры не выполнялись (dry-режим правил не касается); в конце: xgw active, HEALTHY, перехват СНЯТ — состояние не менялось |
| Связь владельца/модели, plain/marked TCP | PASS | связь модели жива во все три вызова (два LEASE_OK получены); владелец на связи; plain/marked не измерялись (вне dry) |
| Финальные режим/службы/связь | PASS | HEALTHY с 02.11 00:16; перехват СНЯТ (off — как до прогона); pool off; xgw-w3c-safety.service inactive (DRY_EXPIRED); правил не касались |
| Прежняя работа Tailscale при актуальности | NOT_RUN | не проверялось (вне области прогона) |

Install/enable/on-reinstall, D1/D2, scoped faults, E4, UDP/IPv6/LAN payload/нагрузка: NOT_RUN
по области ТЗ. **Ритм слишком медленный — INCONCLUSIVE оператора; новых сетевых опытов нет.**

Фактический ритм канала оператора по трём попыткам: 12.569 с → 17.588 с → разрыв >25 с
(DRY_EXPIRED): нестабильный, с выбросом за окно. Прежние данные wave3b согласуются: две
установки прерваны при окне 15 с. Вывод для разработчика (предположение, помечено): канал
«модель → инструмент → терминал» даёт неравномерные интервалы 10–30+ с; окно 25 с может
истекать на «долгих» вызовах; для scoped fault-опытов нужен либо больший lease с
независимой валидацией, либо механизм подтверждения вне цикла модели.

Никаких сырых конфигов/адресов/profiles/snapshot/job.log в Git не включено. Прежний отчёт
(wave3b) не переписывался. Система в исходном состоянии: правила и политики не менялись
(dry-режим), xgw active, capture off, pool off.
