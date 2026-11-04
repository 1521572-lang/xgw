# AN:850/852; два expected-operation-error fixtures требуют исправления

Обновление04.11.2026: [AO66 принят](REVIEW-REAL-MACHINE-0.2.0-wave3ao.md), оба ANfixturedefects
закрыты actualAO. OriginalAN850/852 неизменён. Ниже история; runtimegatesfalse.


Source: docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3an-2026-11-04.md.
Pinnedpureformatter воспроизвёлexactpublicprefix, originalнеизменён.
Логикапродукта корректно сохраняетRuntimeError изтела/checker, пишетUNKNOWN1/noReceipt.
Сборщик не распознавал намеренный RuntimeError("PRIVATE_FIXTURE"). Этоfixturebug.
Все852исполнялись;850принимаютсятолькоscoped;полныйANнеPASS. WorkerexitNOT_COLLECTED.
Productsrc/units/networkнеизменны. AO66исправляет2failures+всепозиции1–32;неповторять850.
7targetedtests/RuffPASS. FullAO/ThinkCentreNOT_RUN. All7gatesfalse/LiveCBLOCKED_BOOTSTRAP.
Детальные точные данные разбора:

```json
{
  "report_commit": "296d2a062eae3a521860b7f099ee3ca245ea4a7e",
  "tested": {
    "head": "755a5f0d52e94714d7c17fcaef9c7a9fdcecaa38",
    "tree": "c0ff6c10d5ae4947c9e803bae2cd2987eef172e2"
  },
  "passed": 850,
  "completed": 852,
  "failed": [
    "F_CHECKER_RAISE",
    "F_BODY_RAISE"
  ],
  "batch_ms": 263577,
  "case_sum_ms": 214706,
  "prefix_byte_equal": true,
  "footer": {
    "nnp": 0,
    "sudo_rc": 0,
    "start_rc": 0,
    "monitor_rc": 0,
    "show_rc": 0,
    "shape_rc": 3,
    "report_rc": 0,
    "before_health": "HEALTHY_ON",
    "after_health": "HEALTHY_ON",
    "before_pool": "OFF",
    "after_pool": "OFF",
    "before_link": "ALIVE",
    "after_link": "ALIVE",
    "versions_unchanged": true,
    "owner_actions": 0
  },
  "worker_exit_rc": "NOT_COLLECTED",
  "acceptance": "850 scoped; two expected-operation-exception fixture defects OPEN"
}
```

[Новое ТЗ AO66](TEST-PLAN-REAL-MACHINE-0.2.0-wave3ao.md)
