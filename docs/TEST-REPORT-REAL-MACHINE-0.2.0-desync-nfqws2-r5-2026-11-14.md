# TEST-REPORT-REAL-MACHINE-0.2.0-desync-nfqws2-r5-2026-11-14

Дата: 2026-11-14; прогон 11:45–12:40 UTC. CODE c7500f6f40bdfbc9d16b1b23056063813a71a839
(установлен и оставлен), BASE d395628ff1d6b5c55fa14435eacce325c93ca748 (модуль на машине до
замены — SHA fe562809… сверён), план 20a8151, ветка gui-light. Исполнитель GLM-5.3-Flash;
Ubuntu 26.04 amd64; Python 3.12.3; Xray 26.10.21; nfqws2 v1.0.7. Root — один systemd-run
--system юнит с FIFO-очередью, остановлен после восстановления. Согласия r2–r4 действовали
(замена модуля, перезапуск демона, профили/offload); временное изменение mangleid покрыто
областью «offload на WAN», исходное значение возвращено из снимка до прогона.

## Итог: **PASS** — фикс восстановления mangleid подтверждён на живом цикле

TESTS 25 PASS; APPLICABILITY PASS (TSO on изменяем, mangleid присутствует); CYCLE PASS;
RESTORE PASS. Первый FAIL отсутствует.

## Состояния флага

- До прогона (ethtool-before): tso on, **mangleid on** (наследие r4), gso/gro on,
  tx-checksum-ip-generic off [fixed].
- Состояние для теста (после штатного `ethtool -K tx-tcp-mangleid-segmentation off` при
  выключенном движке): tso **on** (не сбился), mangleid **off** — TSO остался включённым при
  изменении под-флага.

## §2–§3: контроль и цикл — PASS

- TESTS: `tests/test_nfqws2.py` — **25 passed** (1,8 с).
- Установка: заменён только nfqws2.py (root:root 0644, SHA bf278ea9… = CODE), перезапуск только
  xgw.service — HEALTHY, HTTPS 200, PID Xray 262461.
- §3.2 disorder-badseq: движок включён (acct=1, engine_offload=true) — worker **active**, очередь
  200 занята, фактически **tso off, gso off, gro off** (mangleid off), PID Xray 262461, HTTPS 200;
  два шага watchdog — PID стабилен; всего стартов с момента включения — **1** (штатный), fallback
  и повторных стартов нет.
- §3.3 возврат к seqovl: worker перезапущен, полный `ethtool -k` — **все пять значений совпали со
  состоянием для теста: tso on, gso on, gro on, mangleid off** (сохранённое значение восстановлено
  вместо дефолта ядра on — суть фикса подтверждена на живом шлюзе), tx-checksum-ip-generic
  off [fixed]; PID Xray сохранён, HTTPS 200.
- §3.4 disorder → engine=off: worker остановлен, очередь пуста, те же пять значений после off,
  `xgw enable` — nfq_output отсутствует, HTTPS 200, HEALTHY.

## §4: возврат машины — PASS

mangleid возвращён в значение **снимка до прогона** (on), конфиг **байтово идентичен**
исходному (ключ engine удалён → off по дефолту), panel.json идентичен, acct=0, полный
`ethtool -k` **байтово идентичен снимку до прогона**, diag «OK — 32, WARN — 1, FAIL — 0»
(WARN — линия дня: TLS-обрывы проб-хостов, стиль прежних отчётов), HEALTHY, capture on,
PID Xray 262461, worker/очереди нет, HTTPS 200. **Оставшийся код: CODE c7500f6** — только
nfqws2.py обновлён, приёмка успешна, модуль оставлен; cli.py/daemon.py не трогались (BASE).

Примечание: строки «up at t=…» отдельных фаз частично обрезаны окном чтения журнала
исполнителя; контроль соответствия выполнен по файлам ethtool/cmdline и финальным сверкам,
не по усечённым строкам. Видео напрямую — NOT_RUN (перенесено, маршруты не добавляются);
прогон не является доказательством YouTube без VPN или обхода ТСПУ.

Отчёт без снимков, IP/доменов, имён серверов/устройств и URL; приватные журналы и ethtool —
в каталоге прогона (mode 0700), worktree CODE сохранён до разбора отчёта.
