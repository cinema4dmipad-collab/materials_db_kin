# Teswel — Signals & Error Codes (Appendix A, §9)

From КНТК.412231.100ИЭ. XML namespace paths use `KeenetiX/...` (receive) and `Robot/...` (send).

## EthernetKRL Config (Example)

```xml
<ETHERNETKRL>
  <CONFIGURATION>
    <EXTERNAL><TYPE>Server</TYPE><IP>172.31.1.201</IP><PORT>5050</PORT></EXTERNAL>
    <INTERNAL>
      <ENVIRONMENT>Submit</ENVIRONMENT>
      <IP>172.31.1.55</IP><PORT>54600</PORT>
      <ALIVE Set_Flag="1" Ping="200"/>
    </INTERNAL>
  </CONFIGURATION>
  <!-- RECEIVE: KeenetiX/* ; SEND: Robot/* -->
</ETHERNETKRL>
```

## Control Signals (Robot → SPPR)

| # | Signal | Type | Group | Data |
|---|--------|------|-------|------|
| 1 | CONNECT_SYSTEMS | BOOL | System | — |
| 2 | DISCONNECT_SYSTEMS | BOOL | System | — |
| 3 | DISCONNECT_TESWEL | BOOL | System | — |
| 4 | START_PROGRAM | BOOL | Program | — |
| 5 | END_PROGRAM | BOOL | Program | — |
| 6 | PAUSE_PROGRAM | BOOL | Program | — |
| 7 | RESUME_PROGRAM | BOOL | Program | — |
| 8 | CHECK_DATA | BOOL | Setings | — |
| 9 | START_CALIBRATION | BOOL | Setings | — |
| 10 | REFSAMPLE_POINT_OK | BOOL | Setings | — |
| 11 | END_CALIBRATION | BOOL | Setings | — |
| 12 | INIT_SESSION | INT | Session | Wheel type ID |
| 13 | INIT_TRAJECTORY | INT | Zone_control | Trajectory ID |
| 14 | ActPos_E1 | REAL | ActPos | E1 (rotation / A axis in SPPR) |
| 15–19 | @X, @Y, @Z, @A, @B, @C | REAL | ActPos | Pose; Z maps to V in SPPR |

## Status Signals (SPPR → Robot)

| # | Signal | Type | Group | Meaning |
|---|--------|------|-------|---------|
| 1 | SYSTEMS_CONNECTED | BOOL | System | Connect OK |
| 2 | SYSTEMS_DISCONNECTED | BOOL | System | Disconnect OK |
| 3 | INIT_SESSION_OK | BOOL | Session | Session initialized |
| 4 | SESSION_RESULT_OK | BOOL | Session | No defects |
| 5 | SESSION_RESULT_DEFECT | BOOL | Session | Defects found |
| 6 | INIT_TRAJECTORY_OK | BOOL | Zone_control | Trajectory initialized |
| 7 | START_PROGRAM_OK | BOOL | Program | Recording started |
| 8 | END_PROGRAM_OK | BOOL | Program | Recording finished |
| 9 | PAUSE_PROGRAM_OK | BOOL | Program | Paused |
| 10 | RESUME_PROGRAM_OK | BOOL | Program | Resumed |
| 11 | CHECK_DATA_OK | BOOL | Setings | Check passed |
| 12 | CHECK_DATA_FAIL | BOOL | Setings | Check failed |
| 13 | CHECK_DATA_REQUEST | INT | Setings | Lodgement for cal/setup |
| 14 | CHECK_DATA_FINISH | BOOL | Setings | Refsample checks done |
| 15 | REFSAMPLE_POINT | INT | Setings | Go to ref point ID |
| 16 | START_CALIBRATION_OK | BOOL | Setings | Calibration started |
| 17 | END_CALIBRATION_OK | BOOL | Setings | Calibration ended |
| 18 | REFSAMPLE_ID | INT | Setings | Refsample ID |
| 19 | KEENETIX_ERROR | INT | ERROR | Error code XYZ |

## Error Code Format

`XYZ` — X=class, Y=series, Z=number. Emitted on `KEENETIX_ERROR`.

| Code | Error | Cause (short) | Action |
|------|-------|---------------|--------|
| 200 | Unknown | Unclassified | Support |
| 210 | SPPR connect | Module not running | Restart SPPR menu in KeenetiX Pro |
| 310 | SDAQS connect | DB module down | Support |
| 410 | OEB connect | OEB off/fault | Restart OEB, check cables |
| **531** | Wheel type not found | Missing/wrong ID in DB | Check `wheels.number` |
| **532** | Duplicate wheel type | DB normalization | Support |
| **534** | Session create failed | Disk/DB fault | Support |
| **535** | No trajectories for wheel | Missing trajectories | Check `trajectories` for `wheel_id` |
| **541** | Duplicate trajectory | DB normalization | Support |
| **542** | Trajectory/wheel mismatch | Wrong ID for session | Check DB + control system |
| **543** | Trajectory not found | Missing/wrong ID | Check `trajectories.number` |
| **551** | Validation: defects | Sensor on defect area | Reposition, retry, check refsample settings |
| **552** | Validation: no contact | No acoustic contact | Reposition, check COF |
| **553** | Validation: zero data | Zero/empty A-scan from scanner channel | Check scanner/OEB connection |
| **591** | Out of zone | Robot left scan area | Check robot program/positioning |
| **592** | Speed exceeded | Feed too high | Check robot program |
| **610** | Signal sequence | Unexpected signal order | Check robot program |
| **620** | Bad message format | XML parse failure | Check robot program |
| **630** | Bad INT value | INT < 0 | Check robot program |

Series mapping: **530** = init_session, **540** = init_trajectory, **550** = check_data, **590** = kinematics, **600** = protocol.

## Abbreviations

| Abbr | Meaning |
|------|---------|
| УЗК | Ultrasonic testing |
| СППР | Decision support system (KeenetiX Pro) |
| СОЖ | Coolant/fluid supply |
| ОЭБ | Opto-electronic block (LUS-01) |
| ОК | Control object (wheel) |
| ЗК | Control zone (trajectory) |
| КО | Refsample |
