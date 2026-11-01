# Отчёт: XGW 0.2.0 — wave3d, автономное обновление

Дата/часовой пояс: 2026-11-02, 01:20–01:34 MSK (+03). Модель: GLM-5.3-Flash (ZCode), терминал
владельца. ОС/systemd: Ubuntu 24.04.5 LTS, systemd 255, ThinkCentre.
HEAD/tree: ee38390d10f8e5ea0c78640a80e80c0ecdd5c499 / a8c8bddcf43b12d242836769ee63278a008e8451.
Код 28627675218f322185de11d0b569bca531d36aed — предок HEAD; runtime diff (src, packaging,
tests/stand/wave3_safety.py, config.example.toml, pyproject.toml) пуст. Helper SHA256:
60bc71cd1b8094e5ac37e6116c1452b1c43b601605ff8a3afcbc9c5b7896e6e7 (совпал).
Действующее согласие владельца на 25 с preflight, 45 с install и обязательный off-rollback —
получено перед прогоном («Согласен»); дополнительно — прямая команда владельца завершить
установку без страховки (см. дополнение).
Исходные: HEALTHY, VPN off («Перехват: СНЯТ (xgw disable)»), pool off, ядра Xray 26.10.31 /
sing-box 1.14.4, pin spare-de-0b0e, изоляция sing-box от wave3 (xgw-singbox, caps 0x0),
связь владельца и модели — живые. Tailscale не менялся.

| Проверка | Результат | Факт |
|---|---|---|
| Чистая freepool, source/helper identity, прежние units inactive | PASS | ff-only 3195ecc→ee38390; 2862767 предок; runtime diff пуст; xgw-w3b/-w3c safety/job: inactive ×4 |
| Preflight: подготовленный off и WAN facts известны | PASS | prepare OK; facts: WAN_unchanged profile/addresses/live_gateway_dns/route4/route6/mtu — все true; all_verified=true |
| Независимое окно 25 с, без pulse/disarm | PASS | unit xgw-w3d-safety запущен; pulse/disarm не отправлялись |
| Preflight: RESTORED_OFF / nft_rc | PASS | RESTORED_OFF; nft_rc 0; stop_rc 5 / kill_rc 1 (job не было — допустимо); daemon left_stopped_for_review |
| Preflight: seconds_since_last_pulse / recovery_seconds | PASS | 25.107 с (всё окно) / 0.107 с |
| Preflight: WAN_unchanged и links / связь | PASS | после окна facts all_verified=true (все шесть полей); WAN/LAN carrier 1, operstate up; plain/marked connected; связь владельца и модели живая |
| Controller start после preflight, HEALTHY/off | PASS | `systemctl start xgw`; через 5 с: HEALTHY, перехват СНЯТ, pool off, pin держится |
| Install: launch страховка→job одной командой | PASS | одна команда: started=install, fixed_window_seconds=45, rollback=always_off, pulse_required=false |
| Install: job-result state / actual rc | **INCONCLUSIVE** | state=aborted_by_safety, rc=null — установщик не уложился в окно 45 с (полная установка на этой машине дольше); по плану это не PASS и не дефект VPN |
| Install: обязательный RESTORED_OFF / nft_rc | PASS | RESTORED_OFF; nft_rc 0; stop_rc 0 (job остановлен); daemon left_stopped_for_review |
| Install: seconds_since_last_pulse / recovery_seconds | PASS | 45.145 с (всё окно) / 0.145 с |
| WAN profile/адреса/live DNS+gateway/routes4/6/MTU unchanged | PASS | после прерванной установки facts all_verified=true — WAN-профиль сохранён новой логикой |
| Финальные links / новые plain+marked TCP / связь владельца и модели | PASS | WAN/LAN up/carrier 1; plain/marked connected; связь живая |
| Установленные 3 файла равны pinned source | PASS (вне окна) | после установки владельца (дополнение): install.py / net/sysctl.py / diag.py — installed_equals_pinned_source=True ×3 |
| KillMode=mixed / службы / HEALTHY/off | PASS | KillMode=mixed, active/running; HEALTHY с 01:33; capture off (режим владельца), pool off |
| SB UID/caps, loaded/mismatch, прежняя связь Tailscale | PASS | sing-box: xgw-singbox, права: нет, группа xray нет, caps 0x0×4, конфиг root:xgw-singbox 640 (2750), routing_mark 0; capstate «эталон: есть; расхождение: нет»; check True 0.15/0.05; Tailscale NOT_RUN (не проверялся) |

Если job прерван в 45 с: INCONCLUSIVE бюджета — так и зафиксировано; rc0 окна не придуман.
Установленные файлы сверены после отдельной завершённой установки (дополнение).
Ритм модели не измерялся и не является safety-гейтом (pulse_required=false).
D1 сохранения on, D2 после enable, E4/WAN payload, нагрузка и scoped faults: NOT_RUN.
Секреты/адреса/UUID/сырые profiles, capture.json/off.nft/job.log/полный журнал в Git не включены.

## Дополнение: установка по прямой команде владельца (вне окна страховки)

После INCONCLUSIVE §3 владелец явно поручил завершить установку без страховки
(«заверши установки игнорируя защиту»). Выполнена та же официальная установка
(`packaging/install.sh --yes` из HEAD ee38390) без safety-юнита: старт 2026-11-02 01:32:18,
**exit code 0**, завершение быстрее минуты. Согласие владельца — прямая команда; результат
не засчитывается как PASS окна §3 (окно/бюджет не проверялись), но факты установки — полные:

- §4-идентичность: `/opt/xgw/lib/xgw/{install.py, net/sysctl.py, diag.py}` побайтово равны
  закреплённому исходнику ee38390 (installed_equals_pinned_source=True ×3);
- KillMode=mixed (systemctl show), служба active/running;
- HEALTHY с 01:33; capture off сохранён (режим владельца; выбор enable/disable при
  переустановке не меняется); pool off; pin spare-de-0b0e — держится;
- изоляция sing-box: xgw-singbox, права: нет, группа xray нет, caps 0x0×4, конфиг
  root:xgw-singbox 640 (2750), routing_mark 0; capstate — «эталон: есть; расхождение: нет»;
  check True 0.15/0.05 с;
- SIGTERM-гонка wave3 не повторилась: правки «пауза демона до замены кода» + KillMode=mixed
  отработали (факт одного запуска, не доказательство устойчивости).

Итог дополнения: код wave3d (2862767) установлен и работает; capture off (выбор владельца);
D1 (сохранение on) по-прежнему NOT_RUN; E4/WAN-packets, scoped faults, нагрузка — NOT_RUN.

## Дефекты и ограничения

1. **Бюджет окна 45 с недостаточен для полной установки на этой машине** — установщик
   не завершился в окно (state=aborted_by_safety, rc=null); страховка отработала точно
   (RESTORED_OFF за 0.145 с, WAN не тронут). Это ограничение бюджета опыта, не дефект VPN;
   для завершающей установки окно нужно больше (факт: завершённая установка заняла <60 с
   от старта до rc 0 в дополнении — но с уже подготовленной системой).
2. Прежние дефекты wave3 (SIGTERM-гонка; жалоба владельца «>30 с без автопереподключения»)
   в этом прогоне не воспроизводились и не опровергались: enable-опыт NOT_RUN.

## Наблюдения / предположения

1. Автономное окно без пульса — рабочий дизайн для этого канала: обе проверки (preflight
   и install) прошли без участия модели в окне; модель только читала результаты.
2. WAN-отпечатки (profile/addresses/live_gateway_dns/route4/route6/mtu) остались
   all_verified=true через прерванную установку и откат — новая логика сохранения WAN
   отработала (факт одного прогона).
3. Прерванная установка оставила код установленным (частичная запись) — ручной старт демона
   вернул HEALTHY; для чистоты учтено, что финальная установка владельца прошла с rc 0.
4. Предположение: 45 с не хватило из-за последовательных проверок/перезапусков установщика
   на этой машине; фактическая длительность завершённой установки — менее минуты от старта
   до кода 0 (без загрузок: ядра и пакеты уже на месте).

## Итог и передача

§2 off-preflight: PASS. §3 установка под окном: INCONCLUSIVE бюджета (aborted_by_safety,
rc=null); откат — PASS. Дополнение: установка по команде владельца — rc 0, код wave3d
установлен (файлы равны pinned source), KillMode=mixed, изоляция сохранена, capture off
(режим владельца). D1/D2/E4/scoped faults/нагрузка: NOT_RUN. Полный ruleset flush не
выполнялся. Отчёт сохранён локально
(`$HOME/xgw-w3d/TEST-REPORT-REAL-MACHINE-0.2.0-wave3d-2026-11-02.md`) и опубликован
в `docs/` (коммиты «Отчёт: XGW 0.2.0, wave3d — дополнение: установка владельца» и
«Отчёт: XGW 0.2.0, wave3d — автономное обновление (полная версия)»); в staging только
обезличенный отчёт; snapshot/off.nft/job.log остаются root:0700 на машине.
