# Ubuntu 24.04 — бюджет Selective, отказ и живой контроль VPN (553de56) — 2026-11-18

- RESULT: **TESTS PASS (143 + 3 panel + 1 exhausted_budget отдельно + Qt 11), INSTALL
  PASS (6/6 файлов с --gui, таймер 95 мин), API_WEB_QT PASS (probe_budget идентичен в
  обоих API, 401 без авторизации, остаток/UTC согласованы в вебе и desktop), PROBE_
  ACCOUNTING PASS (нормальная попытка: ровно +1 МиБ = 0.5 пара + 0.25 встроенный
  повтор CDN + 0.25 VPN-контроль, пофазно), BUDGET_STOP PASS (малый лимит 20 МиБ →
  исчерпание до нуля → следующий цикл даёт reason=probe_budget, правило снято,
  воркеры inactive, резервы не растут на 20 опросах), UTC_ROLLOVER NOT_RUN (граница
  не наступила в живом окне; часовая фикстура test_exhausted_budget…=PASS), START/
  RECHECK NOT_RUN (fallback по TLS прямого канала — как в предыдущих раундах),
  MEDIA_PATH NOT_RUN, VPN_RETURN PASS (после исчерпания бюджета новый сеанс YouTube
  через VPN — xray +51 МБ / 48.8 c), RESTORE PASS (accept, restore-completed,
  check_installed 6/6 — слой `553de56` оставлен)**.
- CODE: `553de562572c192c78454c927816155b02efc28b`; Ubuntu 24.04.5 LTS; Qt 6.4.2 /
  PyQt6 6.6.1 / Python 3.12.3. Установка: 5 файлов CORE + gui/zapret2.py, конфиги
  byte-identical до/после, GUI перезапущен штатно.

## Таблица результата

| Блок | Результат | Наблюдение |
| --- | --- | --- |
| TESTS | PASS | 143 passed (8 наборов); panel -k zapret2: 3 passed; `test_exhausted_budget_preserves_vpn_control_and_reopens_after_utc_boundary` — PASS отдельно (закрытие маршрута, расход на VPN-пробу, без нового воркера, возобновление после UTC-границы на фикстурных часах); Qt-фикстура 11 passed |
| INSTALL | PASS | prepare/apply complete, check_installed 6/6, таймер 95 мин (NEXT 00:13), GUI перезапущен |
| API_WEB_QT | PASS | `/api/state` и `/api/zapret2/overview`: probe_budget идентичен {spent 18874368, limit 268435456, remaining 249561088=max(0,limit−spent), resets_at 1795046400=00:00 UTC}; без авторизации оба 401; last_transport_ok_at отсутствует в off; веб «Остаток бюджета проб — 238 из 256 МиБ · сброс в 00:00 UTC», desktop «Домены и проверки»: «238.00 МиБ · сброс в 00:00 UTC» — согласовано; 390px без overflow; spent стабилен между опросами в off |
| PROBE_ACCOUNTING | PASS | нормальная попытка (kit 180/120/256, клик 19:44:17Z): spent 18874368 → +524288 (preparing, плановая пара) → +262144 (встроенный CDN-повтор) → +262144 (fallback, VPN-контроль) = **19922944, ровно +1 МиБ за попытку**; планируемая пара 0.5 МиБ и резервы 0.25 подтверждены пофазно |
| BUDGET_STOP | PASS | лимит 20 МиБ через форму (spent не обнулён, remaining=1048576 ≥ 786432 — запуск разрешён, лимит одинаков в 2 API и 2 UI): попытка списала 0.5+0.25+0.25 → remaining=0 ровно на лимите; режим оставлен до следующего цикла → причина **`fallback/probe_budget`** (19:51:18Z), воркеры MainPID=0, spent заморожен на 20 опросах (~3.5 мин), правило снято |
| UTC_ROLLOVER | NOT_RUN | resets_at (00:00 UTC) не наступил в живом окне прохода (опыт завершён в 20:0x UTC); часовая фикстура — PASS (см. TESTS) |
| START_RECHECK | NOT_RUN | fallback/youtube_cdn_probe_failed: page ok 348 мс, CDN TLS-таймаут 20 321 мс (прямой канал к googlevideo деградирует — как в предыдущих раундах); до active не дошло |
| MEDIA_PATH | NOT_RUN | active не достигнут |
| VPN_RETURN | PASS | после BUDGET_STOP: off кнопкой → off/off; новый сеанс YouTube через VPN — дельта ACCEPTED client_rule=false, **xray +51 МБ / 48.8 c**, cfg_changed=false (первая пара на pending-переходе честно переснята) |
| RESTORE | PASS | accept: конфиги OK/OK, restore-completed присутствует, check_installed 6/6 (5 CORE + gui/zapret2.py); лимит восстановлен 256 МиБ, spent дня (20 МиБ) сохранён в журнале: {spent 20971520, limit 268435456, remaining 247463936}; таймер остановлен (запас ~73 мин) |

## Живая хронология бюджета (UTC)

| Время | Событие | spent | remaining |
| --- | --- | --- | --- |
| 19:44:17 | клик (kit 180/120/256) | 18874368 | 249561088 |
| 19:45:25 | preparing/nfqueue: пара | 19398656 (+0.5 МиБ) | 249036800 |
| 19:45:33 | встроенный CDN-повтор | 19660800 (+0.25) | 248775680 |
| 19:45:49 | fallback: VPN-контроль | 19922944 (+0.25) | 248512640 |
| 19:47:24 | клик с лимитом 20 МиБ | 19922944 | 1048576 |
| 19:48:43 | пара | 20447232 (+0.5) | 524288 |
| 19:49:00 | повтор CDN | 20709376 (+0.25) | 262144 |
| 19:49:08 | fallback: VPN-контроль | **20971520 (=лимит)** | **0** |
| 19:51:18 | следующий цикл: `probe_budget`, воркеры inactive | 20971520 (не растёт) | 0 |

- Отказы обеих попыток — youtube_cdn_probe_failed (page ok 348 мс; TLS прямого
  канала деградирует — согласуется с [предыдущим отчётом](2026-11-18_gui-selective-status.md)).
- Финал: off/off, воркеры inactive, VPN/panel 200, конфиги `89bf2a67…`/`33916cb5…`
  byte-identical, диск 43 ГБ, тестовый Chrome закрыт; JSONL/IP/URL — в приватном
  каталоге опыта (0700).

## Наблюдения для Codex

1. **Резервная механика точна**: 0.5/0.25/0.25 списания совпали с фазами попытки
   байт-в-байт; исчерпание останавливает попытки на следующем цикле без роста
   резервов и без попыток обойти лимит; рабочий PID не поднимался после probe_budget.
2. **Бюджет виден одинаково во всех поверхностях** (2 API, веб, desktop-окно) с
   одинаковыми значениями и границей сброса; 390px и компактная тема не ломают
   отображение.
3. Восстановление лимита после опыта возвращает remaining без сброса spent дня —
   журнал дня сохраняется (день продолжается).
4. START оставляется для следующего прохода при восстановлении прямого TLS-канала
   к googlevideo; все приготовления (kit, сборщики, пары) проверены.
- Publication commit: `19b3b3b84f068459d32c099d29115918a8227201` (97fbed9 → 19b3b3b, remote verified byte-identical to local HEAD).
