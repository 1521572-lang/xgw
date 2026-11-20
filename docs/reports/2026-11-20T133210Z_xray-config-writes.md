# ThinkCentre · кто применяет конфигурацию Xray во время просмотра — 2026-11-20

- RESULT: **INSTALL PASS (apply), ТЕСТЫ КАНДИДАТА FAIL → по правилу ТЗ
  «при любом сбое после создания таймера — §4»: WRITER_CONTROL, LIVE_PLAY,
  FLOW, CONFIG_WRITER — NOT_RUN (заблокированы фазой тестов); RESTORE
  VERIFIED (3 файла = базе `3a00777`, off/off fresh, таймер остановлен)**.
  Разбор отказов: 20 отказов на кандидате (root), из них **17
  предсуществующие** — тесты `test_daemon.py` падают идентично и на
  принятой базе `3a00777` под root (впервые запущены в этой серии; ранее
  test_daemon не входил в наборы ТЗ); **3 новых отказа кандидата —
  `test_applier.py`** (`test_rollback_to_last_good_when_new_config_does_not_
  start`, `test_failed_when_rollback_does_not_help`,
  `test_first_start_without_last_good_reports_failure`) с
  `AttributeError: 'Event' object has no attribute 'bytes_read'` —
  рассинхрон new `apply/applier.py` с тестовыми стабами в самом кандидате.
  Снапшот-механика нового кода не проверена вживую (блокер тестов).
- ОС: Ubuntu 24.04.5 LTS; база 11/11 (5 `3a00777` + 6 `08d31ee`); кандидат
  `dce7ec8` — 3 файла (apply/applier.py, apply/singbox_generation.py,
  daemon.py) поверх `3a00777` (apply из `1e27384`); sudo -n (NOPASSWD),
  NoNewPrivs=0; VPN baseline 206/65536 + delta xray (окно 1.1с).

## §1 Установка и тесты

- prepare/apply complete; guard rollback 90м (`xgw-write-trace-rollback`);
  off/off fresh после apply; `install-location` записан.
- Тесты кандидата от пользователя: 20 FAILED / остальные passed;
  от root (`sudo -n env PYTHONPATH=… pytest`): **20 FAILED** — те же.
  Контрольный прогон `tests/test_daemon.py` на чистой базе `3a00777`
  (отдельный worktree, root): **17 FAILED** → совпадающий набор
  предсуществующих отказов; разница «только в кандидате» — ровно 3 теста
  applier (см. RESULT). Отказов «только на базе» нет (кандидат ничего не
  починил в этом наборе).
- Первопричина новых отказов: в тестах `test_applier.py` кандидата
  события-стабы не содержат поле `bytes_read`, которое читает новый
  `applier.py` (`src/xgw/daemon.py:3595`-подобный путь в applier) —
  рассинхрон кода и тестов внутри кандидата.
- Правило ТЗ применено: сбой зафиксирован, фазы §2/§3 не начинались,
  выполнено восстановление.

## §4 Восстановление

guard rollback rc 0; marker; sha256 config+panel OK; **3 файла оверлея
сверены с базой `3a00777` (cmp, поштучно)**; xgw.service active; воркеры
MainPID=0; off/off fresh (первый опрос); ipify ок; таймер остановлен
(ActiveState=inactive) → **RESTORE VERIFIED**. 12 записей steps.tsv;
сырые журналы тестов — в каталоге опыта 0700.

## Статусы по ТЗ

| Статус | Значение |
| --- | --- |
| INSTALL | PASS (prepare/apply/timer), но **тесты FAIL — блокер** |
| WRITER_CONTROL | NOT_RUN — заблокирован тестовым сбоем §1 |
| LIVE_PLAY | NOT_RUN — заблокирован |
| FLOW | NOT_RUN — заблокирован |
| CONFIG_WRITER | NOT_RUN — атрибуция не выполнялась (код кандидата требует сначала устранить 3 отказа applier) |
| RESTORE | **VERIFIED** |

## Наблюдения для Codex

1. **Новые отказы кандидата — 3 теста applier**: тестовые стабы событий
   отстали от нового API applier (`bytes_read`). Синхронизировать стабы
   либо читать поле опционально; пока этого нет — код записи-трассировки
   не может быть принят по правилам серии (тестовый гейт).
2. **Предсуществующие 17 отказов test_daemon на принятой базе** (root):
   `test_daemon.py` в серии ТЗ не запускался ни разу — и сразу дал массовый
   рассинхрон (AttributeError bytes_read и др.). Стоит либо привести
   test_daemon в соответствие с базой `3a00777`, либо явно исключить/починить
   до включения в наборы ТЗ; иначе каждый следующий кандидат будет нести
   «шум» из 17 отказов, маскируя свои.
3. Права: тесты test_daemon требуют root-класса операций (SO_MARK, nft
   netlink) — запуск от пользователя даёт дополнительные warnings; при
   интеграции в ТЗ указывать ожидаемый уровень привилегий.
4. Инфраструктура атрибуции (`docs/helpers/xray_config_writes.py`,
   journalctl --grep=xray_config_write) установлена, но не отработала ни
   одного живого окна — проверка писателей остаётся открытой для следующего
   кандидата после починки тестов.
- Publication commit: `463d20c89dd2175d174fb2bb47d5ff7e35dc196b` (6ad275e → 463d20c, ancestor verified).
