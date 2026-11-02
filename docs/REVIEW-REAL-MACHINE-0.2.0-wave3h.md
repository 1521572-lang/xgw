# Разбор wave3h и следующий ограниченный опыт

Дата 02.11.2026. Исходный
[отчёт bc24353](https://github.com/1521572-lang/xgw/blob/bc24353592c4d56be34280b06a46decf1da6a70d/docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3h-2026-11-02.md)
прочитан полностью. Подмена фактических данных ожидаемыми не обнаружена; неопределённости
сохранены. Ниже уточняются границы интерпретации отчёта.

## Что подтверждено

| Факт | Результат |
|---|---|
| Installed source identity | 4/4, установленный nft.py2739e81c; повторной замены нет |
| Enable | rc0,8.533с |
| Обычный HTTPS приon | HTTP200/32769байт/0.466с, второй положительный запуск подряд |
| Marked HTTPS приon | HTTP200/32769байт/0.292с |
| Независимый возвратoff | total25.161с, restore0.161с, nft0 |
| WAN comparison | 6/6True; carrier1 в точках |
| On context | live enabledtrue, requested/effectiveon, inboundfalse, LISTENloopback, proxy lookup local/lo/tproxy, mismatchfalse |
| Loaded/checkpoint | null/child_deadline8с/phase loaded; event иcheckpoint согласованы |
| Guard layout | deadline_or_error, фактический hook не получен |

Таблица кратких наблюдений не доказывает VPN-egress, полное тело, устойчивость, LAN/UDP/IPv6,
DNS-on/Tailscale-on, actualWAN packets или непрерывную связь модели внутриon. Новый guard
не откатывать по одному отсутствующему диагностическому полю. Полная волна3 не принята.

## Уточнения интерпретации

1. **Guard query не является доказанным таймаутом.**
   [Catch в использованном helper](https://github.com/1521572-lang/xgw/blob/fcaf04f6c60d6d45d974524d6ef7c1b9eb8dd6d9/tests/stand/wave3_enable_probe.py#L286)
   объединял subprocess.TimeoutExpired с OSError, ValueError/KeyError/TypeError при JSON/schema.
   Следовательно, deadline_or_error не позволяет утверждать, что именно nft не завершился
   за0.8с. Это значение UNKNOWN с неустановленной причиной, а не подтверждённый timeout.
2. **Phase loaded ограничивает внешний вызов, не его внутренние стадии.**
   [Capture.loaded](https://github.com/1521572-lang/xgw/blob/fcaf04f6c60d6d45d974524d6ef7c1b9eb8dd6d9/src/xgw/net/capture.py#L858)
   снова вызывает rules/effective_mode; [effective_mode](https://github.com/1521572-lang/xgw/blob/fcaf04f6c60d6d45d974524d6ef7c1b9eb8dd6d9/src/xgw/net/capture.py#L377)
   может повторно вызывать inbound_problem/rules. Ранее завершённый inbound_check не
   исключает повторную сборку/GeoIP как внутреннюю стадию loaded. Также не установлен
   конкретный syscall, nft-процесс или CPU-парсер. Этого нельзя выводить из однойphase.
3. **Восемь секунд — бюджет всего child, не измеренная длительность Capture.loaded.**
   В него входят запуск, импорт/config, предварительный inbound и другие стадии. Из phase
   loaded на момент общего deadline нельзя получить точное время отдельного метода.
   Новый trace использует своё относительное начало после создания Capture; незавершённый
   running record не имеет финальной длительности.

## Решение для следующего прогона

Продуктовый src/packaging/config не меняется относительно573b233. Никакой переустановки/G1,
смены WAN/config/Tailscale, новых scopedfaults или увеличения safety25с. Новый code pin
f78c2f1432ae56cdec8e229b59f33b9ee4723760 относится к test helpers и узким проверкам.

- Guard worker независимо и параллельно loaded8с/HTTPS4с: numeric JSON query3с. Только при
  неуспехе JSON приon — один native numeric fallback3с. Валидный, но неожиданный layout
  остаётся фактом и не запускает fallback радиPASS. По каждой попытке точный rc/state/
  error_class/elapsed/bytecount. Rawstdout/stderr root0600 не отправляются вGit.
- Native fallback разбирает те же hook/priority/drop/reject metadata. Он не является
  полным manifest/packet доказательством. Numeric output описан в
  [официальном nft manual](https://www.netfilter.org/projects/nftables/manpage.html).
- Full diagnostic сохраняет до48 read_trace records/active stack для generation, nft/ip
  runner и ключевых Capture methods. Значения/исключения исходных вызовов сохраняются;
  неожиданная операция записи запрещена. Trace включает overhead и не является benchmark.
- Off-first preflight, одинenable25с и автономный always-off rollback прежние. При долгом
  enable диагностический job может быть прерван, что даёт частичные данные и отчёт.

Каноническое ТЗ: TEST-PLAN-REAL-MACHINE-0.2.0-wave3i.md. Шаблон той же фазы разделяет
loaded/kernel checkpoint и guard/on-guard.json. Реальная wave3i первоначально NOT_RUN.
Локально34 узких sampler теста PASS, Ruff PASS; новых netns/широких VM прогонов нет.
