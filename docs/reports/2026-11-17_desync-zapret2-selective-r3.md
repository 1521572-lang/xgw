# Ubuntu 24.04 — T11.3 r3: Selective и диагностика HTTPS-проб — 2026-11-17

- RESULT: **PASS — Selective включён из веб-интерфейса с активным youtube_transport_ok и
  полной диагностикой transport_probes; видео ≥150 c пригодного 720p с одновременным
  VPN-контролем; выключение кнопкой; restore accept (слои остались)**. Установка
  `a8b177f6deec1e2c20c4effef977bf144bdf4f24` — 8/8 манифест == SHA (new), таймер 90 м
  armed до apply, конфиги byte-identical. §2 тесты: **93 passed** + `node --check` +
  `bash -n` обоих скриптов. §3: при off/off обе новые строки карточки — «Нет данных»,
  `evidence.transport_probes={}` в overview и /api/state; retry-сохранение — `saved`,
  **новая ревизия b90318dd одновременно в обоих API**, Proton показывает повтор 120 с;
  390 px/темы читаемы. §4: настройки Selective через форму — `saved`, count=2, секрет
  пары r2 нигде не отражён; включение кнопкой → **active/youtube_transport_ok за ~60 c**
  с полной диагностикой: **page ok/http 200/elapsed 457 мс (≥16 КиБ прошёл — фикс окна
  8→12 c работает), cdn ok/http 200/bytes 31/elapsed 274 мс**, transport=https_reachable,
  playback=not_tested. §5 видео Selective: интервалы 154 c и 183 c, 720p 100 % сэмплов,
  буфер 64–82, пауз нет, SABR POST свежие; **одновременный контроль example.com и
  gnu.org загрузились в браузере** (заголовки подтверждены); дельты route_evidence —
  **PARTIAL**: applied-конфиг Xray переписывается при активном Selective (toggle
  probe-inbound каждый check-цикл; дифф содержимого — 0 смысловых полей, меняется
  сериализация) — пара снапов структурно incomparable, прибор честно отклонил; привязка
  медиа к прямому пути — по CDP SABR + клиентскому правилу + активной очереди. Длинный
  15+6+5 — **NOT_RUN** (остаток таймера < 35 мин на момент решения). §6: выключение
  кнопкой → policy_matched/off, transport_probes очищен, новый сеанс YouTube через VPN —
  дельта **xray +496 КБ/25 c, client_rule=false**; restore **accept**, verify_manifest
  new 8/8, Proton/панель/VPN/control 200, таймер остановлен.
- CODE: `a8b177f6deec1e2c20c4effef977bf144bdf4f24`; база установки `6f69cc2…` —
  установщик сверил побайтово (BLOCKED_BASE не было). Манифест new (8):
  panel.py `730907ec…`, zapret2_control.py `cbc33519…` (новые возможности/причины),
  zapret2_management.py `e678a85d…`, zapret2.html `03163e27…`, zapret2.css
  `21e7be8d…`, zapret2.js `6c954f97…`, zapret2.py `c5e32045…` (окно пробы 12/6 c),
  gui/zapret2.py `1150ef07…`. После accept файлы == new_sha на диске.
- Таймер: armed 2026-11-17T13:02:09Z, NEXT 17:32:07 MSK (1 ч 29 мин), остановлен
  после финальной сверки. Установленные файлы оставлены (accept).

## §1–2 Подготовка, тесты, установка — PASS

- Снапсшот машины: off/off, воркеры inactive, очередь пуста (proc-файл отсутствует),
  VPN/panel 200, конфиги `89bf2a67…`/`33916cb5…`; место 46 ГБ; открытых удалённых
  файлов нет (tcpdump отсутствует с перезагрузки владельца).
- Целевые тесты (9 наборов/узких тестов): **93 passed**; node v18.19.1
  (`node --check` OK), `bash -n` OK.

## §3 Интерфейс при off/off — PASS

- Карточка: обе новые строки проб — «Нет данных»; `evidence.transport_probes={}` в
  overview и /api/state; 390 px — строки читаемы, overflow нет (обе темы).
- Retry-сохранение при off/off: 300→120 — `saved`; новая ревизия **b90318dd**
  одновременно в overview и /api/state; Proton-страница zapret2 показывает «повтор
  после отказа через 120 с»; воркеры остались inactive — сохранение не запускало
  обработчик.

## §4 Selective и две HTTPS-пробы — PASS

- Через форму: multisplit + 6 доменов + transport on + страница watch + свежая
  подписанная CDN `/videoplayback` (GET 200 до отправки, получена из DevTools того же
  Chrome). Результат `saved`, count=2; подпись отсутствует в ответе, двух GET и на
  экране (поля password, логи чисты).
- «Домены через zapret2» + подтверждение → preparing/nfqueue → **active/
  youtube_transport_ok за ~60 c**. UTC включения 2026-11-17T13:19:58Z, ревизия
  `8a2d3f09`, transport_probes: page {ok:true, phase:body, kind:ok, http:200,
  elapsed_ms:457}, cdn {ok:true, phase:body, kind:ok, http:200, bytes:31,
  elapsed_ms:274}. VPN остаётся работоспособен.
- Честная оговорка процесса: первый клик кнопки при off/popытке после save пришёлся на
  disabled-рендер (старые blockers/скрытая вкладка) — включение выполнено после
  активации вкладки; двойная замена URL не потребовалась (первая пара принята).

## §5 Видео и одновременный VPN-контроль — PASS (MEDIA_PATH=PARTIAL)

- Интервал Selective: **154–183 c наблюдения, 720p в 100 % сэмплов, пауз нет**,
  буфер 64–82 c, свежие SABR POST (15–36) — CDP; отдельная контрольная вкладка
  example.com и gnu.org — **загрузились** (титулы подтверждены), их байты — через
  штатный VPN-выход (xray-группа, native AUTO auto-4).
- Дельты route_evidence: **PARTIAL** — при активном Selective applied-конфиг Xray
  переписывается каждый probe-цикл (toggle probe-inbound; дифф содержимого — 0
  смысловых полей), прибор честно возвращает `incomparable_snapshots`; три попытки
  пары (включая окно сразу после probe-цикла) — все отвергнуты корректно. Привязка
  медиа к прямому пути: CDP SABR + клиентское правило + активная очередь (гейт
  transport_probes) — частичное, по ТЗ помечено PARTIAL.
- Vision: кадры подтверждены (видео движется, рекламы/диалогов нет).

## §6 Выключение и возврат — PASS

- Кнопка off → policy_matched/off, **transport_probes очищен ({})**, воркер inactive.
- Новый запрос YouTube через VPN — дельта **xray +496 КБ за 25 c**, client_rule=false.
- Restore **accept**: panel byte-identical, verify_manifest new 8/8 на диске,
  Proton перезапущен от пользователя, панель/VPN/control 200. Таймер остановлен.

## Финальное состояние

off/off, очередь пуста (proc-файл отсутствует), воркеры inactive, acct=0, VPN 200,
panel 200, конфиги `89bf2a67…`/`33916cb5…` byte-identical. Установленный слой
a8b177f оставлен (8 файлов == new_sha). Диск 46 ГБ свободно. Приватное: скрипты/
снапы/скриншоты в `~/xgw-sel-r3.fs` (0700/0600); URL-подписи, IP, конфиги — на машине.
- Publication commit: `536ede68c925e6ece866301174865a0477b94e76` (bb31f21 → 536ede6, remote verified byte-identical to local HEAD).
