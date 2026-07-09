---
name: teswel-expert
description: Expert knowledge on Teswel laser UT wheel weld inspection workflow, status-signal protocol, SDAQS data model, and refsample calibration. Use when working with Teswel integration, teswel_controller, test_teswel, SDAQS wheels/trajectories/refsamples, status signals (CONNECT_SYSTEMS, INIT_SESSION, INIT_TRAJECTORY, CHECK_DATA, START_PROGRAM), or KeenetiX Pro automatic mode for wheel pairs.
---

# Teswel Expert

Operational and algorithmic knowledge for the **Teswel** wheel-pair laser ultrasonic inspection system (KeenetiX Pro as SPPR server, robot as client).

## When to Read References

| Task | Read |
|------|------|
| Workflow / signal sequence / block logic | [reference-instruction.md](reference-instruction.md) §4–5 |
| SDAQS entities (wheels, trajectories, refsamples, sessions, scans) | [reference-instruction.md](reference-instruction.md) §5.4 |
| Status signal names, types, XML tags | [reference-signals-errors.md](reference-signals-errors.md) §Signals |
| Error codes 530/540/550/590/610 | [reference-signals-errors.md](reference-signals-errors.md) §Errors |
| Refsample check / calibration / manual setup | [reference-instruction.md](reference-instruction.md) §5.8, §5.12 |
| Code & tests in this repo | [reference-codebase.md](reference-codebase.md) |

**Source document:** `КНТК.412231.100ИЭ` — *Инструкция по эксплуатации* (OOO KINETIK, 2025). Full extracted text is in the references above.

## High-Level Algorithm

Linear shift flow per session:

```
Launch → Connect systems → [Fill DB] → Automatic mode
  └─ Session cycle (INIT_SESSION → trajectories → SESSION_RESULT_*)
       └─ Zone cycle (INIT_TRAJECTORY → CHECK_DATA* → START_PROGRAM → scan → END_PROGRAM)
→ [View results] → Disconnect → Shutdown
```

`*` CHECK_DATA block may branch into calibration (RS0) or manual refsample setup before START_PROGRAM.

## Signal Sequence (Automatic Mode)

Minimal happy path for one wheel type with one control zone:

1. `CONNECT_SYSTEMS` → `SYSTEMS_CONNECTED`
2. `INIT_SESSION` (wheel type `number`) → `INIT_SESSION_OK`
3. `INIT_TRAJECTORY` (trajectory `number`) → `INIT_TRAJECTORY_OK`
4. `CHECK_DATA` → `CHECK_DATA_OK` (or calibration branch → `END_CALIBRATION_OK`)
5. `START_PROGRAM` → `START_PROGRAM_OK` → robot moves → `END_PROGRAM` → `END_PROGRAM_OK`
6. Repeat 3–5 for all trajectories of the wheel type
7. `SESSION_RESULT_OK` or `SESSION_RESULT_DEFECT`
8. Repeat 2–7 for next wheel; `DISCONNECT_SYSTEMS` / `DISCONNECT_TESWEL` on shutdown

Signal is **active** when its value changes and is not a special zero/null value (EthernetKRL/XML over TCP; KeenetiX = server, robot = client).

## SDAQS Data Model (Quick Map)

| Instruction term | SDAQS table | Key fields |
|------------------|-------------|------------|
| Тип ОК (wheel type) | `wheels` | `number`, `name`, `max_diameter`, `max_width` |
| Зона контроля (trajectory) | `trajectories` | `number`, `wheel_id`, `refsample_id`, `a_*`, `v_*`, `angle`, `fead` |
| Контрольный образец (refsample) | `refsamples` | `number`, `lodgement`; **RS0** is immutable calibration standard |
| Сессия | `sessions` | auto-created on `INIT_SESSION` |
| Скан | `scans` | auto-created on `END_PROGRAM`; `is_defective`, `is_analysed` |

Scanner settings (`reference_file`, `settings`, `stc_alpha`) are written during manual setup on «Настройки сканера», not when creating refsample rows.

## Codebase Entry Points

- Controller / XML protocol: `controller_modules/teswel_controller.py`
- SDAQS scheme: `daq_modules/sdaqs_modules/teswel_sdaqs.py`
- Config: `datas/configs/teswel_config.yaml`, `datas/configs/sdaqs_configs/`
- Integration tests: `tests/test_teswel/` — see [reference-codebase.md](reference-codebase.md)
- Test docs: `docs/components/test_teswel.md`

## Agent Rules

1. **Read references before** changing Teswel workflow, signal handling, or SDAQS schema usage.
2. **Do not contradict** the instruction signal order; error series 530/540/550 match init_session / init_trajectory / check_data blocks.
3. **RS0** (`refsamples` record) must not be modified — used for base calibration.
4. Each wheel type needs its **own** trajectory set even if parameters duplicate.
5. For GUI/manual setup details (STROBE, STC, filter), defer to §5.12 in [reference-instruction.md](reference-instruction.md) and the separate methodology document cited there.
