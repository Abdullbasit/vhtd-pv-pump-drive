#!/usr/bin/env python3
"""
hs300_protocol.py - HS300-22K link driver.  NO UI, NO I/O POLICY.

This file is the reference implementation of the wire protocol and the
register map. It is deliberately free of any dashboard, threading or display
code so that porting it to the ESP32 is a mechanical translation:

    Python                        ESP32 / C++
    ----------------------------  --------------------------------------
    Link.open()                   Serial2.begin(115200, SERIAL_8N1, rx, tx)
    Link._frame()                 build into a uint8_t[]
    Link._txn()                   write + read with millis() deadline
    Link.read_telemetry()         same, into float tel[64]
    Link.write_setting()          same
    TELEMETRY / SETTINGS tables   PROGMEM struct arrays

Wire format, from comm_ser.h:

    [0xFF]* [0xAA][0x55][CMD][ADDR][CNT][payload...][XOR]

    0xFF   optional preamble, COMM_TX_PREAMBLE of them. Ignored - receivers
           scan for the AA 55 pair. It exists to absorb a mis-framed first
           byte on a lazily-biased RS485 bus.
    CMD    1 READ_TEL  2 READ_SET  3 WRITE_SET  4 PING  0x7E NAK
           responses set bit 7
    XOR    over CMD, ADDR, CNT and every payload byte
    floats little-endian IEEE754

    Corrupt frames are DISCARDED SILENTLY by the drive - answering noise on a
    half-duplex bus would spam it. A NAK means the frame was well formed but
    the command was unknown.
"""
import struct
import time

try:
    import serial
except ImportError:                                     # pragma: no cover
    serial = None

# rev 31 FLASHED 2026-09-04: SET 66..72 = the nameplate (panel F40..F46),
#   engineering units on the wire (kW, V, Hz, A rms, pairs, rpm). F40
#   PLATE_RETUNE is a PASSWORD now - write 123, not 1, or nothing happens.
#   Writes are RAM until command('SAVE_SETTINGS'), like a keypad edit.
# rev 24 FLASHED 2026-09-02 07:4x: CMD_PANEL_LOCK 18 / CMD_PANEL_UNLOCK 19.
FW_MAGIC   = 0x4853341D          # "HS34" map rev 32: +SET 73/74 BUS_SHED_HI/LO (F49/F50),
                                 # +TEL 165/166 BUS_SHED / BUS_SHED_MIN. rev 23 was
                                 # +SET 62 TUNE_REST (panel F47);
                                 # TUNE_STS stage field shifted by TU_WAIT at 0
# N_TEL is a COUNT, not a last index, and it was 128 while the table already
# ran to index 128 - so read_telemetry() fetched 0..127 and CAP_INDEX was
# never actually read. 139 now covers the pre-start block as well.
N_TEL      = 167
N_SET      = 75
READ_TEL, READ_SET, WRITE_SET, PING, NAK = 0x01, 0x02, 0x03, 0x04, 0x7E
SYNC = b'\xAA\x55'


# ---------------------------------------------------------------- registers
# (index, name, unit, scale, group)
#   scale: DIVIDE the raw value by this for engineering units. Registers 0..31
#   of both banks are the drive's own uint16 tables, stored exactly as the
#   TM1638 panel shows them - F22..F31 really are 500..2000 for 0.5..2.0.
TELEMETRY = [
    # --- 0..13  stored ADC calibration offsets (raw counts) ---
    ( 0, "ADC_OFFS_VDC",    "cnt", 1,    "offsets"),
    ( 1, "ADC_OFFS_IDC",    "cnt", 1,    "offsets"),
    ( 2, "ADC_OFFS_VGA",    "cnt", 1,    "offsets"),
    ( 3, "ADC_OFFS_VGB",    "cnt", 1,    "offsets"),
    ( 4, "ADC_OFFS_VGC",    "cnt", 1,    "offsets"),
    ( 5, "ADC_OFFS_I_INVA", "cnt", 1,    "offsets"),
    ( 6, "ADC_OFFS_I_INVB", "cnt", 1,    "offsets"),
    ( 7, "ADC_OFFS_I_INVC", "cnt", 1,    "offsets"),
    ( 8, "ADC_OFFS_I_GRID_A","cnt",1,    "offsets"),
    ( 9, "ADC_OFFS_I_GRID_B","cnt",1,    "offsets"),
    (10, "ADC_OFFS_I_GRID_C","cnt",1,    "offsets"),
    (11, "ADC_OFFS_V_INVA", "cnt", 1,    "offsets"),
    (12, "ADC_OFFS_V_INVB", "cnt", 1,    "offsets"),
    (13, "ADC_OFFS_V_INVC", "cnt", 1,    "offsets"),
    # --- 14..31  panel measurement mirror (only fresh if the panel updated) ---
    (14, "MEAS_VDC",        "V",   1,    "panel"),
    (15, "MEAS_IDC",        "A",   10,   "panel"),
    (16, "MEAS_I_INV_A",    "A",   10,   "panel"),
    (17, "MEAS_I_INV_B",    "A",   10,   "panel"),
    (18, "MEAS_I_INV_C",    "A",   10,   "panel"),
    (19, "MEAS_V_GRID_A",   "V",   1,    "panel"),
    (20, "MEAS_V_GRID_B",   "V",   1,    "panel"),
    (21, "MEAS_V_GRID_C",   "V",   1,    "panel"),
    (22, "MEAS_I_INV_D",    "A",   1000, "panel"),
    (23, "MEAS_I_INV_Q",    "A",   1000, "panel"),
    (24, "MEAS_I_INV_ABS",  "A",   1000, "panel"),
    (25, "MEAS_PWR_IN",     "kW",  10,   "panel"),
    (26, "MEAS_PWR_OUT",    "kW",  10,   "panel"),
    (27, "MEAS_PF_IN",      "",    1000, "panel"),
    (28, "MEAS_PF_OUT",     "",    1000, "panel"),
    (29, "MEAS_TEMP",       "C",   10,   "panel"),
    (30, "TERMINALS_IN",    "bits",1,    "panel"),
    (31, "ANALOG_IN",       "cnt", 1,    "panel"),
    # --- 32..  live floats, already in engineering units ---
    (32, "VDC",             "V",   1, "live"),
    (33, "IDC",             "A",   1, "live"),
    (34, "PDC",             "W",   1, "live"),
    (35, "VG_A",            "V",   1, "live"),
    (36, "VG_B",            "V",   1, "live"),
    (37, "VG_C",            "V",   1, "live"),
    (38, "IINV_A",          "A",   1, "live"),
    (39, "IINV_B",          "A",   1, "live"),
    (40, "IINV_C",          "A",   1, "live"),
    (41, "STS",             "",    1, "live"),
    (42, "MODE",            "",    1, "live"),
    (43, "FAULT_FLAGS",     "",    1, "live"),
    (44, "FREQ",            "Hz",  1, "live"),
    (45, "SET_FREQ",        "Hz",  1, "live"),
    (46, "MOD_IDX",         "",    1, "live"),
    (47, "TEMP",            "C",   1, "live"),
    (48, "STOP_REASON",     "",    1, "live"),
    (49, "MOTOR_POWER",     "idx", 1, "live"),
    (50, "AC_V_SP",         "V",   1, "live"),
    (51, "STS_1PH",         "",    1, "live"),
    (52, "COM1_FRAMES",     "",    1, "link"),
    (53, "COM1_ERRORS",     "",    1, "link"),
    (54, "COM2_FRAMES",     "",    1, "link"),
    (55, "COM2_ERRORS",     "",    1, "link"),
    (56, "CPU_ISR_PCT",     "%",   1, "cpu"),
    (57, "CPU_IDLE_PCT",    "%",   1, "cpu"),
    (58, "CPU_ISR_US",      "us",  1, "cpu"),
    (59, "CPU_ISR_HZ",      "Hz",  1, "cpu"),
    (60, "UPTIME_S",        "s",   1, "cpu"),
    (61, "RUN_TIME_S",      "s",   1, "cpu"),
    (62, "TX_DROPPED",      "",    1, "link"),
    (63, "RX_RESTARTS",     "",    1, "link"),
    # --- lifetime, EEPROM-backed, survives power cycles ---
    (64, "TOTAL_RUN_H",     "h",   1, "lifetime"),
    (65, "TOTAL_KWH",       "kWh", 1, "lifetime"),
    (66, "START_COUNT",     "",    1, "lifetime"),
    (67, "RESET_COUNT",     "",    1, "lifetime"),
    (68, "FAULT_OC_CNT",    "",    1, "lifetime"),
    (69, "FAULT_OV_CNT",    "",    1, "lifetime"),
    (70, "FAULT_UV_CNT",    "",    1, "lifetime"),
    (71, "FAULT_OT_CNT",    "",    1, "lifetime"),
    (72, "WARRANTY_H",      "h",   1, "lifetime"),
    (73, "WARRANTY_LEFT",   "h",   1, "lifetime"),
    (74, "WARRANTY_FLAG",   "",    1, "lifetime"),
    (75, "PEAK_VDC",        "V",   1, "peaks"),
    (76, "PEAK_IDC",        "A",   1, "peaks"),
    (77, "PEAK_TEMP",       "C",   1, "peaks"),
    (78, "PEAK_KW",         "kW",  1, "peaks"),
    (79, "FAULT_TOTAL",     "",    1, "peaks"),
] + [t for n in range(8) for t in (
    (80+2*n, "FLOG%d_CODE" % n, "",  1, "faultlog"),
    (81+2*n, "FLOG%d_HOUR" % n, "h", 1, "faultlog"))] + [
    (96, "PURCHASE_DAY",   "d", 1, "warranty"),
    (97, "DATE_NOW",       "d", 1, "warranty"),
    (98, "WARRANTY_DAYS",  "d", 1, "warranty"),
    (99, "WARRANTY_DLEFT", "d", 1, "warranty"),
    (100, "BAUD_COM2",     "",  1, "port"),
    (101, "BAUD_COM1",     "",  1, "port"),
    (102, "BAUD_TRIAL_S",  "s", 1, "port"),
    (103, "PORT_HEALTH",   "",  1, "port"),

    # --- 104..119  sensorless FOC. Only live when the drive is running the
    # FOC ISR (lab8); in V/f mode these hold whatever the last FOC session
    # left, so gate any display on FOC_MODE together with STS. PAR_* are the
    # ACTIVE runtime machine parameters - after an auto-tune they are the
    # measured ones, so the log records what the drive actually used. ---
    (104, "FOC_WM_HAT",    "Hz", 1, "foc"),   # rotor speed estimate (MRAS)
    (105, "FOC_FSLIP",     "Hz", 1, "foc"),   # slip; stator = WM_HAT + FSLIP
    (106, "FOC_ID",        "A",  1, "foc"),   # d axis, peak
    (107, "FOC_IQ",        "A",  1, "foc"),   # q axis (torque), peak
    (108, "FOC_ID_REF",    "A",  1, "foc"),
    (109, "FOC_IQ_REF",    "A",  1, "foc"),   # railed at cap = torque limited
    (110, "FOC_PSIR",      "Wb", 1, "foc"),   # rotor flux, rated 0.975
    (111, "FOC_VDEM",      "V",  1, "foc"),   # pre-saturation voltage demand
    (112, "FOC_MODE",      "",   1, "foc"),   # 0 I-f, 1 blend, 2 sensorless
    (113, "FOC_TE",        "Nm", 1, "foc"),   # torque estimate
    (114, "FOC_PEST",      "W",  1, "foc"),   # 1.5(vd id + vq iq)
    (115, "FOC_TUNE_STS",  "",   1, "foc"),   # 0 tune pending, 1 ok, 3 failed
    (116, "FOC_PAR_RS",    "ohm",1, "foc"),
    (117, "FOC_PAR_RR",    "ohm",1, "foc"),
    (118, "FOC_PAR_LM",    "mH", 1, "foc"),
    (119, "FOC_PAR_SIGLS", "mH", 1, "foc"),
    # --- 120..121  instantaneous phase currents through the FOC intake
    # path, live with the drive stopped - inject DC through a sensor and
    # compare against a clamp meter. Zero here while real current flows is
    # the dead-readback failure that winds the tune into an OC. ---
    (120, "IU_INST",       "A",  1, "diag"),   # sensor A = phase U
    (121, "IW_INST",       "A",  1, "diag"),   # sensor B = phase W; V is reconstructed
    # --- 122..127 pre-allocated spares. Claiming one later is NOT a map
    # change: index and count are fixed, magic stays, only the name here
    # gets updated. Old masters see a zero register come alive. ---
    (122, "ISR_CNT",       "",   1, "diag"),
    (123, "ADC_A_RAW",     "",   1, "diag"),
    (124, "ADC_A_OFS",     "",   1, "diag"),
    (125, "ADC_B_RAW",     "",   1, "diag"),
    (126, "ADC_B_OFS",     "",   1, "diag"),
    (127, "CAP_STATE",     "",   1, "diag"),   # 0 idle 1 armed 2 running 3 full
    (128, "CAP_INDEX",     "",   1, "diag"),   # samples; ring: the wrap point
    # --- pre-start motor health check. Additive: nothing above moved, so the
    # magic does not change and an old master reading 0..128 is unaffected.
    # R_UV/VW/WU are LINE-TO-LINE (two windings each); R_U/V/W are those
    # solved for the individual phases, so a fault names the phase. SPREAD is
    # computed on the PAIRS - line-to-line dilutes, so a 20% winding fault
    # shows here as about 10%. ---
    (129, "PS_STATE",      "",   1, "prestart"),  # 6 = settling, 7 = pass, 8 = failed
    (130, "PS_FLAGS",      "",   1, "prestart"),  # see PS_FLAG_BITS below
    (131, "PS_LEAK_A",     "A",  1, "prestart"),  # worst zero-sequence current
    (132, "PS_R_UV",       "ohm",1, "prestart"),  # U-V pair (star mode: +A)
    (133, "PS_R_VW",       "ohm",1, "prestart"),  # V-W pair (star mode: +B)
    (134, "PS_R_WU",       "ohm",1, "prestart"),  # W-U pair (star mode: +C)
    (135, "PS_R_U",        "ohm",1, "prestart"),  # solved phase; 0 in star mode
    (136, "PS_R_V",        "ohm",1, "prestart"),
    (137, "PS_R_W",        "ohm",1, "prestart"),
    (138, "PS_SPREAD",     "",   1, "prestart"),  # fraction, trips over 0.08
    (139, "PS_LEAK_DC",    "A",  1, "prestart"),  # Idc: ALL THREE phases
    (140, "PS_OFS_PP",     "A",  1, "prestart"),  # null-to-null offset drift
    (141, "PS_VCODE",      "",   1, "prestart"),  # 4 bits/vector, see PS_VCODES
    (142, "PS_IDLE_UV",    "A",  1, "prestart"),  # sensor B during U-V, expect ~0
    (143, "PS_IDLE_VW",    "A",  1, "prestart"),  # sensor A during V-W, expect ~0
    (144, "PS_AB_RATIO",   "",   1, "prestart"),  # -ia/ic during W-U, expect 1.000
    (145, "FAULT_DETAIL",  "",   1, "live"),      # latched: WHICH protection fired
    (146, "PS_QUIET_MS",   "ms", 1, "prestart"),  # settling dwell actually taken
    (147, "CAP_VALID",     "",   1, "diag"),     # samples actually written
    (148, "CAP_SRC0",      "id", 1, "diag"),     # LATCHED source, ch0
    (149, "CAP_SRC1",      "id", 1, "diag"),
    (150, "CAP_SRC2",      "id", 1, "diag"),
    (151, "IDQ_PEAK",      "A",  1, "live"),      # peak |i_dq| this start
    (152, "MPPT_VOC",     "V",  1, "mppt"),      # 0 = capture rejected
    (153, "MPPT_VHOLD",   "V",  1, "mppt"),      # live climb hold level
    (154, "MPPT_VRATIO",  "",   1, "mppt"),
    (155, "TUNE_VDEAD",   "V",  1, "foc"),
    (156, "TUNE_L40",     "mH", 1, "foc"),
    (157, "TUNE_L100",    "mH", 1, "foc"),
    (158, "TUNE_L200",    "mH", 1, "foc"),
    # rev 25 - the EEPROM window. EE_DATA is whatever CMD_EE_READ8/16 last
    # fetched; EE_STAT is the EE_ST_* outcome of the last CMD_EE_*. CHECK
    # EE_STAT after every write - a refusal and a success look identical
    # otherwise, because nothing is echoed and the EEPROM is not read back.
    (159, "EE_DATA",      "",   0, "eep"),
    (160, "EE_STAT",      "",   0, "eep"),
    # rev 27 - who started this run, when, how long, and what it cost. These
    # describe the CURRENT run, or the LAST one once stopped: they freeze
    # together rather than clearing, so an idle drive still answers.
    # There is no clock in the drive and none is needed - RUN_AGE_S keeps
    # counting after the stop, so:  started_at = now - RUN_AGE_S.
    (161, "START_REASON", "",   0, "run"),
    (162, "RUN_SECONDS",  "s",  0, "run"),
    (163, "RUN_KWH",      "kWh", 3, "run"),
    (164, "RUN_AGE_S",    "s",  0, "run"),
    # rev 32 - the bus shed. BUS_SHED is the live factor on the FOC torque
    # current limit (1.0 healthy bus .. 0.10 floor); BUS_SHED_MIN is the
    # lowest since the start, reset at energise. A 16 s logger misses the
    # dip itself - the latch is what says a cloud came through.
    (165, "BUS_SHED",     "",   3, "mppt"),
    (166, "BUS_SHED_MIN", "",   3, "mppt"),
]

# TEL_PS_FLAGS bits - mirrors the PS_F_* defines in hs300_drive.h.
# Only LEAK, ASYM and OPEN refuse a start; the rest are warnings.
PS_FLAG_BITS = [
    (0x001, "SKIPPED",  "check disabled by PRESTART_EN - it did NOT run"),
    (0x002, "NO_MOTOR", "all three pairs open: nothing connected (warn)"),
    (0x004, "R_HIGH",   "symmetric but high vs stored Rs: cold/long cable (warn)"),
    (0x008, "LEAK",     "FAIL zero-sequence current: insulation to earth"),
    (0x010, "ASYM",     "FAIL winding spread over threshold"),
    (0x020, "OPEN",     "FAIL one or two phases open with the rest intact"),
    (0x040, "PHASE_U",  "  the open phase is U"),
    (0x080, "PHASE_V",  "  the open phase is V"),
    (0x100, "PHASE_W",  "  the open phase is W"),
    (0x200, "RAIL_UV",  "U-V never reached 16 A: slope biased HIGH"),
    (0x400, "RAIL_VW",  "V-W never reached 16 A: slope biased HIGH"),
    (0x800, "RAIL_WU",  "W-U never reached 16 A: slope biased HIGH"),
    (0x1000, "LEAK_DC",  "FAIL DC-link cross-check: with LEAK clear the leak is on V"),
    (0x2000, "OFS_DRIFT","WARN offset moved between dwells - leak figure unproven"),
    (0x4000, "OVERCUR",  "FAIL current ran away - NOT asymmetry, no measurements taken"),
    (0x8000, "QUIET_TMO","WARN injected DC had not decayed when the dwell timed out"),
]

# stop_reason codes the pre-start check publishes on TEL_STOP_REASON (48)
PRESTART_STOP_REASONS = {30: "INSUL_LEAK", 31: "WINDING_ASYM", 32: "PHASE_OPEN"}

# TEL_FAULT_DETAIL (145) - latched protection source. Only the estop path
# writes it and only a reset clears it. TEL_STOP_REASON (48) cannot be used
# for this: the panel stop writes 10 and CMD_STOP writes 11 straight into it,
# so any stop issued after a trip overwrites the code that said what tripped.
FAULT_DETAIL = {
    0: "no fault",
    2: "FAULT generic",
    3: "OC generic",
    4: "OVER VOLTAGE",
    5: "UNDER VOLTAGE",
    7: "OVER TEMPERATURE",
    10: "stopped from the panel",
    11: "stopped over the link",
    20: "OC dq ENVELOPE - id^2+iq^2 over (1.15*i_max)^2",
    21: "OC dq TRACKING - current loop lost authority",
    22: "OC RMS TIME-OVERCURRENT - the thermal layer",
    23: "OC INSTANTANEOUS per-phase",
    30: "PRESTART insulation leak",
    31: "PRESTART winding asymmetry",
    32: "PRESTART phase open",
}

# TEL_PS_VCODE: four bits per line-to-line vector - UV 0-3, VW 4-7, WU 8-11.
# A 0.000 in a result register cannot distinguish "never measured" from
# "measured as zero"; this can.
PS_VCODES = {
    0: "not run",
    1: "ok",
    2: "OPEN - first level never reached 4 A",
    3: "NO SLOPE - second level under 2 A above the first",
    4: "OUT OF RANGE - slope outside 0.05..5.0 ohm",
    5: "OVER-CURRENT ABORT - |i| exceeded 25 A",
    6: "RAILED - completed but never reached 16 A",
}


def ps_vcode_decode(v):
    """Split TEL_PS_VCODE into (UV, VW, WU) human-readable outcomes."""
    v = int(v)
    return {n: PS_VCODES.get((v >> (4 * i)) & 0xF, "?")
            for i, n in enumerate(("UV", "VW", "WU"))}


# (index, name, unit, scale, min, max, group)
# min/max mirror min_max_setting_vals[] in settings.c. The DRIVE clamps to
# these itself and the WRITE_SET reply echoes what it actually stored - always
# compare the echo against what you sent.
SETTINGS = [
    ( 0, "F00 VFD_POWER",           "idx", 1,      1,   21, "protection"),
    ( 1, "F01 OVER_CURRENT",        "A",   1,      1,  500, "protection"),
    ( 2, "F02 OVER_CURRENT_TIME",   "ms",  1,      1,10000, "protection"),
    ( 3, "F03 OVER_VOLTAGE",        "V",   1,    200,  800, "protection"),
    ( 4, "F04 OVER_VOLTAGE_TIME",   "ms",  1,      1,10000, "protection"),
    ( 5, "F05 OVER_TEMP",           "C",   1,     40,  100, "protection"),
    ( 6, "F06 OVER_TEMP_TIME",      "s",   1,      1,  100, "protection"),
    ( 7, "F07 AUTO_START_TIME",     "min", 1,      1,  200, "startup"),
    ( 8, "F08 FMIN",                "Hz",  1,      5,   50, "drive"),
    ( 9, "F09 FMAX",                "Hz",  1,      5,   50, "drive"),
    (10, "F10 ACC_FACTOR",          "",    1,      1,   20, "drive"),
    (11, "F11 DEC_FACTOR",          "",    1,      1,   20, "drive"),
    (12, "F12 MPPT_SENS_FMIN",      "",    1,      5,  100, "mppt"),
    (13, "F13 MPPT_SENS_FMAX",      "",    1,      5,  100, "mppt"),
    (14, "F14 MPPT_CORR_FMIN",      "",    1,      5,  100, "mppt"),
    (15, "F15 MPPT_CORR_FMAX",      "",    1,      5,  100, "mppt"),
    (16, "F16 GRID_MIN_VOLTAGE",    "V",   1,    100,  500, "grid"),
    (17, "F17 MPPT_START_DIFF_F",   "Hz",  1,     15,   40, "mppt"),
    (18, "F18 GRID_MAX_CURRENT",    "A",   1,      1,  500, "grid"),
    (19, "F19 GRID_AUTO_START",     "",    1,      0,    1, "grid"),
    (20, "F20 GRID_AUTOSTART_TIME", "s",   1,      1, 1000, "grid"),
    (21, "F21 GRID_MIN_FMAX_V",     "V",   1,    150,  500, "grid"),
    (22, "F22 CF_VDC",              "x",   1000, 500, 2000, "calibration"),
    (23, "F23 CF_IDC",              "x",   1000, 500, 2000, "calibration"),
    (24, "F24 CF_VAC_IN_R",         "x",   1000, 500, 2000, "calibration"),
    (25, "F25 CF_VAC_IN_S",         "x",   1000, 500, 2000, "calibration"),
    (26, "F26 CF_VAC_IN_T",         "x",   1000, 500, 2000, "calibration"),
    (27, "F27 CF_VAC_220_OUT",      "x",   1000, 500, 2000, "calibration"),
    (28, "F28 CF_IAC_OUT_R",        "x",   1000, 500, 2000, "calibration"),
    (29, "F29 CF_IAC_OUT_S",        "x",   1000, 500, 2000, "calibration"),
    (30, "F30 CF_IAC_OUT_T",        "x",   1000, 500, 2000, "calibration"),
    (31, "F31 CF_TEMPERATURE",      "x",   1000, 500, 2000, "calibration"),
    (32, "CMD",                     "code",1,      0,   12, "runtime"),
    (33, "FREQ_SP",                 "Hz",  1,      0,   50, "runtime"),
    (34, "MODE",                    "",    1,      0,    2, "runtime"),
    (35, "AC_VOLT_SP",              "V",   1,      0,  500, "runtime"),
    (36, "MOD_IDX",                 "",    1,      0,    1, "runtime"),
    (37, "FAN_PWM",                 "%",   1,      0,  100, "runtime"),
    # 38 and 39 are claimed. They were still generated as SPARE0/SPARE1 below
    # after the capture buffer went in, so the agent showed "SPARE0" for the
    # capture control register - a naming lag, not a wire mismatch.
    (38, "CAP_CTRL",                "code",1,      0,  255, "runtime"),
    (39, "PRESTART_EN",             "",    1,      0,    1, "runtime"),
    # Zero-sequence trip level. Set it from TEL_PS_LEAK_A (131) on a healthy
    # machine - 3 to 5x that reading. Raising it raises the detection floor in
    # proportion; see PRESTART_CHECK_DESIGN.md.
    (40, "PS_ZS_TRIP",              "A",   1,      0,   25, "prestart"),
    (41, "PS_SPREAD_MAX",           "",    1,      0,    1, "prestart"),
    (42, "CAP_DIV",                "",    1,      1, 1000, "capture"),
    (43, "CAP_SRC0",               "id",  1,      0,   28, "capture"),
    (44, "CAP_SRC1",               "id",  1,      0,   28, "capture"),
    (45, "CAP_SRC2",               "id",  1,      0,   28, "capture"),
    (46, "OC_TRK_A",                "A",   1,      1,  200, "protection"),
    (47, "OC_ENV_A",                "A",   1,     10,  300, "protection"),
] + [
    (48, "WARRANTY_H",     "h", 1, 0, 65535, "warranty"),
    (49, "WARRANTY_DAYS",  "d", 1, 0, 65535, "warranty"),
    (50, "PURCHASE_DAY",   "d", 1, 0, 65535, "warranty"),
    (51, "DATE_NOW",       "d", 1, 0, 65535, "warranty"),
    (52, "BAUD_COM2", "ix", 1, 0, 6, "port"),
    (53, "BAUD_COM1", "ix", 1, 0, 6, "port"),
    (54, "START_FREQ", "Hz", 1, 0.5, 9.5, "drive"),
    (55, "MPPT_VOC_FRAC", "", 1, 0.30, 0.95, "mppt"),
    (56, "FOC_RS",                  "ohm", 1,      0,    5, "machine"),
    (57, "FOC_RR",                  "ohm", 1,      0,    2, "machine"),
    (58, "FOC_LM",                  "mH",  1,      5,  200, "machine"),
    (59, "FOC_LLS",                 "mH",  1,      0,   30, "machine"),
    (60, "FOC_LLR",                 "mH",  1,      0,   30, "machine"),
    (61, "MPPT_VOC_BACK", "",    1,   0.20, 0.90, "mppt"),
    (62, "TUNE_REST",     "s",   1,   0.0,  60.0, "tune"),   # panel F47
    # rev 25 - address/data mailbox for CMD_EE_*. RAM only, never committed.
    # ADDR is a BYTE address; a 16-bit access needs it EVEN.
    (63, "EE_ADDR",       "",    0,   0.0,  8191.0,  "eep"),
    (64, "EE_DATA",       "",    0,   0.0,  65535.0, "eep"),
    # rev 27 - master switch for the F07 unattended start. Was a dead
    # variable for a long time; the only gate was F07 != 0, so turning
    # auto-start off meant destroying the delay you wanted to keep.
    # RAM ONLY - readSettings() re-arms it to 1, like PRESTART_EN.
    (65, "AUTOSTART_EN",  "",    0,   0.0,  1.0,     "run"),
    (66, "PLATE_RETUNE",  "",    0,   0.0, 9999.0,  "plate"),
    (67, "PLATE_KW",      "kW",  1,   0.1,  200.0,  "plate"),
    (68, "PLATE_V_LL",    "V",   0, 100.0, 1000.0,  "plate"),
    (69, "PLATE_F_HZ",    "Hz",  0,  10.0,  200.0,  "plate"),
    (70, "PLATE_I_RMS",   "A",   1,   1.0, 1000.0,  "plate"),
    (71, "PLATE_PP",      "",    0,   1.0,   12.0,  "plate"),
    (72, "PLATE_RPM",     "rpm", 0, 100.0, 6000.0,  "plate"),
    # rev 32 - the bus shed lines, fractions of the bus at energise (Voc on
    # the array). Panel F49/F50, x1000 there. HI may exceed 1.0 on purpose:
    # that is how the shed is exercised on a battery bus that will not sag.
    (73, "BUS_SHED_HI",   "",    3,   0.30,   2.00,  "mppt"),
    (74, "BUS_SHED_LO",   "",    3,   0.20,   1.50,  "mppt"),
]

COMMANDS = {
    "START": 1, "STOP": 2, "RESET_FAULT": 3, "MCU_REBOOT": 4, "CLR_STATS": 5,
    "START_1PH": 7, "STOP_1PH": 8, "DRV_RESET": 9,
    "SAVE_SETTINGS": 10, "LOAD_DEFAULTS": 11, "RELOAD_EEPROM": 12,
    "CLR_PEAKS": 13, "ADC_ZERO": 14, "OTA_ENTER": 15,
    "FOC_RETUNE": 16, "FOC_DEFAULTS": 17,
    # rev 24. PANEL_LOCK disables the front keypad for 120 s and must be
    # RESENT while a test runs - it counts down, so a controller that dies
    # releases the panel instead of stranding the drive.
    "PANEL_LOCK": 18, "PANEL_UNLOCK": 19,
    # rev 25 - read/write one byte or one 16-bit word anywhere in the EEPROM,
    # so a single calibration constant can be set without disturbing its
    # neighbours. ADC_ZERO above is all-or-nothing and that is why this
    # exists. APPLY_OFFS pushes the stored D-block into the working offsets;
    # without it a written offset does nothing until the next boot.
    "EE_READ16": 20, "EE_WRITE16": 21, "EE_READ8": 22, "EE_WRITE8": 23,
    "EE_APPLY_OFFS": 24,
}

# STATUS enum, anpc_inv.h. anpcInvState[] in main.c prints the same order but
# labels index 2 "FL_DV" and index 6 "FL_UW"; the enum calls them FAULT and
# FAULT_UV_WAIT. The enum is authoritative - UV_WAIT is the RECOVERABLE state
# SetFreqRamp() clears once Vdc climbs back over 250 V, and reading it as
# "under-frequency" would send you looking in the wrong place entirely.
STATE_NAMES = ["OFF", "ON", "FAULT", "FAULT_OC", "FAULT_OV",
               "FAULT_UV", "FAULT_UV_WAIT", "FAULT_OT"]

# OPERATING_MODE enum, anpc_inv.h. NOT the order you would guess:
#     MODE_MANUAL = 0,  MODE_MPPT = 1,  MODE_DCBUS = 2
# The panel's KEY_SETUP does `if (++inverterMode == 2) inverterMode = 0;`
# so from the keypad it only toggles MANUAL <-> MPPT. DCBUS is reachable over
# the wire and only means anything on a board built for grid input.
MODE_NAMES  = {0: "MANUAL", 1: "MPPT", 2: "DCBUS"}

TEL_BY_NAME = {r[1]: r[0] for r in TELEMETRY}
SET_BY_NAME = {r[1]: r[0] for r in SETTINGS}
SET_LIMITS  = {r[0]: (r[4], r[5]) for r in SETTINGS}
SET_SCALE   = {r[0]: r[3] for r in SETTINGS}
TEL_SCALE   = {r[0]: r[3] for r in TELEMETRY}

SET_CMD = SET_BY_NAME["CMD"]
SET_CAP_CTRL   = SET_BY_NAME["CAP_CTRL"]
SET_CAP_DIV    = SET_BY_NAME["CAP_DIV"]
SET_CAP_SRC0   = SET_BY_NAME["CAP_SRC0"]
TEL_CAP_STATE  = TEL_BY_NAME["CAP_STATE"]
TEL_CAP_INDEX  = TEL_BY_NAME["CAP_INDEX"]
TEL_CAP_VALID  = TEL_BY_NAME["CAP_VALID"]

# Baud is written as an INDEX into this table, never as a rate. A typo cannot
# ask for 19201 or 0, and the drive reverts on its own if nobody talks at the
# new rate within 30 s - so a wrong setting costs half a minute, not a trip
# with the programmer.
BAUD_TABLE = [2400, 4800, 9600, 19200, 38400, 57600, 115200]

def baud_index(baud):
    return BAUD_TABLE.index(baud)

# ---- dates on this protocol are DAYS SINCE 2026-01-01, never YYYYMMDD ----
# Every register is a float32, exact only to 16,777,216. 20260727 is past
# that, so a YYYYMMDD date would arrive off by a day. u16 days runs to 2205.
import datetime
DAY_EPOCH = datetime.date(2026, 1, 1)

def to_day(d):
    """datetime.date (or ISO string) -> days since 2000-01-01"""
    if isinstance(d, str):
        d = datetime.date.fromisoformat(d)
    return (d - DAY_EPOCH).days

def from_day(n):
    """days since 2000-01-01 -> datetime.date"""
    return DAY_EPOCH + datetime.timedelta(days=int(n))

def today_day():
    return to_day(datetime.date.today())


def state_name(v):
    i = int(v + 0.5)
    return STATE_NAMES[i] if 0 <= i < len(STATE_NAMES) else "?%d" % i


# ------------------------------------------------------------------ profiles
# The two ports need different timing, and it is not cosmetic. RS485 is half
# duplex: the drive holds DE through its reply and releases it on the USART TC
# flag, then the adapter has to turn its own driver around.
PROFILES = {
    "rs485": dict(gap=0.020, timeout=0.50, post_tx=0.002),
    "ttl":   dict(gap=0.003, timeout=0.30, post_tx=0.000),
}


class LinkError(Exception):
    pass


class CaptureNotFrozen(Exception):
    """The ring was still running when it was read."""


class Link:
    # Set to True (or pass --debug to the agent) and every FAILED transaction
    # prints what went out and what came back.
    debug = False
    _dbg_left = 8

    """One serial port speaking the HS300 protocol. Not thread-safe on its own
    - hs300_agent.py serialises access with a lock, exactly as a single ESP32
    task would."""

    def __init__(self, port, baud=115200, mode="rs485", retries=3):
        self.port_name = port
        self.baud = baud
        self.prof = PROFILES[mode]
        self.retries = retries
        self.ser = None
        self.stats = dict(txn=0, retry=0, fail=0, bad_crc=0)

    # -- lifecycle ---------------------------------------------------------
    def open(self):
        if serial is None:
            raise LinkError("pyserial missing:  pip install pyserial")
        s = serial.Serial()
        # SHORT fixed read timeout, set ONCE. _recv() enforces the real
        # per-transaction budget with a deadline - it must never assign
        # s.timeout again, see the note there.
        s.port, s.baudrate, s.timeout = self.port_name, self.baud, 0.02
        s.rtscts = s.dsrdtr = s.xonxoff = False
        # DTR/RTS must stay LOW. pyserial raises both on open; on most
        # USB-RS485 adapters RTS is the driver enable, and an asserted RTS
        # parks the adapter transmitting so the drive's reply never arrives.
        try: s.dtr = s.rts = False
        except Exception: pass
        s.open()
        try: s.dtr = s.rts = False
        except Exception: pass
        time.sleep(0.2)
        s.reset_input_buffer()
        self.ser = s
        return self

    def close(self):
        if self.ser:
            self.ser.close()
            self.ser = None

    # -- framing -----------------------------------------------------------
    # ---- CRC16-CCITT, poly 0x1021, init 0xFFFF -------------------------
    # Two check bytes on the wire, LOW BYTE FIRST, computed over
    # CMD..payload. NOT the Modbus CRC in modbus_rtu.py - that one is the
    # reflected 0xA001 algorithm and gives different values. Check constant:
    # crc16("123456789") == 0x29B1.
    @staticmethod
    def _crc16(data):
        crc = 0xFFFF
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 \
                      else (crc << 1) & 0xFFFF
        return crc

    @staticmethod
    def _xor(b):
        x = 0
        for c in b:
            x ^= c
        return x

    @classmethod
    def _frame(cls, cmd, addr=0, cnt=1, values=None):
        body = bytearray([cmd, addr, cnt])
        for v in (values or []):
            body += struct.pack('<f', float(v))
        c = cls._crc16(bytes(body))
        return SYNC + bytes(body) + bytes([c & 0xFF, c >> 8])

    def _recv(self, timeout, keep=None):
        """Collect bytes, then parse whole frames out of the buffer.

        Never assume a read length - pyserial's read(n) can return short, and
        parsing incrementally leaves a tail in the OS buffer that the next
        attempt mis-frames. Re-scanning the accumulated buffer also handles a
        leading 0xFF preamble, an adapter echo, and trailing junk for free."""
        p = self.ser
        # DO NOT TOUCH p.timeout HERE.
        #
        # pyserial's timeout setter calls _reconfigure_port(), which on Windows
        # calls SetCommState - and that DISCARDS THE DRIVER'S RECEIVE BUFFER.
        # Setting it inside the receive loop therefore throws away part of the
        # reply that is already in flight, and you get a frame with bytes
        # missing from the middle, a different amount lost each attempt, and
        # the full timeout consumed waiting for data that was deleted locally.
        #
        # The port is opened once with a short fixed timeout; the caller's
        # budget is enforced here in software instead.
        deadline = time.time() + timeout
        buf = bytearray()
        while time.time() < deadline:
            n = p.in_waiting
            chunk = p.read(n if n else 1)
            if chunk:
                buf += chunk
                if keep is not None:
                    keep += chunk
            i = 0
            while True:
                j = buf.find(SYNC, i)
                if j < 0 or len(buf) < j + 6:
                    break
                cmd, addr, cnt = buf[j+2], buf[j+3], buf[j+4]
                npay = 0 if cmd == NAK else 4 * cnt
                end = j + 5 + npay + 2              # two CRC bytes now
                if len(buf) < end:
                    break
                pay = bytes(buf[j+5:j+5+npay])
                if not (cmd & 0x80) and cmd != NAK:
                    i = j + 2                       # our own echo, skip it
                    continue
                c = self._crc16(bytes([cmd, addr, cnt]) + pay)
                if buf[end-2] != (c & 0xFF) or buf[end-1] != (c >> 8):
                    self.stats["bad_crc"] += 1
                    i = j + 2
                    continue
                return cmd, addr, cnt, pay
        return None

    def _txn(self, req, timeout=None):
        if self.ser is None:
            raise LinkError("port not open")
        timeout = timeout or self.prof["timeout"]
        self.stats["txn"] += 1
        tries = []                              # per-attempt, for the dump
        for attempt in range(self.retries):
            time.sleep(self.prof["gap"])
            self.ser.reset_input_buffer()
            self.ser.write(req)
            if self.prof["post_tx"]:
                self.ser.flush()
                time.sleep(self.prof["post_tx"])
            raw = bytearray() if self.debug else None
            t0 = time.time()
            r = self._recv(timeout, raw)
            if self.debug:
                tries.append((raw, (time.time() - t0) * 1000))
            if r is not None:
                if attempt:
                    self.stats["retry"] += attempt
                return r
        self.stats["fail"] += 1

        # Dump the first few failures. test_link.py and this module drive the
        # same wire, so when one works and the other does not, the difference
        # is in the bytes - and nothing else will show it.
        if self.debug and Link._dbg_left > 0:
            Link._dbg_left -= 1
            cmd, addr, cnt = req[2], req[3], req[4]
            want = 1 + 5 + 4*cnt + 1        # preamble + header + payload + xor
            print("\n  [debug] FAILED  sent %s   expecting %d bytes back"
                  % (req.hex(" ").upper(), want))
            for k, (raw, ms) in enumerate(tries):
                short = want - len(raw)
                print("  [debug]   try %d: got %3d/%d B in %5.1f ms   %s"
                      % (k+1, len(raw), want, ms,
                         "COMPLETE" if short <= 0 else "%d SHORT" % short))
                if raw:
                    print("  [debug]     head %s" % bytes(raw[:8]).hex(" ").upper())
                    print("  [debug]     tail %s" % bytes(raw[-8:]).hex(" ").upper())
            print("  [debug]   bad_crc total: %d" % self.stats.get("bad_crc", 0))
        return None

    @staticmethod
    def _floats(pay):
        return [struct.unpack_from('<f', pay, 4*i)[0] for i in range(len(pay)//4)]

    # -- operations --------------------------------------------------------
    def ping(self):
        """Returns the firmware magic, or None. ALWAYS check it before writing
        anything: a mismatch means the register map moved and every index in
        this file is wrong."""
        r = self._txn(self._frame(PING, 0, 1))
        if not r or r[0] != (PING | 0x80):
            return None
        return struct.unpack('<I', r[3])[0]

    def read_telemetry(self, addr=0, cnt=N_TEL):
        r = self._txn(self._frame(READ_TEL, addr, cnt), timeout=1.0)
        if not r or r[2] != cnt:
            return None
        return self._floats(r[3])

    def read_settings(self, addr=0, cnt=N_SET):
        r = self._txn(self._frame(READ_SET, addr, cnt), timeout=1.0)
        if not r or r[2] != cnt:
            return None
        return self._floats(r[3])

    def write_settings(self, addr, values):
        """Contiguous multi-register write. Returns the drive's echo, which is
        what it ACTUALLY STORED after clamping - not what you sent."""
        r = self._txn(self._frame(WRITE_SET, addr, len(values), values))
        if not r or r[2] != len(values):
            return None
        return self._floats(r[3])

    def write_setting(self, idx, value):
        e = self.write_settings(idx, [value])
        return e[0] if e else None

    # -- capture readout ---------------------------------------------------
    def read_capture_channel(self, chan, src_id=None, samples=None):
        """One capture channel, oldest sample first, in engineering units.

        ADDR is the index WITHIN the channel, so a read cannot stream across
        channel boundaries: ceil(256/60) = 5 frames per channel, 15 for all
        three. Selecting the channel is a WRITE to SET_CAP_CTRL = 10 + n.
        """
        samples = samples or CAP_SAMPLES
        if self.write_setting(SET_CAP_CTRL, 10 + chan) is None:
            return None
        out = []
        while len(out) < samples:
            n = min(CAP_RD_MAX, samples - len(out))
            r = self._txn(self._frame(READ_CAP, len(out), n), timeout=1.0)
            # CHECK THE ECHOED ADDR, not just the count. A reply that carries
            # the right number of samples from the wrong offset would be
            # spliced into the record silently and read as data.
            if not r or r[2] != n or r[1] != len(out):
                return None
            out.extend(self._floats(r[3]))
        if src_id is None:
            return out
        return [cap_unscale(src_id, v) for v in out]

    def read_capture(self, rearm=3):
        """All three channels plus the metadata needed to read them.

        Returns a dict with 'wrap', 'div', 'dt', 'chans' and 'names'.

        THE RING IS UNWRAPPED HERE. In ring mode CAP_INDEX is the WRAP POINT,
        not a count: sample [wrap] is the OLDEST and [wrap-1] the newest, i.e.
        the instant of the freeze. Rotating by wrap puts the trip at the END
        of the returned list, which is what a fault record should look like.
        """
        # FREEZE FIRST. A full readout is 15 frames; at 9600 baud one 60-sample
        # frame is ~517 ms and the whole thing ~7.8 s, while a ring at DIV 1
        # turns the buffer over every 51.2 ms - TEN TIMES PER FRAME. Reading a
        # running ring cannot produce a coherent record: each frame comes from
        # a different revolution, and the seam between them looks like a signal
        # that stopped. CAP_CTRL 4 stops it where it is and does not re-arm.
        # AND VERIFY IT TOOK. Writing 4 and carrying on was not enough: on a
        # firmware where cap_apply_ctrl() had no case for it, the write fell
        # through to cap_arm() and RE-ARMED the ring, so the readout that
        # followed was of a buffer that had just been restarted. Poll for
        # CAP_FULL and say so plainly if it never arrives.
        self.write_setting(SET_CAP_CTRL, 4.0)
        state = -1
        for _ in range(10):
            time.sleep(0.05)
            t = self.read_telemetry(TEL_CAP_STATE, 1)
            if t:
                state = int(round(t[0]))
                if state == 3:
                    break

        tel = self.read_telemetry(0, N_TEL)
        if tel is None:
            return None
        state = int(round(tel[TEL_CAP_STATE]))
        if state != 3:
            # Do not read a moving buffer and hand back something that looks
            # like a record. 15 frames take ~7.8 s; the ring turns over every
            # 51.2 ms at DIV 1.
            raise CaptureNotFrozen(
                "CAP_CTRL=4 did not freeze the ring - state is still %d. The "
                "firmware may not implement CAP_CTRL_FREEZE; reading it now "
                "would splice ~%d separate revolutions into one file."
                % (state, 8000 // 51))
        wrap = int(round(tel[TEL_CAP_INDEX]))
        # TRUNCATE TO WHAT WAS ACTUALLY WRITTEN. The buffer is .bss, so the
        # unwritten tail is zeros - and zeros do not READ as zero: raw 0 on the
        # id/iq sources unscales to exactly -65.536 A, which looks like a
        # measurement. TEL_CAP_INDEX cannot answer this, it is a cursor.
        valid = int(round(tel[TEL_CAP_VALID]))
        valid = max(0, min(valid, CAP_SAMPLES))
        st = self.read_settings(0, N_SET)
        if st is None:
            return None
        div = max(1, int(round(st[SET_CAP_DIV]))) if SET_CAP_DIV < N_SET else 1
        src = [int(round(st[SET_CAP_SRC0 + i])) for i in range(3)]

        chans, names = [], []
        for i in range(3):
            c = self.read_capture_channel(i, src[i], samples=valid or 1)
            if c is None:
                return None
            c = c[:valid]
            # Rotate ONLY when the buffer wrapped. The firmware sets wrap to 0
            # when it did not, so this is belt and braces - rotating a partial
            # record would put the unwritten region in the MIDDLE, which is
            # worse than at the end because it stops looking like a gap.
            if valid == CAP_SAMPLES and 0 < wrap < len(c):
                c = c[wrap:] + c[:wrap]
            chans.append(c)
            names.append(CAP_SOURCES.get(src[i], ("?",))[0])
        import math as _m
        holes = sum(1 for c in chans for v in c if _m.isnan(v))

        # RE-ARM, so the recorder goes back to watching. Freezing to read is
        # necessary - a readout is ~7.8 s while a ring at DIV 1 turns over
        # every 51.2 ms - but a ring left frozen never records again, and a
        # fault recorder that only catches the first fault is not a fault
        # recorder. Re-arming REPAINTS AND RESTARTS the buffer, so it must
        # happen strictly after every channel has been read.
        #
        # rearm is the mode to go back to, 3 = ring/freeze-on-estop, which is
        # the fault-recorder mode and the power-on default. Pass rearm=None to
        # leave it frozen - for a second look at the same record.
        #
        # It cannot be read back from SET_CAP_CTRL: the freeze write already
        # overwrote that register with 4, so the previous mode is gone by the
        # time we get here. Hence an explicit argument, not a guess.
        rearmed = False
        if rearm is not None:
            self.write_setting(SET_CAP_CTRL, float(rearm))
            time.sleep(0.05)
            t = self.read_telemetry(TEL_CAP_STATE, 1)
            # 1 = ARMED (waiting for a trigger), 2 = RUNNING (ring turning)
            rearmed = bool(t) and int(round(t[0])) in (1, 2)

        return {"state": state, "wrap": wrap, "div": div, "valid": valid,
                "holes": holes, "rearmed": rearmed, "rearm_mode": rearm,
                "frozen": state == 3, "full": valid == CAP_SAMPLES,
                "dt": 200e-6 * div, "srcs": src, "names": names,
                "chans": chans}


    def command(self, name_or_code):
        code = COMMANDS[name_or_code] if isinstance(name_or_code, str) else int(name_or_code)
        return self.write_setting(SET_CMD, float(code))


# ---------------------------------------------------------------------------
# MODULE-LEVEL HELPERS GO HERE, BELOW THE CLASS - NOT BETWEEN ITS METHODS.
# cap_to_csv was once inserted between read_capture() and command(). At column
# zero it ENDED THE CLASS BODY, so command() became an unreachable nested
# function inside it and Link.command silently ceased to exist. No syntax
# error, no import error - just an AttributeError in every tool that used it,
# which is all of them: hs300_ota.py, foc_repeat.py, foc_sweep.py,
# foc_first_run.py, solar_day.py, battery_day.py and hs300_agent.py.
# ---------------------------------------------------------------------------
class CaptureNotFrozen(Exception):
    """The ring was still running when it was read."""


def cap_to_csv(cap, path, allow_live=False):
    """Write a capture to CSV with a real time axis. t = 0 is the FREEZE, so
    the pre-trip history is negative - which is how a fault record reads.

    REFUSES A LIVE RING unless allow_live. A record read while the buffer is
    still being written is not a record of anything: the samples span an
    arbitrary moment, and the row at t = 0 is wherever the cursor happened to
    be. Writing it to a file that looks exactly like a fault record is how a
    diagnostic tool starts lying. Pass allow_live=True to take it anyway - it
    is still truncated to the valid count, so nothing unwritten is exported.
    """
    if not cap.get("frozen") and not allow_live:
        raise CaptureNotFrozen(
            "ring is still running (state %d) - nothing was frozen, so this "
            "is not a trip record. Use allow_live=True to export it anyway."
            % cap.get("state", -1))
    n = len(cap["chans"][0])
    if n == 0:
        raise ValueError("capture contains 0 valid samples - nothing to write")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("t_s," + ",".join(cap["names"]) + "\n")
        for i in range(n):
            t = (i - n + 1) * cap["dt"]
            f.write("%.6f," % t +
                    ",".join("%.6g" % cap["chans"][c][i] for c in range(3)) + "\n")
    return path

# --- CAP_SOURCES BEGIN (generated by tools/gen_cap_sources.ps1) ---
# DO NOT HAND-EDIT. The definition lives in CAP_SRC_TABLE in
# drive/hs300_capture.h; re-run the generator and commit both.
#   value = (stored - offset) / scale
CAP_SAMPLES = 256   # drive/hs300_capture.h
CAP_RD_MAX  = 60    # comm/comm_ser.h, samples per READ_CAP frame

CAP_SOURCES = {
      0: ("none", 1, 0),
      1: ("wm_hat_hz", 500, 0),
      2: ("iq", 500, 32768),
      3: ("id", 500, 32768),
      4: ("psi_r", 10000, 0),
      5: ("v_demand", 100, 0),
      6: ("f_slip", 1000, 32768),
      7: ("te_est", 100, 32768),
      8: ("p_est_w", 1, 0),
      9: ("iInvReadAdcA", 1, 0),
     10: ("iInvReadAdcB", 1, 0),
     11: ("vDcReadAdc", 1, 0),
     12: ("vDcInst", 100, 0),
     13: ("duty_a", 10000, 0),
     14: ("inverterFreq", 100, 0),
     15: ("drive_state", 1, 0),
     16: ("tempInt", 100, 0),
     17: ("iDcReadAdc", 1, 0),
     18: ("idc_units", 100, 0),
     19: ("id_ref", 500, 32768),
     20: ("iq_ref", 500, 32768),
     21: ("i_trk_err", 500, 0),
     22: ("i_dq_mag", 500, 0),
     23: ("mppt_dp_dv", 10, 32768),
     24: ("mppt_dv", 100, 32768),
     25: ("mppt_dp", 1, 32768),
     26: ("set_freq", 100, 0),
     27: ("vdc_units", 50, 0),
     28: ("iq_shed", 10000, 0),
}
# --- CAP_SOURCES END ---

# --- capture readout (CMD 5 READ_CAP) --------------------------------------
# ADDR is the sample index WITHIN the channel selected by writing
# SET_CAP_CTRL = 10 + n. CNT is samples, capped at 60 by the frame size -
# the same ceiling read_telemetry works to. Unpack is identical.
READ_CAP = 0x05


CAP_UNWRITTEN = 0xFFFF   # drive/hs300_capture.h - painted in at arm time


def cap_unscale(src_id, raw):
    """stored -> engineering units, using the generated CAP_SOURCES table.

    An unwritten slot comes back as NaN, never as a number. The firmware
    paints CAP_UNWRITTEN into every slot at arm, so a hole in the record is
    visible as a hole - on a raw ADC source a zero is a legal reading and
    cannot be told from empty memory any other way.
    """
    if int(raw) == CAP_UNWRITTEN:
        return float("nan")
    _name, scale, offset = CAP_SOURCES.get(src_id, ("?", 1.0, 0.0))
    return (raw - offset) / scale


# ---------------------------------------------------------------------------
# THE EEPROM WINDOW (firmware rev 25). Module-level, BELOW the Link class -
# a helper at column zero between two methods ends the class body and every
# method after it becomes unreachable. That has happened in this file before.
# ---------------------------------------------------------------------------

EE_ADDR_MAX = 8191          # AT24C64, 64 kbit = 8192 bytes

# Byte addresses. Mirrors the map beside CMD_EE_* in comm/comm_ser.h.
EE_D_BLOCK   = (0x000, 0x040)   # D00..D31; D00..D13 are the ADC offsets
EE_F_LEGACY  = (0x040, 0x080)   # F00..F31   - firmware REFUSES writes
EE_LIFETIME  = (0x080, 0x180)   # lifetime A/B, lifetime2 A/B
EE_FOC_STORE = (0x180, 0x200)   # FOC store A/B
EE_F_EXT     = (0x200, 0x226)   # F32..F50   - firmware REFUSES writes
EE_FREE      = (0x226, 0x2000)

EE_ST = {0: "OK", 1: "RANGE", 2: "ALIGN", 3: "IO",
         4: "PROTECTED (settings mirror - use write_setting)",
         5: "BUSY (drive is running)"}

# D-block index -> name, from READ_ONLY_VALS in Core/display/settings.h.
# EEPROM byte address is 2 * index. Only 0..13 are calibration; D14..D31 are
# live readings the firmware rewrites on its own.
EE_ADC_OFFSETS = ["VDC", "IDC", "VGA", "VGB", "VGC",
                  "I_INVA", "I_INVB", "I_INVC",
                  "I_GRID_A", "I_GRID_B", "I_GRID_C",
                  "V_INVA", "V_INVB", "V_INVC"]


class EepromError(RuntimeError):
    pass


def _ee_status(link):
    st = int(round(link.read_telemetry(TEL_BY_NAME["EE_STAT"], 1)[0]))
    return st, EE_ST.get(st, "unknown %d" % st)


def ee_read(link, addr, width=16):
    """Return the byte or 16-bit word at EEPROM byte address addr."""
    if width not in (8, 16):
        raise ValueError("width must be 8 or 16")
    link.write_setting(SET_BY_NAME["EE_ADDR"], addr)
    link.command("EE_READ16" if width == 16 else "EE_READ8")
    st, name = _ee_status(link)
    if st:
        raise EepromError("read 0x%04X: %s" % (addr, name))
    return int(round(link.read_telemetry(TEL_BY_NAME["EE_DATA"], 1)[0]))


def ee_write(link, addr, value, width=16):
    """Store value at EEPROM byte address addr, then read it back to confirm.

    The firmware refuses writes into the two settings mirrors and refuses any
    write while the drive is running; both come back as EepromError rather
    than silently doing nothing.
    """
    if width not in (8, 16):
        raise ValueError("width must be 8 or 16")
    link.write_setting(SET_BY_NAME["EE_ADDR"], addr)
    link.write_setting(SET_BY_NAME["EE_DATA"], value)
    link.command("EE_WRITE16" if width == 16 else "EE_WRITE8")
    st, name = _ee_status(link)
    if st:
        raise EepromError("write 0x%04X = %d: %s" % (addr, value, name))
    got = ee_read(link, addr, width)
    if got != value:
        raise EepromError("write 0x%04X: wrote %d, read back %d"
                          % (addr, value, got))
    return got


def ee_apply_adc_offsets(link):
    """Push the stored D-block into the working ADC offsets, now.

    Without this a written offset sits in EEPROM doing nothing until the next
    boot and looks like a failed write. Each channel is re-validated on the
    way through and an out-of-range value is REPLACED by its compile-time
    default, so read the offset back afterwards instead of assuming.
    """
    link.command("EE_APPLY_OFFS")
    st, name = _ee_status(link)
    if st:
        raise EepromError("apply offsets: %s" % name)


def ee_adc_offset(link, channel, value=None):
    """Read or set one ADC offset by name, e.g. ee_adc_offset(link, "IDC").

    Setting one applies it immediately. THIS CHANGES WHAT THE DRIVE MEASURES:
    every current, voltage and power derived from that channel moves with it.
    """
    try:
        idx = EE_ADC_OFFSETS.index(channel.upper())
    except ValueError:
        raise ValueError("no ADC offset called %r; have %s"
                         % (channel, ", ".join(EE_ADC_OFFSETS)))
    addr = idx * 2
    if value is None:
        return ee_read(link, addr, 16)
    ee_write(link, addr, int(value), 16)
    ee_apply_adc_offsets(link)
    return ee_read(link, addr, 16)


# ---------------------------------------------------------------------------
# WHO STARTED THE RUN (firmware rev 27). Module-level, BELOW the Link class.
# ---------------------------------------------------------------------------

STARTR_NONE, STARTR_PANEL, STARTR_COMM = 0, 1, 2
STARTR_AUTO_BOOT, STARTR_AUTO_TIMER = 3, 4
STARTR_AUTO_UV, STARTR_AUTO_OT, STARTR_AUTO_GRID = 5, 6, 7
STARTR_UNKNOWN = 8
STARTR_AUTO_DEFER = 9

# Mirrors STARTR_* in drive/hs300_drive.h.
START_REASON_NAMES = {
    0: "never started since power-on",
    1: "PANEL - someone pressed the keypad",
    2: "COMM - a PC tool sent CMD_START",
    3: "AUTO - started at power-on by the build config",
    4: "AUTO - the auto-start delay after boot",
    5: "AUTO - recovered from an undervoltage trip",
    6: "AUTO - cooled down after an over-temperature trip",
    7: "AUTO - grid-mode auto-start timer",
    8: "unattributed - a call site that did not say",
    9: "AUTO - retry after a deferred start or a linger stop",
}


def start_reason_name(code):
    return START_REASON_NAMES.get(int(code), "unknown code %d" % int(code))

# Mirrors STOPR_* in drive/hs300_drive.h and the STATUS-derived codes 5/10/11.
# Codes 12 and 13 added 2026-09-07: clean stops that are NOT faults.
STOPR_START_DEFER, STOPR_LINGER = 12, 13
STOP_REASON_NAMES = {
    0: "none",
    5: "UNDERVOLTAGE trip - bus under 200 V",
    10: "PANEL - stopped at the keypad",
    11: "COMM - a PC tool sent CMD_STOP",
    12: "START DEFERRED - the array could not carry the start, retrying",
    13: "LINGER - ran below cut-in with the sun falling, stopped to retry",
    20: "OC envelope", 21: "OC tracking", 22: "OC RMS time-overcurrent", 23: "OC instantaneous",
    30: "INSUL_LEAK", 31: "WINDING_ASYM", 32: "PHASE_OPEN",
    41: "tune: Rs", 42: "tune: 40 Hz injection", 43: "tune: leakage out of band",
    44: "tune: ROTOR DID NOT TURN", 45: "tune: rotor dragged", 46: "tune: could not hold current",
    47: "tune: disagrees with the nameplate", 48: "tune: current abort",
}


def stop_reason_name(code):
    return STOP_REASON_NAMES.get(int(code), "code %d" % int(code))


def is_auto_start(code):
    return STARTR_AUTO_BOOT <= int(code) <= STARTR_AUTO_GRID


def run_info(link, now=None):
    """Who started the current or last run, when it began, and what it cost.

    Returns a dict. started_at is derived as now - RUN_AGE_S, because the
    drive has no clock; it is therefore only as good as the fact that the MCU
    has not been reset since (a reset zeroes these and reason reads 0).
    """
    import datetime
    t = link.read_telemetry(0, N_TEL)
    code = int(round(t[TEL_BY_NAME["START_REASON"]]))
    age = int(round(t[TEL_BY_NAME["RUN_AGE_S"]]))
    dur = int(round(t[TEL_BY_NAME["RUN_SECONDS"]]))
    kwh = t[TEL_BY_NAME["RUN_KWH"]]
    sts = int(round(t[TEL_BY_NAME["STS"]]))
    now = now or datetime.datetime.now()
    return {
        "reason": code,
        "reason_name": start_reason_name(code),
        "is_auto": is_auto_start(code),
        "running": sts == 1,
        "started_at": (now - datetime.timedelta(seconds=age)) if code else None,
        "age_s": age,
        "duration_s": dur,
        "kwh": kwh,
        "avg_kw": (kwh * 3600.0 / dur) if dur > 0 else 0.0,
    }


def format_run_info(d):
    if not d["reason"]:
        return "no run since power-on"
    when = d["started_at"].strftime("%Y-%m-%d %H:%M:%S")
    h, rem = divmod(d["duration_s"], 3600)
    m, s = divmod(rem, 60)
    return ("%s\n  started %s (%s ago)\n  %s for %dh%02dm%02ds, %.3f kWh, avg %.2f kW"
            % (d["reason_name"], when, _ago(d["age_s"]),
               "running" if d["running"] else "ran", h, m, s,
               d["kwh"], d["avg_kw"]))


def _ago(sec):
    if sec < 60:
        return "%ds" % sec
    if sec < 3600:
        return "%dm" % (sec // 60)
    return "%dh%02dm" % (sec // 3600, (sec % 3600) // 60)
