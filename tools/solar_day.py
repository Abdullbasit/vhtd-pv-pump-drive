'''
solar_day.py - log a whole day of MPPT operation. WATCHES ONLY.

    python solar_day.py COM11 9600 --flow 1

Start it before sunrise, leave it, stop it after sunset with Ctrl-C. It writes
a running CSV and, at the end, a report that answers the question the sweep
could not: what does the array actually deliver, hour by hour, and how much
water does that turn into.

IT NEVER COMMANDS THE DRIVE
  No START, no STOP, no frequency writes, no mode writes. Not one setting is
  touched. Put the drive in MPPT yourself and let it run its own day. This
  reads telemetry and the flowmeter and nothing else, so there is no ramp to
  protect and nothing here can hammer the pipe. If it crashes the pump carries
  on exactly as before.

WHY A WHOLE DAY
  The sweep answered what the pump does at any given power. It cannot answer
  how much power there is, which hours it is available, or whether MPPT
  actually settles where the characterisation says it should. Those need a
  day of watching, and a day of watching needs no experiment at all.

WHAT THE REPORT GIVES
  total volume and energy for the day, and kWh per m3 over the whole day
  the power profile by hour, and when the array first and last sustained flow
  how long was spent inside the efficient plateau, and how much water came
  from inside it against outside it
  every start and stop, with the volume and energy each one cost
  the frequency MPPT actually chose against the power available, so you can
  see whether it lands where the characterisation says it should
  the flow reading validated by M91 throughout, so a drifting meter cannot
  quietly corrupt a whole day

RESUMING
  It appends by default if a file for today already exists, so a laptop that
  sleeps or a cable knocked out does not cost the morning. Pass --fresh to
  start a new file instead.

NOTE ON THIS FILE
  No double quotes, no forward slashes, no hash characters, because the
  transfer channel strips exactly those.
'''
import sys, os, time, math, struct, argparse, datetime, csv, operator, json
try:
    import webview
except ImportError:
    webview = None


sys.path.insert(0, '.')
import hs300_protocol as proto
try:
    import modbus_rtu
except ImportError:
    modbus_rtu = None

dv = operator.truediv


def keep_awake():
    '''STOP WINDOWS SLEEPING FOR THE LENGTH OF THE RUN.

    2026-09-04 cost an entire PV afternoon. The laptop was on battery, it
    suspended at 15:16, and this tool carried on the instant it woke at
    18:15 with a three hour hole in the middle. Worse than losing the data,
    the CSV looked CONTINUOUS - the gap only showed up as two intervals of
    180 and 23.5 minutes among thousands of 15 s ones - and the sunset, the
    whole reason the UV ladder was being watched, was never recorded.

    ES_SYSTEM_REQUIRED tells Windows a process needs the machine awake. It
    is ADVISORY: a closed lid, a flat battery or Modern Standby can still
    win, which is why the caller also tells the operator to plug in. The
    flag is released by atexit so the laptop sleeps normally afterwards.'''
    if sys.platform != 'win32':
        return False
    try:
        import ctypes, atexit
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        k32 = ctypes.windll.kernel32
        if not k32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
            return False
        atexit.register(k32.SetThreadExecutionState, ES_CONTINUOUS)
        return True
    except Exception:
        return False

TEL_PDC = proto.TEL_BY_NAME['PDC']
TEL_FREQ = proto.TEL_BY_NAME['FREQ']
TEL_STS = proto.TEL_BY_NAME['STS']
TEL_MODE = proto.TEL_BY_NAME['MODE']
TEL_VDC = proto.TEL_BY_NAME['VDC']
TEL_IDC = proto.TEL_BY_NAME['IDC']
TEL_TEMP = proto.TEL_BY_NAME['TEMP']
TEL_FAULT = proto.TEL_BY_NAME['FAULT_FLAGS']
TEL_MOD = proto.TEL_BY_NAME['MOD_IDX']
'''Two temperature readings from different code paths on the same ADC. Reg 47
is the live value, reg 29 is the panel measurement mirror scaled by 10.
Agreement between them is evidence the reading is real; a persistent gap is
evidence it is not.'''
TEL_TEMP2 = proto.TEL_BY_NAME['MEAS_TEMP']
TEL_FOC0 = proto.TEL_BY_NAME['FOC_WM_HAT']

'''Two extra block reads per sample, added 2026-09-04 for the questions the
last PV run could not answer.

  68..70   the LIFETIME fault counters. The sunset of 09-04 tripped the drive
           on undervoltage an unknown number of times because nothing was
           counting - the log only showed FAULT_UV_WAIT before and after a
           gap. A counter that ticks tells you how many times the UV ladder
           fired even if every trip happens between two samples.
  151..164 IDQ_PEAK, the MPPT tracker's own view of the array, and the
           per-run energy counters. MPPT_VRATIO is what the tracker thinks
           Vdc/Voc is, which is the one number that says whether it is
           sitting where it means to sit.'''
'''67 is TEL_RESET_COUNT - MCU boots. The three fault counters after it are
published but never incremented by the firmware (found 2026-09-05), so this
is the one register in the block that moves: a step in it during the day is
a reboot, most likely a brown-out during a twilight start.'''
TEL_FCNT0 = proto.TEL_BY_NAME['START_COUNT']           # 66; resets 67, OC 68, UV 70
TEL_BLK0  = proto.TEL_BY_NAME['IDQ_PEAK']              # 151 .. 164
'''The bus shed, 165..166, added 2026-09-05 evening. On the 14:59 cloud the
FOC held current while the array lost it, and the bus went from 475 V to the
200 V trip between two samples. The shed scales the torque limit down with
the bus at ISR rate; BUS_SHED is the live factor, BUS_SHED_MIN the lowest
since the start. The MIN is the column to read: at 16 s per sample the
logger will never see the dip, only the latch it leaves behind.'''
TEL_SHED0 = proto.TEL_BY_NAME['START_REASON']          # 161; BUS_SHED 165 .. 166
'''CAP_STATE, 127: 2 = the fault-recorder ring is running, 3 = it FROZE on
a trip and holds the 512 ms before it. Logged so the first trip of the day
is visible in the CSV the moment it happens - dump it with
hs300_capture_dump.py before anything re-arms it.'''
TEL_CAP0  = proto.TEL_BY_NAME['CAP_STATE']             # 127 .. 128
'''The pre-start block, 129..138. Added 2026-09-05 because the winding
asymmetry gate had been dead since it was written - it measured a 58 percent
spread on a motor with shorted turns and passed it, having compared a fraction
against a limit that was 100x too large.

The gate is fixed and now sits at 25 percent, but that number rests on four
healthy samples taken inside a 5 C window. PS_SPREAD is published on EVERY
start, so logging it across a whole day is what says whether a healthy machine
drifts with temperature - and therefore whether 25 can safely become 15.'''
TEL_PS0   = proto.TEL_BY_NAME['PS_STATE']              # 129 .. 138
TEL_STOPR = proto.TEL_BY_NAME['STOP_REASON']           # inside the 0..63 read

'''The voltage ceiling, computed exactly as foc_step() computes it:
     vlim = FOC_V_MARGIN * FOC_M_MAX * Vdc / sqrt(3)
On 09-04 the drive sat with v_demand EQUAL to vlim for 28 minutes on the
array - it was bus-voltage limited, not current limited and not FOC limited,
and MPPT had no authority left because every perturbation ran into the same
wall. That was only discovered by hand afterwards. Logging vlim and the
headroom against it makes it visible in the CSV as it happens.'''
FOC_V_MARGIN = 0.95
FOC_M_MAX = 0.94
SET_CF_TEMP = proto.SET_BY_NAME['F31 CF_TEMPERATURE']
CMD_RESET = proto.COMMANDS['RESET_FAULT']
CMD_START = proto.COMMANDS['START']

'''Motor nameplate, for the voltage headroom check. With SVPWM the bus can
synthesise Vdc divided by root two as line to line RMS, so the frequency at
which the drive runs out of volts is that figure divided by the V per Hz
slope. Measured on this installation: 296 V at 46 Hz on a 470 V bus, which is
a modulation index of 0.89 and a ceiling near 52 Hz.'''
MOTOR_V = 320.0
MOTOR_F = 50.0

DIAG_TIME_REG = 81
DIAG_RATIO_REG = 97
M91_LO, M91_HI = 97.0, 103.0

FIELDS = ['iso', 't_s', 'sts', 'mode', 'hz', 'P_W', 'VDC', 'IDC', 'drive_C',
          'Q_m3h', 'vel_ms', 'QperP', 'bore_mm', 'M91_pct', 'transit_us',
          'pos_total', 'fault', 'mod_idx', 'headroom_pct', 'panel_C',
          'f_rot', 'f_slip', 'foc_id', 'foc_iq', 'psir', 'foc_md',
          'te_Nm', 'p_est_W',
          'foc_idref', 'foc_iqref', 'v_dem', 'vlim', 'v_left', 'on_ceiling',
          'stop_r', 'f_uv_n', 'f_oc_n', 'idq_pk',
          'mppt_voc', 'mppt_vhold', 'mppt_vratio', 'run_kwh',
          'rpm', 'ps_spread', 'ps_flags', 'ps_ru', 'ps_rv', 'ps_rw', 'ps_leak',
          'foc_rs', 'foc_rr', 'foc_lm', 'foc_sigls', 'tune_sts',
          'shed', 'shed_min', 'cap_state', 'resets',
          # added 2026-09-08 06:05 mid-run, so they sit LAST: the day's CSV had
          # its header rewritten in place and the earlier rows are simply short
          'starts', 'start_r']


def mean(xs):
    xs = [x for x in xs if x is not None]
    return dv(sum(xs), len(xs)) if xs else None


def raw_read(ser, unit, first_register, count, timeout=0.6):
    addr = first_register - 1
    body = bytes([unit, 0x03]) + struct.pack('>HH', addr, count)
    c = modbus_rtu.crc16(body)
    req = body + bytes([c & 0xFF, c >> 8])
    want = 5 + 2 * count
    time.sleep(0.02)
    ser.reset_input_buffer()
    ser.write(req)
    ser.flush()
    buf = bytearray()
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = ser.in_waiting
        chunk = ser.read(n if n else 1)
        if chunk:
            buf += chunk
        if len(buf) >= want:
            break
    for j in range(max(0, len(buf) - want + 1)):
        if buf[j] != unit or buf[j + 1] != 0x03 or buf[j + 2] != 2 * count:
            continue
        fr = buf[j:j + want]
        ck = modbus_rtu.crc16(fr[:-2])
        if (ck & 0xFF) != fr[-2] or (ck >> 8) != fr[-1]:
            continue
        return list(struct.unpack('>%dH' % count, fr[3:3 + 2 * count]))
    return None


class DayLog:
    def __init__(self, link, args, csvpath, emit=None):
        self.link = link
        self.a = args
        self.emit = emit if emit else (lambda m: print(m, flush=True))
        self.rows = []
        self.csvpath = csvpath
        self.energy_J = 0.0
        self.volume_m3 = 0.0
        self.plateau_J = 0.0
        self.plateau_m3 = 0.0
        self.run_s = 0.0
        self.events = []
        self._last_t = None
        '''Pole pairs, for rotor rpm. Read LAZILY, not in __init__: on a PV
        drive this tool is routinely started hours before the array wakes the
        inverter, and a settings read then returns nothing at all.'''
        self._pp = None
        self._last_sts = None
        self.pending = []
        self.write_errs = 0
        self.ring_next = 0.0        # time.time() of the next ring dump
        self.ring_ok = False        # last arm confirmed what was asked for
        self.ring_n = 0             # dumps written
        self.ring_trips = 0         # frozen-by-a-trip records saved
        self.read_errs = 0
        self.recoveries = []
        self.last_recover = 0.0
        self.live = dict(row=None, totals=dict(), history=[])

    def f32_at(self, reg):
        g = raw_read(self.link.ser, self.a.flow, reg, 2)
        return modbus_rtu.f32(g, 0, 'cdab') if g else None

    def sample(self, t0):
        now = time.time()
        g = raw_read(self.link.ser, self.a.flow, 1, 12) if self.a.flow else None
        q = vel = None
        if g:
            q = modbus_rtu.f32(g, 0, 'cdab')
            vel = modbus_rtu.f32(g, 4, 'cdab')
        tt = self.f32_at(self.a.tt_reg) if self.a.flow else None
        rr = self.f32_at(self.a.ratio_reg) if self.a.flow else None
        m91 = rr * 100.0 if rr is not None else None
        tot = None
        if g and len(g) >= 12:
            tot = modbus_rtu.total(modbus_rtu.i32(g, 8, 'cdab'),
                                   modbus_rtu.f32(g, 10, 'cdab'))

        tel = self.link.read_telemetry(addr=0, cnt=64)

        '''FOC block, one extra 16 register read. Registers hold the last
        session when the drive is off, so the row only records them while
        the state is ON - a stale flux number in an OFF row would be worse
        than a blank one.'''
        '''GATED ON tel. Waiting overnight for an inverter to wake on PV
        means every read times out, and four dead reads per sample can push
        the cycle past the requested period. One failed read is enough to
        know the drive is not there yet.'''
        foc = fcnt = blk = ps = shed = cap = None
        if tel:
            foc = self.link.read_telemetry(addr=TEL_FOC0, cnt=16)
            fcnt = self.link.read_telemetry(addr=TEL_FCNT0, cnt=5)
            blk = self.link.read_telemetry(addr=TEL_BLK0, cnt=14)
            ps = self.link.read_telemetry(addr=TEL_PS0, cnt=10)
            shed = self.link.read_telemetry(addr=TEL_SHED0, cnt=6)
            cap = self.link.read_telemetry(addr=TEL_CAP0, cnt=2)
        if tel:
            p, hz = tel[TEL_PDC], tel[TEL_FREQ]
            sts, mode = tel[TEL_STS], tel[TEL_MODE]
            vdc, idc, temp = tel[TEL_VDC], tel[TEL_IDC], tel[TEL_TEMP]
            fault = tel[TEL_FAULT]
            mi = tel[TEL_MOD]
            temp2 = dv(tel[TEL_TEMP2], 10.0)
        else:
            p = hz = sts = mode = vdc = idc = temp = fault = mi = None
            temp2 = None

        bore = None
        if q is not None and vel is not None and abs(vel) > 1e-6:
            area = dv(dv(q, 3600.0), vel)
            if area > 0:
                bore = math.sqrt(dv(4.0 * area, math.pi)) * 1000.0

        '''How much of the available bus voltage is left. Under about 10
        percent the drive is close to running out of volts, and above the
        ceiling the motor is under fluxed and drawing extra current for the
        same torque.'''
        head = None
        if (vdc is not None and vdc > 50.0 and hz is not None and hz > 1.0):
            need = MOTOR_V * dv(hz, MOTOR_F)
            avail = dv(vdc, math.sqrt(2.0))
            if avail > 0:
                head = (1.0 - dv(need, avail)) * 100.0

        qp = None
        if q is not None and p is not None and p > 50.0 and q > 0:
            qp = dv(q * 1000.0, p)

        '''Integrate with the ACTUAL gap between samples, not the requested
        period. A retry, a slow reply or a laptop that dozed all stretch the
        real interval, and assuming the nominal one quietly loses volume.'''
        if self._last_t is not None:
            dt = now - self._last_t
            if 0 < dt < self.a.max_gap:
                if p is not None and p > 0:
                    self.energy_J += p * dt
                if q is not None and q > 0:
                    self.volume_m3 += dv(q, 3600.0) * dt
                if sts is not None and int(sts) == 1:
                    self.run_s += dt
                if (hz is not None and self.a.plateau_lo <= hz
                        <= self.a.plateau_hi):
                    if p is not None and p > 0:
                        self.plateau_J += p * dt
                    if q is not None and q > 0:
                        self.plateau_m3 += dv(q, 3600.0) * dt
        self._last_t = now

        s = None if sts is None else proto.state_name(sts)
        if s != self._last_sts:
            if self._last_sts is not None:
                self.events.append((now - t0, self._last_sts, s,
                                    self.volume_m3, dv(self.energy_J, 3.6e6)))
            self._last_sts = s

        row = dict(iso=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   t_s=round(now - t0, 1), sts=s,
                   mode=(proto.MODE_NAMES.get(int(mode + 0.5), '?')
                         if mode is not None else None),
                   hz=round(hz, 2) if hz is not None else None,
                   P_W=round(p, 1) if p is not None else None,
                   VDC=round(vdc, 1) if vdc is not None else None,
                   IDC=round(idc, 2) if idc is not None else None,
                   drive_C=round(temp, 1) if temp is not None else None,
                   Q_m3h=round(q, 4) if q is not None else None,
                   vel_ms=round(vel, 5) if vel is not None else None,
                   QperP=round(qp, 3) if qp is not None else None,
                   bore_mm=round(bore, 2) if bore is not None else None,
                   M91_pct=round(m91, 2) if m91 is not None else None,
                   transit_us=round(tt, 3) if tt is not None else None,
                   pos_total=round(tot, 4) if tot is not None else None,
                   fault=int(fault) if fault is not None else None,
                   mod_idx=round(mi, 4) if mi is not None else None,
                   headroom_pct=round(head, 1) if head is not None else None,
                   panel_C=round(temp2, 1) if temp2 is not None else None)

        if foc and sts is not None and int(sts + 0.5) == 1:
            row['f_rot']  = round(foc[0], 3)
            row['f_slip'] = round(foc[1], 3)
            row['foc_id'] = round(foc[2], 2)
            row['foc_iq'] = round(foc[3], 2)
            row['psir']   = round(foc[6], 3)
            row['foc_md'] = int(foc[8] + 0.5)
            row['te_Nm']  = round(foc[9], 2)
            row['p_est_W'] = round(foc[10], 1)
            row['foc_idref'] = round(foc[4], 2)
            row['foc_iqref'] = round(foc[5], 2)
            '''v_demand against the ceiling it is actually working into.
            v_left near zero with iq_ref still climbing is the bus-limited
            signature; v_left healthy means the limit is somewhere else.'''
            vd = foc[7]
            row['v_dem'] = round(vd, 1)
            if vdc is not None and vdc > 50.0:
                vl = FOC_V_MARGIN * FOC_M_MAX * dv(vdc, math.sqrt(3.0))
                row['vlim'] = round(vl, 1)
                row['v_left'] = round(vl - vd, 1)
                row['on_ceiling'] = 1 if vd >= 0.98 * vl else 0
        else:
            for k in ('f_rot', 'f_slip', 'foc_id', 'foc_iq', 'psir',
                      'foc_md', 'te_Nm', 'p_est_W', 'foc_idref', 'foc_iqref',
                      'v_dem', 'vlim', 'v_left', 'on_ceiling'):
                row[k] = None

        '''These four are logged whether the drive is running or NOT. The
        fault counters and the tracker's array view are exactly what you want
        from a drive that has just tripped at sunset, and blanking them on an
        OFF row would throw away the only record of why it stopped.'''
        '''ROTOR SPEED IN RPM, not just the Hz already logged as f_rot. The
        pump is specified in rpm, the yield curve is in rpm, and the cut-in is
        quoted at 26.4 Hz rotor - which nobody can check against a plate
        without doing the arithmetic. pp comes from the panel nameplate.'''
        if foc and sts is not None and int(sts + 0.5) == 1:
            if not self._pp:
                try:
                    st = self.link.read_settings(
                        addr=proto.SET_BY_NAME['PLATE_PP'], cnt=1)
                    if st and st[0] >= 0.5:
                        self._pp = float(st[0])
                except Exception:
                    pass
            pp = self._pp if self._pp else 1.0
            row['rpm'] = round(60.0 * foc[0] / pp, 1)
        else:
            row['rpm'] = None

        '''THE MACHINE ITSELF, logged on every row whether running or not.
        These are what the drive believes the motor IS - the four measured
        parameters plus the tune status - and they are persistent, not
        transient, so an OFF row carries them just as truthfully as a running
        one. They come free: the FOC block read already spans 104..119, so
        these five were being fetched and thrown away.

        WHY LOG A CONSTANT. Because it is not one. A retune rewrites all four,
        and a FAILED tune has historically rewritten them badly - on
        2026-08-29 a bisection returned Lm 18.1 mH on a machine that had been
        pumping five minutes earlier, and saved it. If that ever happens again
        the log says exactly which sample it changed on, instead of leaving a
        day of unexplainable behaviour.

        tune_sts is packed: bit 0 tuned, bit 1 last run failed, bits 2..5 the
        stage reached, bits 6..9 the failcode.'''
        if foc and len(foc) >= 16:
            row['tune_sts']  = int(foc[11] + 0.5)
            row['foc_rs']    = round(foc[12], 4)
            row['foc_rr']    = round(foc[13], 4)
            row['foc_lm']    = round(foc[14], 3)
            row['foc_sigls'] = round(foc[15], 4)
        else:
            for k in ('tune_sts', 'foc_rs', 'foc_rr', 'foc_lm', 'foc_sigls'):
                row[k] = None

        '''The pre-start block is logged on EVERY row, not only while running.
        The values latch from the last start, so an OFF row still carries the
        spread that was measured on the way in - which is exactly what you
        want from a drive that has just refused to start.'''
        if ps and len(ps) >= 10:
            row['ps_flags']  = int(ps[1] + 0.5)
            row['ps_leak']   = round(ps[2], 3)
            row['ps_ru']     = round(ps[6], 4)
            row['ps_rv']     = round(ps[7], 4)
            row['ps_rw']     = round(ps[8], 4)
            row['ps_spread'] = round(ps[9], 4)
        else:
            for k in ('ps_flags', 'ps_leak', 'ps_ru', 'ps_rv', 'ps_rw',
                      'ps_spread'):
                row[k] = None

        row['stop_r'] = (int(tel[TEL_STOPR] + 0.5)
                         if tel and len(tel) > TEL_STOPR else None)
        row['starts'] = int(fcnt[0] + 0.5) if fcnt else None
        row['resets'] = int(fcnt[1] + 0.5) if fcnt else None
        row['f_oc_n'] = int(fcnt[2] + 0.5) if fcnt else None
        row['f_uv_n'] = int(fcnt[4] + 0.5) if fcnt else None
        if blk and len(blk) >= 14:
            row['idq_pk'] = round(blk[0], 2)
            row['mppt_voc'] = round(blk[1], 1)
            row['mppt_vhold'] = round(blk[2], 1)
            row['mppt_vratio'] = round(blk[3], 4)
            row['run_kwh'] = round(blk[12], 4)
        else:
            for k in ('idq_pk', 'mppt_voc', 'mppt_vhold', 'mppt_vratio',
                      'run_kwh'):
                row[k] = None
        if shed and len(shed) >= 6:
            row['start_r'] = int(shed[0] + 0.5)
            row['shed'] = round(shed[4], 3)
            row['shed_min'] = round(shed[5], 3)
        else:
            row['shed'] = row['shed_min'] = row['start_r'] = None
        row['cap_state'] = int(cap[0] + 0.5) if cap else None
        self.rows.append(row)
        self.append_csv(row)

        '''Snapshot for the web view. Kept small on purpose - the browser only
        needs the latest reading and enough history to draw a line.'''
        self.live['row'] = row
        self.live['totals'] = dict(
            m3=round(self.volume_m3, 3),
            kWh=round(dv(self.energy_J, 3.6e6), 3),
            run_h=round(dv(self.run_s, 3600.0), 2),
            recoveries=len(self.recoveries),
            write_errs=self.write_errs, read_errs=self.read_errs,
            queued=len(self.pending))
        h = self.live['history']
        h.append(dict(t=row['iso'][11:], p=row['P_W'], q=row['Q_m3h'],
                      hz=row['hz'], v=row['VDC']))
        if len(h) > 400:
            del h[:len(h) - 400]
        return row

    def recover(self, row):
        '''Clear a tripped drive and start it again.

        ONLY acts on a FAULT. A drive that is merely OFF is left alone, so
        this never fights a deliberate stop and never wakes the pump at dusk.
        Attempts are capped and spaced, because a drive that keeps tripping is
        telling you something and hammering it would be the wrong answer.'''
        if not self.a.auto_recover:
            return False
        if not row['fault'] or row['sts'] == 'ON':
            return False
        if len(self.recoveries) >= self.a.recover_max:
            return False
        if time.time() - self.last_recover < self.a.recover_cooldown:
            return False
        self.last_recover = time.time()
        n = len(self.recoveries) + 1
        self.emit('   FAULT flags 0x%02X at %s - recovery attempt %d of %d'
                  % (row['fault'], row['iso'], n, self.a.recover_max))
        self.emit('   waiting %gs before clearing' % self.a.recover_wait)
        time.sleep(self.a.recover_wait)
        try:
            self.link.command(CMD_RESET)
            time.sleep(2.0)
            t = self.link.read_telemetry(addr=0, cnt=64)
            ok = bool(t) and int(t[TEL_STS]) == 1
            if not ok:
                self.emit('   cleared but not running, sending START')
                self.link.command(CMD_START)
                time.sleep(3.0)
                t = self.link.read_telemetry(addr=TEL_STS, cnt=1)
                ok = bool(t) and int(t[0]) == 1
            self.emit('   %s' % ('running again' if ok else 'STILL DOWN'))
            self.recoveries.append(dict(iso=row['iso'], fault=row['fault'],
                                        ok=ok))
            return ok
        except Exception as e:
            self.emit('   recovery failed: %s: %s' % (type(e).__name__, e))
            self.recoveries.append(dict(iso=row['iso'], fault=row['fault'],
                                        ok=False))
            return False

    def ring_arm(self):
        '''Write the sources and divisor, then CAP_CTRL 3. The settings are RAM
        - a power cycle puts the ring back to wm_hat/iq/iA at DIV 1 - so this
        is also what to call after a reboot. Returns True if it is running.'''
        a = self.a
        try:
            src = self.ring_want_src()
            if self.link.write_setting(proto.SET_BY_NAME['CAP_DIV'], a.ring_div) is None:
                return False                     # not answering - try later
            for i in range(3):
                self.link.write_setting(proto.SET_BY_NAME['CAP_SRC%d' % i], src[i])
            time.sleep(0.2)
            '''0 then 3, not just 3: the sources and divisor are LATCHED by
            cap_arm(), and a drive that has just booted is already in mode 3
            with the boot defaults latched. Disarming first makes the re-arm
            unconditional.'''
            self.link.write_setting(proto.SET_CAP_CTRL, 0)
            time.sleep(0.2)
            self.link.write_setting(proto.SET_CAP_CTRL, 3)
            time.sleep(0.6)
            t = self.link.read_telemetry(addr=proto.TEL_BY_NAME['CAP_STATE'], cnt=1)
            l = self.link.read_telemetry(addr=proto.TEL_BY_NAME['CAP_SRC0'], cnt=3)
            ok = (bool(t) and int(t[0] + 0.5) == 2 and bool(l)
                  and [int(v + 0.5) for v in l] == src)
            self.ring_ok = ok
            return ok
        except Exception as e:
            self.emit('   ring arm failed: %s' % e)
            self.ring_ok = False
            return False

    def ring_want_src(self):
        src = [int(x) for x in self.a.ring_src.split(',')][:3]
        while len(src) < 3:
            src.append(0)
        return src

    def ring_dump(self, now_iso_fn=None):
        '''Freeze, read, re-arm. Called from the main loop when due.'''
        a = self.a
        base = self.csvpath[:-4] if self.csvpath.endswith('.csv') else self.csvpath
        try:
            t = self.link.read_telemetry(addr=proto.TEL_BY_NAME['CAP_STATE'], cnt=1)
            was_frozen = bool(t) and int(t[0] + 0.5) == 3
            t_freeze = time.time()
            rec = self.link.read_capture(rearm=3)
        except Exception as e:
            self.emit('   ring: %s: %s' % (type(e).__name__, e))
            return None
        if not rec:
            return None
        n = rec['valid']
        dt = rec['dt']
        names = rec['names']
        '''THE RING MUST BE CHECKED ON EVERY PULL, NOT TRUSTED FROM STARTUP.
        On 2026-09-06 the logger was started before the array had woken the
        drive; the arm at startup got no reply and the note said it would
        retry at the first dump, which it did not. Every pull of the morning
        came back at DIV 1 with the boot-default sources - wm_hat/iq/id for
        51 ms - and the first real shed events of the day went unrecorded.
        A power cycle or a brown-out during a twilight start does the same
        thing silently. So compare what the drive actually latched with what
        was asked for, and re-arm when they differ.'''
        want = self.ring_want_src()
        if list(rec['srcs']) != want or int(rec['div']) != int(self.a.ring_div):
            self.emit('   ring came back as DIV %d src %s, wanted DIV %d src %s - re-arming'
                      % (rec['div'], list(rec['srcs']), self.a.ring_div, want))
            if self.ring_arm():
                self.emit('   ring re-armed')
        '''ONE SMALL FILE PER PULL, in <outdir>/ring/, named by the time of its
        LAST sample. A single growing file would be megabytes by evening and
        would have to be opened whole to look at one cloud; this way the pull
        that covers 14:59:20 is ring_145924.csv and nothing else needs
        reading. index.csv has one line per pull - start, end, count, and the
        min/max of each channel - so the interesting file can be picked
        without opening any of them.'''
        rdir = os.path.join(os.path.dirname(self.csvpath) or '.', 'ring')
        os.makedirs(rdir, exist_ok=True)
        stamp = datetime.datetime.fromtimestamp(t_freeze).strftime('%H%M%S')
        if was_frozen:
            '''A trip froze it before we got here. The freeze instant is the
            trip, not now, so the times are relative to the trip only.'''
            self.ring_trips += 1
            path = os.path.join(rdir, 'trip_%s.csv' % stamp)
            with open(path, 'w', newline='') as fh:
                w = csv.writer(fh)
                w.writerow(['t_to_trip_s'] + names)
                for i in range(n):
                    w.writerow([round((i - (n - 1)) * dt, 4)] +
                               [round(rec['chans'][c][i], 4) for c in range(3)])
            self.emit('   RING WAS FROZEN BY A TRIP - saved ring/%s (%d samples, %.0f ms each)'
                      % (os.path.basename(path), n, dt * 1000))
            t_start = t_end = None
        else:
            self.ring_n += 1
            path = os.path.join(rdir, 'ring_%s.csv' % stamp)
            t_start = t_freeze - (n - 1) * dt
            t_end = t_freeze
            with open(path, 'w', newline='') as fh:
                w = csv.writer(fh)
                w.writerow(['iso', 't_s'] + names)
                for i in range(n):
                    ts = t_freeze - (n - 1 - i) * dt
                    w.writerow([datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S.%f')[:-3],
                                round(ts, 3)] +
                               [round(rec['chans'][c][i], 4) for c in range(3)])
        try:
            ipath = os.path.join(rdir, 'index.csv')
            new = not os.path.exists(ipath)
            with open(ipath, 'a', newline='') as fh:
                w = csv.writer(fh)
                if new:
                    '''GENERIC column names, plus the channel names as data.
                    The header is written once and the ring can be re-armed
                    with different sources later - on 2026-09-06 the first
                    pulls were the boot defaults and every later row carried
                    vDcInst/set_freq/iq_shed under wm_hat/iq/id headings.'''
                    w.writerow(['file', 'start', 'end', 'n', 'dt_ms', 'trip', 'names'] +
                               ['ch%d_%s' % (c, k) for c in range(3) for k in ('min', 'max')])
                fmt = lambda t: (datetime.datetime.fromtimestamp(t).strftime('%H:%M:%S.%f')[:-3]
                                 if t else '')
                mm = []
                for c in range(3):
                    vals = [v for v in rec['chans'][c][:n] if v == v]
                    mm += [round(min(vals), 3) if vals else '', round(max(vals), 3) if vals else '']
                w.writerow([os.path.basename(path), fmt(t_start), fmt(t_end), n,
                            round(dt * 1000, 1), int(was_frozen), '/'.join(names)] + mm)
        except Exception as e:
            self.emit('   ring index: %s' % e)
        '''The re-arm check inside read_capture races the telemetry refresh and
        reports False a second before the state turns to 2. Look again, and
        only if it is genuinely still frozen write 3 once more.'''
        time.sleep(0.5)
        try:
            t = self.link.read_telemetry(addr=proto.TEL_BY_NAME['CAP_STATE'], cnt=1)
            if t and int(t[0] + 0.5) == 3:
                self.link.write_setting(proto.SET_CAP_CTRL, 3)
                time.sleep(0.5)
                t = self.link.read_telemetry(addr=proto.TEL_BY_NAME['CAP_STATE'], cnt=1)
                if t and int(t[0] + 0.5) == 3:
                    self.emit('   ring did NOT re-arm - fault recorder is off')
        except Exception:
            pass
        return rec

    def run_cmd_file(self):
        '''<outdir>/cmd.txt: one instruction per line, applied over this
        logger's own link so nobody has to stop the logger to change a
        setting. Written on 2026-09-06 after a morning of exactly that.
            set NAME VALUE      write_setting by hs300_protocol name
            cmd NAME            e.g. cmd STOP, cmd START, cmd PANEL_UNLOCK
            save                CMD_SAVE_SETTINGS - REFUSED unless the drive
                                is OFF (it stores live currents as offsets)
        Every line is answered in cmd.log with what the drive echoed back,
        and the file is deleted whether or not every line succeeded.'''
        d = os.path.dirname(self.csvpath) or '.'
        path = os.path.join(d, 'cmd.txt')
        if not os.path.exists(path):
            return
        try:
            lines = [l.strip() for l in open(path).read().splitlines() if l.strip()]
        except Exception:
            return
        try:
            os.remove(path)
        except Exception:
            pass
        with open(os.path.join(d, 'cmd.log'), 'a') as lg:
            for line in lines:
                if line.startswith('#'):
                    continue
                parts = line.split()
                out = None
                try:
                    if parts[0].lower() == 'set' and len(parts) == 3:
                        idx = proto.SET_BY_NAME[parts[1]]
                        e = self.link.write_setting(idx, float(parts[2]))
                        out = 'set %s = %s -> drive stored %s' % (parts[1], parts[2], e)
                    elif parts[0].lower() == 'cmd' and len(parts) == 2:
                        if parts[1] == 'SAVE_SETTINGS':
                            out = 'refused: use "save"'
                        else:
                            e = self.link.command(parts[1])
                            out = 'cmd %s -> %s' % (parts[1], 'ok' if e is not None else 'NO REPLY')
                    elif parts[0].lower() == 'save':
                        t = self.link.read_telemetry(addr=TEL_STS, cnt=1)
                        if t and int(t[0] + 0.5) == 0:
                            e = self.link.command('SAVE_SETTINGS')
                            out = 'save -> %s' % ('ok' if e is not None else 'NO REPLY')
                        else:
                            out = 'save REFUSED: drive is not OFF'
                    else:
                        out = 'unknown: %s' % line
                except Exception as e:
                    out = '%s -> %s: %s' % (line, type(e).__name__, e)
                stamp = datetime.datetime.now().strftime('%H:%M:%S')
                lg.write('%s  %s\n' % (stamp, out))
                self.emit('   cmd.txt: %s' % out)

    def append_csv(self, row):
        '''Written and flushed every sample, but a FAILED write must never end
        the day. Opening the file in Excel on Windows locks it, and the old
        code let that PermissionError propagate and kill the run - losing
        every hour that had not happened yet because of a file someone was
        reading. Rows that cannot be written queue up and go out on the next
        successful open instead.'''
        self.pending.append(row)
        try:
            new = not os.path.exists(self.csvpath)
            with open(self.csvpath, 'a', newline='') as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if new:
                    w.writeheader()
                for r in self.pending:
                    w.writerow(r)
            self.pending = []
            return True
        except Exception:
            self.write_errs += 1
            return False


def report(d, emit, args):
    rows = d.rows
    if not rows:
        emit('no samples.')
        return
    flowing = [r for r in rows if r['Q_m3h'] is not None and r['Q_m3h'] > 0.2]
    running = [r for r in rows if r['sts'] == 'ON']

    emit('')
    emit('=' * 78)
    emit(' SOLAR DAY REPORT')
    emit('=' * 78)
    first = rows[0]['iso']
    last = rows[-1]['iso']
    emit('   %s  to  %s' % (first, last))
    emit('   %d samples, %.2f h of logging, %.2f h with the drive running'
         % (len(rows), dv(rows[-1]['t_s'], 3600.0), dv(d.run_s, 3600.0)))

    kwh = dv(d.energy_J, 3.6e6)
    emit('')
    emit(' THE DAY IN FOUR NUMBERS')
    emit('   water lifted     %.2f m3' % d.volume_m3)
    emit('   energy used      %.2f kWh' % kwh)
    if d.volume_m3 > 0.01:
        emit('   specific energy  %.4f kWh per m3' % dv(kwh, d.volume_m3))
        emit('   day average      %.3f L per Wh'
             % dv(d.volume_m3 * 1000.0, kwh * 1000.0))

    if flowing:
        emit('')
        emit(' WHEN THE WATER RAN')
        emit('   first flow  %s   at %.1f Hz, %.0f W'
             % (flowing[0]['iso'], flowing[0]['hz'] or 0, flowing[0]['P_W'] or 0))
        emit('   last flow   %s   at %.1f Hz, %.0f W'
             % (flowing[-1]['iso'], flowing[-1]['hz'] or 0, flowing[-1]['P_W'] or 0))

    ps = [r['P_W'] for r in running if r['P_W'] is not None]
    if ps:
        pk = max(running, key=lambda r: r['P_W'] or 0)
        emit('')
        emit(' POWER')
        emit('   peak %.0f W at %s, %.1f Hz'
             % (pk['P_W'], pk['iso'], pk['hz'] or 0))
        emit('   mean while running %.0f W' % mean(ps))

    emit('')
    emit(' BY HOUR')
    emit('   hour   mean W   peak W   mean Hz   m3 lifted   L per Wh')
    buckets = {}
    prev_t = None
    for r in rows:
        h = r['iso'][11:13]
        b = buckets.setdefault(h, dict(p=[], hz=[], m3=0.0, J=0.0))
        if r['P_W'] is not None:
            b['p'].append(r['P_W'])
        if r['hz'] is not None and r['sts'] == 'ON':
            b['hz'].append(r['hz'])
        if prev_t is not None:
            dt = r['t_s'] - prev_t
            if 0 < dt < args.max_gap:
                if r['Q_m3h'] and r['Q_m3h'] > 0:
                    b['m3'] += dv(r['Q_m3h'], 3600.0) * dt
                if r['P_W'] and r['P_W'] > 0:
                    b['J'] += r['P_W'] * dt
        prev_t = r['t_s']
    for h in sorted(buckets):
        b = buckets[h]
        if not b['p']:
            continue
        lwh = (dv(b['m3'] * 1000.0, dv(b['J'], 3600.0))
               if b['J'] > 1000.0 and b['m3'] > 0 else None)
        emit('   %s:00 %8.0f %8.0f %9s %11.3f %10s'
             % (h, mean(b['p']), max(b['p']),
                ('%.1f' % mean(b['hz'])) if b['hz'] else '--',
                b['m3'], ('%.3f' % lwh) if lwh else '--'))

    emit('')
    emit(' DID MPPT LAND ON THE PLATEAU')
    emit('   the sweep says %g to %g Hz is the flat efficiency band'
         % (args.plateau_lo, args.plateau_hi))
    if d.volume_m3 > 0.001:
        emit('   %.1f percent of the day water came from inside it'
             % (dv(d.plateau_m3, d.volume_m3) * 100.0))
    if d.plateau_m3 > 0.001 and d.plateau_J > 1000.0:
        emit('   inside the band  %.3f L per Wh'
             % dv(d.plateau_m3 * 1000.0, dv(d.plateau_J, 3600.0)))
    out_m3 = d.volume_m3 - d.plateau_m3
    out_J = d.energy_J - d.plateau_J
    if out_m3 > 0.001 and out_J > 1000.0:
        emit('   outside it       %.3f L per Wh'
             % dv(out_m3 * 1000.0, dv(out_J, 3600.0)))
    hzs = [r['hz'] for r in running if r['hz'] is not None]
    if hzs:
        below = len([h for h in hzs if h < args.plateau_lo])
        above = len([h for h in hzs if h > args.plateau_hi])
        emit('   of %d running samples: %d below the band, %d above, %d inside'
             % (len(hzs), below, above, len(hzs) - below - above))
        if dv(below, len(hzs)) > 0.5:
            emit('   -> MPPT spent most of the day BELOW the efficient band.')
            emit('      Either the array cannot reach it for long, or the')
            emit('      MPPT parameters are holding the frequency down.')

    if d.events:
        emit('')
        emit(' STARTS AND STOPS')
        emit('   time        change            m3 so far   kWh so far')
        for t, a_s, b_s, vol, e in d.events:
            emit('   %8.0fs   %-8s -> %-8s %10.3f %11.3f'
                 % (t, a_s, b_s, vol, e))
        emit('   %d transitions. Each restart refills whatever drained back;'
             % len(d.events))
        emit('   with the check valve at the pump that is a one time cost, not')
        emit('   a per cycle one.')

    m91 = [r['M91_pct'] for r in flowing if r['M91_pct'] is not None]
    if m91:
        emit('')
        emit(' METER VALIDATION ACROSS THE DAY')
        emit('   M91 %.2f to %.2f percent over %d flowing samples (spec %g to %g)'
             % (min(m91), max(m91), len(m91), M91_LO, M91_HI))
        bad = [x for x in m91 if not (M91_LO <= x <= M91_HI)]
        if bad:
            emit('   %d samples out of spec. The geometry drifted at some point'
                 % len(bad))
            emit('   in the day - find them in the CSV before trusting the')
            emit('   volume above.')
        else:
            emit('   -> in spec all day. The volume above is as good as the')
            emit('      absolute calibration, which only the drum test fixes.')
    bores = [r['bore_mm'] for r in flowing if r['bore_mm'] is not None]
    if bores:
        emit('   meter bore %.2f to %.2f mm' % (min(bores), max(bores)))

    '''The clamp question, answered from a normal day rather than an
    experiment. The firmware limits frequency to 0.1 times the bus voltage,
    which is exactly a modulation index of 1.10. If the drive spent the strong
    hours sitting on that line, the ceiling was electrical and not a power
    decision - and no MPPT tuning can recover what it cost.'''
    cl = [r for r in running
          if r['hz'] is not None and r['VDC'] is not None and r['VDC'] > 50]
    if cl:
        on_clamp = [r for r in cl if r['hz'] >= 0.1 * r['VDC'] - args.clamp_tol]
        emit('')
        emit(' WAS THE FREQUENCY CLAMPED')
        emit('   the firmware ceiling is 0.1 times Vdc, the same as modIdx 1.10')
        emit('   %d of %d running samples were within %.2f Hz of it (%.1f percent)'
             % (len(on_clamp), len(cl), args.clamp_tol,
                dv(len(on_clamp), len(cl)) * 100.0))
        if on_clamp:
            ps = [r['P_W'] for r in on_clamp if r['P_W'] is not None]
            hs = [r['hz'] for r in on_clamp]
            vs = [r['VDC'] for r in on_clamp]
            emit('   while clamped: %.0f to %.0f W, %.1f to %.1f Hz, %.0f to %.0f V'
                 % (min(ps), max(ps), min(hs), max(hs), min(vs), max(vs)))
            emit('   first at %s, last at %s'
                 % (on_clamp[0]['iso'], on_clamp[-1]['iso']))
            top = max(cl, key=lambda r: r['P_W'] or 0)
            emit('   the highest power of the day, %.0f W, was at %.1f Hz on a'
                 % (top['P_W'] or 0, top['hz']))
            emit('   %.0f V bus, where the ceiling stood at %.1f Hz'
                 % (top['VDC'], 0.1 * top['VDC']))
            if dv(len(on_clamp), len(cl)) > 0.2:
                emit('   -> the drive spent a serious part of the day against')
                emit('      the ceiling. Frequency was limited by bus voltage,')
                emit('      not by the tracker. Raising the array voltage is')
                emit('      the lever; MPPT parameters are not.')
        else:
            emit('   -> never near it. The frequency was always a power')
            emit('      decision, so the clamp cost nothing today.')

    mis = [r for r in running if r['mod_idx'] is not None]
    if mis:
        pk = max(mis, key=lambda r: r['mod_idx'])
        emit('')
        emit(' VOLTAGE HEADROOM')
        emit('   modulation index %.3f to %.3f while running'
             % (min(r['mod_idx'] for r in mis), pk['mod_idx']))
        emit('   highest %.3f at %.1f Hz on a %.0f V bus'
             % (pk['mod_idx'], pk['hz'] or 0, pk['VDC'] or 0))
        heads = [r['headroom_pct'] for r in running
                 if r['headroom_pct'] is not None]
        if heads:
            emit('   computed headroom %.1f to %.1f percent against a %.0f V '
                 '%.0f Hz motor' % (min(heads), max(heads), MOTOR_V, MOTOR_F))
            if min(heads) < 5.0:
                emit('   -> the drive ran CLOSE TO or OUT OF volts. Above that')
                emit('      point the motor is under fluxed and draws extra')
                emit('      current for the same torque, so the efficiency')
                emit('      figures at those frequencies are not comparable')
                emit('      with the rest.')
            else:
                emit('   -> headroom all day. V per f was held, so every')
                emit('      efficiency figure here is directly comparable.')

    t1 = [r['drive_C'] for r in rows if r['drive_C'] is not None]
    t2 = [r['panel_C'] for r in rows if r['panel_C'] is not None]
    if t1:
        emit('')
        emit(' TEMPERATURE')
        emit('   heatsink %.1f to %.1f C (register 47)' % (min(t1), max(t1)))
        if t2:
            emit('   panel    %.1f to %.1f C (register 29, scaled by 10)'
                 % (min(t2), max(t2)))
            pairs = [(r['drive_C'], r['panel_C']) for r in rows
                     if r['drive_C'] is not None and r['panel_C'] is not None]
            if pairs:
                gaps = [abs(a - b) for a, b in pairs]
                emit('   the two readings differ by %.1f C on average, worst %.1f'
                     % (dv(sum(gaps), len(gaps)), max(gaps)))
                if max(gaps) < 3.0:
                    emit('   -> they agree, so the sensor is reporting something')
                    emit('      real. A heatsink runs far hotter than the case')
                    emit('      or the exhaust air, which is where the heat is')
                    emit('      generated rather than where it ends up.')
                else:
                    emit('   -> they DISAGREE. One path is scaled or stale.')
                    emit('      Check F31, the temperature calibration factor.')

    faults = [r for r in rows if r['fault']]
    if faults:
        emit('')
        emit(' FAULTS')
        emit('   %d samples carried a non zero fault flag, first at %s'
             % (len(faults), faults[0]['iso']))

    emit('=' * 78)


def main():
    ap = argparse.ArgumentParser(description='full day MPPT logger, read only')
    ap.add_argument('port')
    ap.add_argument('baud', type=int, nargs='?', default=9600)
    ap.add_argument('--ttl', action='store_true')
    ap.add_argument('--flow', type=int, default=1)
    ap.add_argument('--period', type=float, default=15.0,
                    help='seconds between samples. 15 gives about 2900 rows '
                         'over a 12 hour day, which is plenty of resolution '
                         'and a small file.')
    ap.add_argument('--max-gap', type=float, default=120.0,
                    help='ignore intervals longer than this when integrating, '
                         'so a laptop that slept does not invent volume')
    ap.add_argument('--clamp-tol', type=float, default=0.5,
                    help='how close to 0.1 times Vdc counts as riding the '
                         'firmware frequency ceiling')
    ap.add_argument('--plateau-lo', type=float, default=36.0)
    ap.add_argument('--plateau-hi', type=float, default=41.0)
    ap.add_argument('--tt-reg', type=int, default=DIAG_TIME_REG)
    ap.add_argument('--ratio-reg', type=int, default=DIAG_RATIO_REG)
    ap.add_argument('--serve', type=int, default=0, metavar='PORT',
                    help='serve a read only web view on this port, so the day '
                         'can be watched from a phone. 0 disables it.')
    ap.add_argument('--auto-recover', action='store_true',
                    help='clear an overcurrent or other FAULT and restart the '
                         'pump. This is the ONE thing here that writes to the '
                         'drive, so it is off unless you ask for it. It never '
                         'acts on a drive that is merely stopped.')
    ap.add_argument('--recover-wait', type=float, default=60.0,
                    help='seconds to wait before clearing a fault')
    ap.add_argument('--recover-cooldown', type=float, default=600.0,
                    help='minimum seconds between recovery attempts')
    ap.add_argument('--recover-max', type=int, default=6,
                    help='give up after this many attempts in a day - a drive '
                         'that keeps tripping is telling you something')
    '''THE RING AS A SECOND, FAST LOGGER. The fault-recorder ring holds 3 x 256
    samples and runs continuously anyway. With --ring N it is frozen, read
    and re-armed every N seconds between slow samples, and the samples are
    appended to <csv>_ring.csv with absolute times - so a DIV 400 ring
    (80 ms, 20.5 s) read every ~16 s covers the day END TO END at 80 ms for
    three signals, where the slow log manages one row every few seconds. The
    default trio is the cloud story: vDcInst, MPPT set_freq, and the bus-shed
    factor. A readout takes ~5.7 s at 9600, during which the ring is frozen
    and would MISS a trip - accept that, or lengthen N. If the ring is found
    already frozen by a trip, the record is saved whole as <csv>_trip_<hms>.csv
    and announced, then the ring is re-armed.'''
    ap.add_argument('--outdir', default='', metavar='DIR',
                    help='put every file of this run under DIR (created). '
                         'Ring pulls go to DIR/ring/, one small file each.')
    ap.add_argument('--ring', type=float, default=0.0, metavar='S',
                    help='dump and re-arm the capture ring every S seconds '
                         '(0 = off). Try 16.')
    ap.add_argument('--ring-div', type=int, default=400,
                    help='CAP_DIV for the ring: 400 = 80 ms/sample, 20.5 s')
    ap.add_argument('--ring-src', default='12,26,28',
                    help='three CAP_SRC ids: default vDcInst,set_freq,iq_shed')
    ap.add_argument('--lock-panel', action='store_true',
                    help='refuse the front keypad for the length of the run, '
                         'so nobody starts or stops the drive by hand while '
                         'a test is logging. Refreshed every 60 s and it '
                         'expires 120 s after this tool stops.')
    ap.add_argument('--fresh', action='store_true',
                    help='start a new file even if one exists for today')
    ap.add_argument('--hours', type=float, default=0.0,
                    help='stop automatically after this many hours. 0 means '
                         'run until Ctrl-C.')
    a = ap.parse_args()

    if modbus_rtu is None:
        print('modbus_rtu.py must sit beside this file.')
        return

    link = proto.Link(a.port, a.baud, 'ttl' if a.ttl else 'rs485')
    link.open()
    magic = link.ping()

    day = datetime.datetime.now().strftime('%Y%m%d')
    csvpath = 'solar_day_%s.csv' % day
    if a.outdir:
        '''A day in its own folder, so the CSV, the settings snapshot, the
        report and the ring pulls travel together and nothing from another
        day sits beside them.'''
        os.makedirs(a.outdir, exist_ok=True)
        csvpath = os.path.join(a.outdir, csvpath)
    if a.fresh and os.path.exists(csvpath):
        csvpath = os.path.join(a.outdir, 'solar_day_%s_%s.csv') % (
            day, datetime.datetime.now().strftime('%H%M%S'))
    logpath = csvpath[:-4] + '.txt'
    out = open(logpath, 'a')

    W = 96
    CR = chr(13)
    live_on = [False]

    def status(txt):
        sys.stdout.write(CR + txt[:W].ljust(W))
        sys.stdout.flush()
        live_on[0] = True

    def emit(s):
        if live_on[0]:
            sys.stdout.write(CR + ' ' * W + CR)
            sys.stdout.flush()
            live_on[0] = False
        print(s, flush=True)
        out.write(s + chr(10))
        out.flush()

    emit('')
    emit('solar_day %s   port=%s baud=%d unit=%d magic=%s'
         % (datetime.datetime.now().strftime('%Y%m%d_%H%M%S'), a.port, a.baud,
            a.flow, hex(magic) if magic else 'no reply'))
    if magic != proto.FW_MAGIC:
        emit('   WARNING firmware magic does not match. Reading anyway - this')
        emit('   tool never writes, so a wrong map can only mislabel, not harm.')
    emit('   appending to %s' % csvpath)
    if keep_awake():
        emit('   sleep inhibited for the length of this run.')
        emit('   STILL PLUG THE LAPTOP IN - this stops IDLE sleep, not a flat')
        emit('   battery and not a closed lid.')
    else:
        emit('   COULD NOT INHIBIT SLEEP. Set the power plan to never sleep on')
        emit('   AC and on battery, or the day gets a hole in it like 09-04.')
    if a.auto_recover:
        emit('   AUTO RECOVERY IS ON. This tool will clear a FAULT and restart')
        emit('   the pump, up to %d times, at least %.0f s apart. It will not'
             % (a.recover_max, a.recover_cooldown))
        emit('   touch a drive that is simply stopped. Everything else here is')
        emit('   still read only.')
    else:
        emit('   THIS TOOL NEVER COMMANDS THE DRIVE. Put it in MPPT yourself.')
        emit('   (pass --auto-recover if you want it to clear trips)')
    if a.lock_panel:
        emit('')
        emit('   PANEL LOCK IS ON. The front keypad is refused - and that is')
        emit('   EVERY key, so nobody can STOP the drive by hand either. The')
        emit('   drive still beeps at them, and the serial link and every')
        emit('   protection stay live. The lock is refreshed every 60 s and')
        emit('   dies 120 s after this tool does, so a crash or Ctrl-C hands')
        emit('   the panel back on its own.')

    '''One settings snapshot per run, beside the CSV. The question a log cannot
    answer on its own is what the drive was SET to while it wrote it - F49/F50,
    the MPPT lines, F07, the gate - and the day this was added is the day
    those started being changed between runs. Read only, like everything
    else here; written once at startup.'''
    snap_state = {'done': False}

    def write_snapshot():
        '''Also called from the loop the first time the drive answers - a
        logger started before dawn finds nobody home at startup.'''
        if snap_state['done']:
            return
        try:
            sets = link.read_settings(addr=0, cnt=proto.N_SET)
            if not sets:
                return
            snap = {'when': datetime.datetime.now().isoformat(timespec='seconds'),
                    'port': a.port, 'fw_magic': ('0x%08X' % magic) if magic else None,
                    'tool_magic': '0x%08X' % proto.FW_MAGIC,
                    'settings': {r[1]: sets[r[0]] for r in proto.SETTINGS
                                 if r[0] < len(sets)}}
            snap_path = csvpath.replace('.csv', '_settings.json')
            with open(snap_path, 'a') as fh:
                fh.write(json.dumps(snap) + chr(10))
            emit('   settings snapshot appended to %s' % os.path.basename(snap_path))
            snap_state['done'] = True
        except Exception as e:                   # never let this stop the log
            emit('   settings snapshot failed: %s' % e)

    write_snapshot()

    tel = link.read_telemetry(addr=0, cnt=64)
    if tel:
        md = proto.MODE_NAMES.get(int(tel[TEL_MODE] + 0.5), '?')
        emit('   drive is in %s mode, %s, %.1f Hz'
             % (md, proto.state_name(tel[TEL_STS]), tel[TEL_FREQ]))
        if md != 'MPPT':
            emit('   NOTE this is not MPPT. Switch it before the sun comes up,')
            emit('   or the day records manual operation instead.')

    st = link.read_settings(addr=0, cnt=proto.N_SET)
    if st:
        cf = st[SET_CF_TEMP]
        emit('   F31 temperature calibration factor %.3f%s'
             % (dv(cf, 1000.0),
                '' if abs(cf - 1000.0) < 1.0 else '   NOT UNITY, readings are scaled'))
        emit('   F05 over temperature trip %.0f C after %.0f s'
             % (st[5], st[6]))

    d = DayLog(link, a, csvpath, emit)

    if a.ring > 0:
        if d.ring_arm():
            emit('   RING LOGGER ON: DIV %d (%.0f ms, %.1f s window), sources %s,'
                 % (a.ring_div, a.ring_div * 0.2, a.ring_div * 0.2 * 256 / 1000.0,
                    a.ring_src))
            emit('   pulled every %.0f s into %s, one file per pull plus index.csv.'
                 % (a.ring, os.path.join(os.path.dirname(csvpath) or '.', 'ring')))
            emit('   The ring is frozen ~6 s per pull - that gap is in the slow log only.')
        else:
            emit('   ring arm did not confirm - will retry at the first dump')
        d.ring_next = time.time() + a.ring
    if a.serve:
        if webview is None:
            emit('   webview.py not found beside this file - no web view')
        else:
            try:
                webview.start(a.serve, d.live,
                              'solar day ' + day, emit)
            except Exception as e:
                emit('   could not start the web view: %s' % e)
    t0 = time.time()
    end = t0 + a.hours * 3600.0 if a.hours > 0 else None
    emit('')
    emit('logging every %gs. Ctrl-C when the sun is down.' % a.period)
    '''NOTHING inside this loop may end the day except Ctrl-C.

    A serial glitch, a meter that misses a reply, a file locked because
    someone opened the CSV to look at it - every one of those is a reason to
    carry on, not to stop logging at eleven in the morning and lose the
    afternoon. Errors are counted and shown; the loop keeps going.'''
    fails = 0

    lock_ok = [False]

    def refresh_lock():
        '''Refreshed, never latched. PANEL_LOCK_S is 120 s in comm_ser.h, so
        60 s gives a whole missed cycle of margin. A failure is not worth
        ending the day over - the panel simply stays unlocked.

        TEST THE RETURN VALUE, DO NOT JUST CATCH. link.command() is
        write_setting(), which returns None on no reply rather than raising,
        so a try/except around it catches nothing and reports success against
        a drive that is not even powered. Caught on 2026-09-04 the first
        night this ran: it printed "panel locked" at 23:36 to an inverter
        that had been dark for hours.

        The transition is announced because on a PV drive it is genuinely
        useful - the minute the lock starts working is the minute the array
        brought the drive up, and that is worth having in the log.'''
        try:
            ok = link.command('PANEL_LOCK') is not None
        except Exception:
            ok = False
        if ok != lock_ok[0]:
            lock_ok[0] = ok
            emit('   panel LOCKED - the drive is answering.' if ok
                 else '   panel lock lost - the drive stopped answering.')
        return ok

    lock_next = 0.0
    if a.lock_panel:
        if not refresh_lock():
            emit('   no reply yet, so the panel is NOT locked. Retrying every')
            emit('   60 s - it locks itself when the drive powers up.')
        lock_next = time.time() + 60.0
    try:
        while end is None or time.time() < end:
            try:
                if a.lock_panel and time.time() >= lock_next:
                    refresh_lock()
                    lock_next = time.time() + 60.0
                r = d.sample(t0)
                fails = 0
                if r['fault'] and r['sts'] != 'ON':
                    d.recover(r)
                status('   %s  %-4s %5s Hz  P %7s W  Q %8s  %6.2f m3  %6.2f kWh  T %4s C%s'
                       % (r['iso'][11:], r['sts'] or '--',
                          ('%.1f' % r['hz']) if r['hz'] is not None else '--',
                          ('%.0f' % r['P_W']) if r['P_W'] is not None else '--',
                          ('%.2f' % r['Q_m3h']) if r['Q_m3h'] is not None else '--',
                          d.volume_m3, dv(d.energy_J, 3.6e6),
                          ('%.0f' % r['drive_C']) if r['drive_C'] is not None else '--',
                          ('  %d QUEUED' % len(d.pending)) if d.pending else ''))
                d.run_cmd_file()
                if r.get('sts'):
                    write_snapshot()             # no-op once written
                    if a.ring > 0 and not d.ring_ok:
                        if d.ring_arm():
                            emit('   ring armed: DIV %d src %s'
                                 % (a.ring_div, a.ring_src))
                if a.ring > 0 and time.time() >= d.ring_next:
                    d.ring_dump()
                    d.ring_next = time.time() + a.ring
            except KeyboardInterrupt:
                raise
            except Exception as e:
                fails += 1
                d.read_errs += 1
                if d.read_errs <= 5 or fails > 20:
                    emit('   sample error %d: %s: %s  (carrying on)'
                         % (d.read_errs, type(e).__name__, e))
                if fails > 20:
                    '''The link may have gone entirely. Reopening costs a few
                    seconds and fixes a USB adapter that re-enumerated.'''
                    emit('   %d consecutive failures - reopening the port' % fails)
                    try:
                        link.close()
                    except Exception:
                        pass
                    try:
                        link.open()
                        emit('   port reopened')
                    except Exception as e2:
                        emit('   reopen failed: %s' % e2)
                    fails = 0
            time.sleep(a.period)
    except KeyboardInterrupt:
        emit('')
        emit('stopped by operator')
    except Exception as e:
        emit('')
        emit('ERROR %s: %s' % (type(e).__name__, e))
    finally:
        if a.lock_panel:
            try:
                link.command('PANEL_UNLOCK')
                emit('')
                emit(' panel unlocked.')
            except Exception:
                emit('')
                emit(' could not unlock the panel - it expires by itself'
                     ' within %d s.' % 120)
        try:
            report(d, emit, a)
        except Exception as e:
            emit('report failed: %s: %s' % (type(e).__name__, e))
        if d.pending:
            emit('')
            emit(' %d rows never reached the CSV. Trying once more.'
                 % len(d.pending))
            if d.append_csv(d.pending.pop()):
                emit('   written.')
            else:
                emit('   still locked. Close whatever has the file open.')
        if d.recoveries:
            emit('')
            emit(' FAULT RECOVERIES')
            for x in d.recoveries:
                emit('   %s  flags 0x%02X  %s'
                     % (x['iso'], x['fault'],
                        'restarted' if x['ok'] else 'FAILED'))
            emit('   %d trips during the day. If this is more than one or two,'
                 % len(d.recoveries))
            emit('   the current limit or the tracker is set too close to an')
            emit('   edge and the recovery is papering over it.')
        if d.write_errs or d.read_errs:
            emit('')
            emit(' %d sample errors and %d write errors during the day, all'
                 % (d.read_errs, d.write_errs))
            emit(' survived. If the write count is high, something had the CSV')
            emit(' open - copy it rather than opening it in place next time.')
        emit('')
        emit(' data: %s   and this log: %s' % (csvpath, logpath))
        emit(' link stats: %s' % link.stats)
        out.close()
        link.close()


if __name__ == '__main__':
    main()
