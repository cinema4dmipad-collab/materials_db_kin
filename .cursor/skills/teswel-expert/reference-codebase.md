# Teswel — KeenetiX Codebase Map

Links instruction concepts to repository paths for implementation and tests.

**RS0 / DSS:** [docs/components/teswel-rs0-dss.md](../../docs/components/teswel-rs0-dss.md) — RS0 check algorithm (`teswel_dss`), `CHECK_DATA` flow, SDAQS contract.

## Modules

| Path | Role |
|------|------|
| `controller_modules/teswel_controller.py` | TCP server, EthernetKRL XML, status signal dispatch |
| `daq_modules/sdaqs_modules/teswel_sdaqs.py` | Teswel SDAQS schema (wheels, trajectories, refsamples, sessions, scans) |
| `datas/configs/teswel_config.yaml` | Network, protocol, calibration expiry |
| `datas/configs/sdaqs_configs/default_records/teswel_default_records.yaml` | Default DB seed |
| `datas/configs/sdaqs_configs/models/teswel_models.yaml` | SDAQS models |
| `datas/configs/keenetix_errors.yaml` | Error code definitions (used in tests) |

## Test Suite (`tests/test_teswel/`)

Documented in `docs/components/test_teswel.md`.

| Area | Files | Covers instruction block |
|------|-------|---------------------------|
| Main cycle | `test_main_cycle/test_sessions_cycle.py`, `base_test_classes.py` | §5.6–5.7 session/zone cycle |
| Errors | `test_major_errors/*` | §9 error codes, signal sequence (610) |
| Sensor checks | `test_sensor_checks/*` | §5.8 calibration/settings/contact validation |
| Emulator | `utils/teswel_emulator.py` | Injects `sig_IN_teswel_status_signal` |
| Utils | `utils/teswel_test_utils.py`, `functions.py` | `report_cm`, `calibration_cycle`, `execute_program` |

## Typical Test Flow (maps to §5.5–5.7)

```
connect_systems → init_session → init_trajectory → check_data
  → [calibration_cycle if fail] → start_program → execute_program (mover)
  → end_program → session_result_ok | session_result_defect
```

## Key Fixtures

- `teswel_emulator` — simulate robot status signals (`--emulate-teswel`)
- `ReaderPatcher` / `a_scan_data_*` — inject A-scan data for check_data/program
- `keenetix_errors` — expected error bytecodes from YAML

## SDAQS Test Data

- `tests/test_teswel/sdaqs/teswel_default_records.yaml` — test wheel/trajectory/refsample records
- `tests/test_teswel/sdaqs/refsample_settings.yaml` — refsample calibration settings

When adding trajectories or refsamples in tests, mirror instruction rules: unique trajectory set per wheel type, RS0 immutable, lodgement numbers for calibration requests.
