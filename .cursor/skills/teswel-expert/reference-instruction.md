# Teswel — Instruction Extract (КНТК.412231.100ИЭ)

Extracted from *Инструкция по эксплуатации* системы лазерного УЗК сварных швов стальных колес (OOO «КИНЕТИК», Москва 2025). Figures omitted; text preserved for algorithm and domain logic.

## 1. Purpose

System detects weld defects: crack, lack of fusion, porosity, slag/non-metallic/metallic inclusions, burn-through.

## 2–3. Hardware (Summary)

- **SPPR workstation** (KeenetiX Pro): control block, switch, operator UI.
- **COF & OEB station**: KINETIK LUS-01 OEB, coolant supply.
- **Transducer fixture**, laser-UT transducer, setup zone (refsample + lodgement).
- Robot + rotary table send position (X,Y,Z,A,B,C), E1 angle, and wheel type ID to SPPR.

Control result: two signals — OK (no defects) or DEFECT (whole product rejection).

## 4. Control

### 4.1 General

- Robot sends transducer pose, E1, and **wheel type ID** (full specs live in SPPR DB).
- SPPR auto-reconfigures on wheel type or control zone ID change (loads settings from DB).

### 4.2 API

- Transport: **Ethernet/IP (TCP/IP)**; SPPR = **server**, robot control system = **client**.
- Message format: **EthernetKRL (XML)**.
- Signal active when value **changes** and is not a special zero value.

### 4.3 GUI Operator Tasks

- Fill DB (§5.4), manual SPPR setup (§5.12), review results (§5.9), monitor status/errors (§5.3, §5.5, §5.8, §9).

## 5. Work Program

### 5.1 Structure

Linear flow for a shift:

1. **Launch** + **Connect systems**
2. Optional **Fill DB**
3. **Automatic mode** (main inspection: reconfig, transducer check, scan, DB write, analysis, SPPR signals)
4. Optional **Manual setup** (reject tuning)
5. Optional **View results**
6. **Disconnect** + **Shutdown**

### 5.2 Launch

Power and start: robot control, robot, SPPR (KeenetiX Pro UI), OEB (2 min warm-up), COF pump.

### 5.3 Connect Systems

| Direction | Signal | Type | Meaning |
|-----------|--------|------|---------|
| Control → SPPR | `CONNECT_SYSTEMS` | BOOL | Start connection |
| SPPR → Control | `SYSTEMS_CONNECTED` | BOOL | All systems connected |

Robot→SPPR connection starts after app init. Other systems connect on `CONNECT_SYSTEMS`. Status tab: green=OK, yellow=in progress, red=disconnected. Retry on failure.

### 5.4 Fill DB

Optional; no dedicated protocol block. **SDAQS connection required.** Can edit DB without scanner/mover/SPPR module connection.

**Process model:**

| Entity | Description |
|--------|-------------|
| **ОК** (control object) | Physical inspected item |
| **Тип ОК** | Shared geometry/criteria class |
| **ЗК** (control zone) | Inspected segment; unique set per wheel type |
| **КО** (refsample) | Physical sample for SPPR/scanner tuning; one KO may map to many zones |
| **Session** | One OK inspection cycle |
| **Scan** | Data for one zone in a session |

**Tables (`«Сбор и хранение данных»`):**

**`wheels`** — wheel types:
- `description`, `max_diameter`, `max_width`, `name`, `number` (int sent by control system)

**`refsamples`** — refsamples:
- `description`, `name`, `number`, `lodgement` (sent during calibration/setup)
- **`RS0`** — base calibration standard; **do not change**
- `reference_file`, `settings`, `stc_alpha` added during manual scanner setup, not at create time
- Create one refsample per unique combination of weld type, fillet size, shell thickness, materials, etc.

**`trajectories`** — control zones:
- `name`, `number`, `refsample_id`, `wheel_id`
- Zone params: `diameter`, `a_mm` (mm vs degrees for rotation axis), `a_step`, `a_0`, `a_len`, `v_step`, `v_0`, `v_len`, `angle` (90° = scan while rotating positioner), `fead`
- Full circle: `a_len=360` in angular mode, `a_len=0` in linear mode
- **Each wheel type needs its own trajectory set** even if duplicated

**Auto-filled:** `sessions`, `scans`. **Service only:** `movers`, `scanners`, `labeling_classes`, `scans_buckets`, `labeling_buckets`.

### 5.5 Automatic Mode

Two nested loops:

1. **Session cycle** — per OK; reconfig to wheel type
2. **Zone cycle** — per zone; reconfig, transducer check, record, save, zone analysis

### 5.6 Session Cycle

| Direction | Signal | Type | Data / meaning |
|-----------|--------|------|----------------|
| Control → SPPR | `INIT_SESSION` | INT | Wheel type `number` in DB (≠0) |
| SPPR → Control | `INIT_SESSION_OK` | BOOL | Session ready |
| SPPR → Control | `SESSION_RESULT_OK` | BOOL | No defects in any zone |
| SPPR → Control | `SESSION_RESULT_DEFECT` | BOOL | Defect in ≥1 zone |

On success: `sessions` row created. Errors → `KEENETIX_ERROR` series **530**. Then zone cycle; after all zones → session result. Next session starts with new `INIT_SESSION`.

### 5.7 Zone Cycle

| Direction | Signal | Type | Data / meaning |
|-----------|--------|------|----------------|
| Control → SPPR | `INIT_TRAJECTORY` | INT | Trajectory `number` (≠0) |
| Control → SPPR | `START_PROGRAM` | BOOL | Begin recording |
| Control → SPPR | `END_PROGRAM` | BOOL | End recording; create scan |
| SPPR → Control | `INIT_TRAJECTORY_OK` | BOOL | Zone ready |
| SPPR → Control | `START_PROGRAM_OK` | BOOL | May start motion |
| SPPR → Control | `END_PROGRAM_OK` | BOOL | Scan saved to `scans` |

Flow: reconfig → move to zone start → transducer checks (§5.8) → `START_PROGRAM` → move → `END_PROGRAM`. When all zones for session done, SPPR exits zone loop and analyzes session. Else waits for next `INIT_TRAJECTORY`. Errors → series **540**.

### 5.8 Transducer Check

| Direction | Signal | Type | Role |
|-----------|--------|------|------|
| Control → SPPR | `CHECK_DATA` | BOOL | Start check |
| Control → SPPR | `START_CALIBRATION` | BOOL | Start cal/setup |
| Control → SPPR | `END_CALIBRATION` | BOOL | Finish cal/setup |
| Control → SPPR | `REFSAMPLE_POINT_OK` | BOOL | At ref point |
| SPPR → Control | `CHECK_DATA_OK` | BOOL | Pass — proceed to recording |
| SPPR → Control | `CHECK_DATA_FAIL` | BOOL | Fail — branch |
| SPPR → Control | `CHECK_DATA_FINISH` | BOOL | Refsample points OK |
| SPPR → Control | `CHECK_DATA_REQUEST` | INT | Lodgement number for cal/setup |
| SPPR → Control | `REFSAMPLE_POINT` | INT | Move to ref point on sample |
| SPPR → Control | `END_CALIBRATION_OK` | BOOL | Calibration ended |

**Check order:**

1. **Calibration expiry** (`last_calibration_date` on `refsamples`, RS0):
   - Expired → `CHECK_DATA_FAIL` → `START_CALIBRATION` → `CHECK_DATA_REQUEST` (RS0 lodgement) → move to point 0 → `CHECK_DATA`
   - Success → `CHECK_DATA_FINISH` → `END_CALIBRATION` → `END_CALIBRATION_OK`
   - Need transducer/ring replacement → `REFSAMPLE_POINT` (point 1 = service) → operator replaces → confirm → retry until `CHECK_DATA_FINISH`

2. **Settings expiry** (same date field, per-zone refsample):
   - Same pattern; opens «Настройки сканера» for manual setup (§5.12) → operator saves → `CHECK_DATA_FINISH`

3. **Contact validation on OK** (no-contact detection):
   - Re-`CHECK_DATA` after cal/setup
   - Pass → `CHECK_DATA_OK`
   - Fail → view signal, retry cal, retry manual setup, reposition/retry, or **ignore** (force `CHECK_DATA_OK`)

Block always: starts with `CHECK_DATA`, ends with `CHECK_DATA_OK`.

### 5.9 View Results

Outside automatic mode. Select scan in `scans`; fields `is_defective`, `is_analysed`, `defective_reason`. Download to «Результаты сканирования» for A/B/C-scans. Retention via `scans_expire_timedelta` (keys 0=OK, 1=defect).

### 5.10 Disconnect

`DISCONNECT_SYSTEMS` → `SYSTEMS_DISCONNECTED`.

### 5.11 Shutdown

`DISCONNECT_TESWEL` — terminal disconnect from robot side on control failure. Power off all components.

### 5.12 Manual Setup

Triggered after move to refsample during check block. Methodology in separate document *Методика лазерного ультразвукового контроля сварных швов стальных колес*.

**Saved settings:** reference signal, filter params, STROBE, STC (ВРЧ), ref point positions.

**Procedure (two ref points A-A / B-B with flat-bottom holes h1, h2):**

1. Reference signal — select, verify, close preview
2. At point 1: record, switch to «Обработанный»
3. Filter — enable filter/contrast/convolution; set band limits
4. STROBE — add CONTACT (contact peak), HIGH/LOW on fillet defect; depth markers
5. STC — «Получить» amplitudes at shallow and deep defect points; enable STC function
6. No-contact point — verify CONTACT strobe inactive
7. Save — «Сохранить настройки» → select refsample → confirm → «Принять настройки»; cycle continues

## 6–8. Maintenance, COF, Transducer Replacement

- Regular maintenance: COF cleaning monthly, fixture lubrication monthly, SPPR blow-out bimonthly, refsample verification yearly.
- COF: gel:water 1:1; level sensor; pump on contact via 15-pin cable.
- Transducer/ring replacement: service position, disconnect cables/fiber/COF tube, 4×M3×10 screws, replace, reconnect, confirm on SPPR, enable COF.
