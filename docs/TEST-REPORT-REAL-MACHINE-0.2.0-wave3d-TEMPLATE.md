# Отчёт: XGW 0.2.0 — wave3d, автономное обновление

Шаблон, фактические результаты NOT_RUN. Дата/часовой пояс/модель/ОС/systemd: NOT_RUN.
HEAD/tree: NOT_RUN. Код28627675218f322185de11d0b569bca531d36aed; helperSHA: NOT_RUN.
Действующее согласие на25с preflight,45с install и обязательный off-rollback: NOT_RUN.
Исходные HEALTHY/off/pool off/ядра/pin/Tailscale/связь: NOT_RUN.

| Проверка | Результат | Факт |
|---|---|---|
| Чистая freepool, source/helper identity, прежние units inactive | NOT_RUN | — |
| Preflight: подготовленный off и WAN facts известны | NOT_RUN | — |
| Независимое окно25с, без pulse/disarm | NOT_RUN | — |
| Preflight: RESTORED_OFF / nft_rc | NOT_RUN | — |
| Preflight: seconds_since_last_pulse / recovery_seconds | NOT_RUN | — |
| Preflight: WAN_unchanged и links / связь | NOT_RUN | — |
| Controller start после preflight, HEALTHY/off | NOT_RUN | — |
| Install: launch страховка→job одной командой | NOT_RUN | — |
| Install: job-result state / actual rc | NOT_RUN | — |
| Install: обязательный RESTORED_OFF / nft_rc | NOT_RUN | — |
| Install: seconds_since_last_pulse / recovery_seconds | NOT_RUN | — |
| WAN profile/адреса/live DNS+gateway/routes4/6/MTU unchanged | NOT_RUN | — |
| Финальные links / новые plain+marked TCP / связь владельца и модели | NOT_RUN | — |
| Установленные3файла равны pinned source | NOT_RUN | — |
| KillMode=mixed / службы / HEALTHY/off | NOT_RUN | — |
| SB UID/caps, loaded/mismatch, прежняя связь Tailscale | NOT_RUN | — |

Если job прерван в45с: INCONCLUSIVE бюджета, rc0 не придумывать. Если WAN fact=null:
NOT_VERIFIED, совпадением не считать. Ритм модели не измеряется и не является safety-гейтом.
Сетевые состояния нельзя выводить только из socket.connect или наличия новых файлов.
D1 сохранения on, D2 после enable, E4/WAN payload, нагрузка и scoped faults: NOT_RUN.
Секреты/адреса/UUID/сырые profiles, capture.json/off.nft/job.log/полный журнал в Git не включать.
