# ThinkCentre. zapret2 в поставке XGW — 2026-11-10

- Дата; CODE 044409b (не установлен); сумма помощника OK (baf316b9…); база bfb8218 — установленная
  машина на нём, HEALTHY.
- До: diag (OK/WARN/FAIL): **33/0/0**; режим пула observe; zapret2 off; nfqws2 v1.0.7 во внешнем
  /opt/zapret2 на месте.
- Самопроверка исходников: worktree CODE и BASE собраны, сумма помощника верна; `before` — **`STOP
  bundle_check_failed`** (helper_rc=2), воспроизведён повторно.
- Причина STOP (диагностика по шагам snapshot, приватно, конфиги не печатались): helper требует
  работающих **обоих ядер** (`xgw-xray` и `xgw-singbox`, PID > 0); `xgw-singbox.service` — inactive,
  MainPID=0 → `core_not_running`. Состояние машины при этом легитимно: в применённом конфиге Xray
  есть протокол hysteria (свежий Xray покрывает hysteria2 сам), мостов sing-box в сборке нет —
  службе нечего запускать; шлюз HEALTHY, diag без FAIL. Требование helper'а «оба ядра работают»
  разошлось с реальностью машины.
- Второй блокер: готовый архив Ubuntu 26.04 amd64 от владельца **не передан** (по ТЗ — NOT_RUN
  artifact; SHA-256 архива в ТЗ: 88ac3262…, сверка не проводилась — сверять нечего).
- Тесты (без изменения шлюза, для данных разработчику): test_zapret2_bundle + test_zapret2 +
  test_config — **77 passed**, новых падений нет.
- Не выполнено (последовательно из-за STOP): check комплекта (нужен архив), согласие и установка
  трёх Python-файлов и комплекта, приёмка на /opt/xgw/zapret2/1.0.7, finish. Машина не менялась.
- Конечное: on/HTTPS OK (health-уровень: state=HEALTHY, capture on); diag — 33/0/0, новых FAIL
  нет; режим пула observe; zapret2 off.
- Передать разработчику: helper zapret2_bundle требует оба ядра активными — на конфигурации, где
  Xray покрывает hysteria2 сам, sing-box законно неактивен и приёмка не стартует; нужно ослабить
  требование (например, «xgw-xray работает; sing-box — если есть мосты») или отдельный допуск.
- Итог: **NOT_RUN** (шаг 1: расхождение baseline — sing-box inactive, легитимно; плюс NOT_RUN
  artifact — архива владельца нет). Первый непройденный шаг — 1. На машине: код **bfb8218** (не
  менялся), состояние HEALTHY, VPN включён, zapret2 off, nfqws2 v1.0.7 в /opt/zapret2.
