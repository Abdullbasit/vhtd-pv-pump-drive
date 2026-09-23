#!/usr/bin/env python3
"""relay_ctl.py - throw the attack relays and stamp it in the day's log.

    python relay_ctl.py load on 90         R1 = resistor bank (banks preset by breakers)
    python relay_ctl.py string out         R2 = string isolator: out = R2 ON, in = R2 OFF
    python relay_ctl.py 1 on 90            close relay 1, auto-open after 90 s
    python relay_ctl.py 1 off
    python relay_ctl.py all off
    python relay_ctl.py status
    python relay_ctl.py mark "string 2 pulled by hand"
    python relay_ctl.py --serial COM7 1 on   same, over the USB cable instead
    python relay_ctl.py --ip 192.168.1.50 1 on   local path by IP (no mDNS)

Talks to the YD-ESP32-C3-4IN4OUT running tools/esp_relay, trying the paths
in order: LOCAL first - HTTP on the LAN, http://hs300relay.local/cmd (or
--ip), ~50 ms, no internet - then CLOUD - MQTT through broker.hivemq.com,
topics relay/<ID>/cmd|reply|ev|status, the same broker and WiFi list as the
converter agent - or the USB serial with --serial. The log says which path
answered. Every call appends a line to runs/<today>/marks.log (PC clock, ms)
with the box's reply, so the ring and the 3.5 s rows can be cut at the exact
instant. The drive is never touched - this is not the logger's link.
"""
import sys, os, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
MQTT_HOST, MQTT_PORT = 'broker.hivemq.com', 1883
LOCAL_HOST = 'hs300relay.local'          # mDNS name in main.cpp; override with --ip
LOCAL_IP   = '192.168.0.179'             # last known DHCP lease, tried when mDNS fails
DEVICE_ID = 'hs300relay-q7v2mk'          # must match DEVICE_ID in tools/esp_relay/src/main.cpp

ALIAS = {'load': '1', 'string': '2'}          # 2026-09-08 wiring: R1 load, R2 string isolator

def build_cmd(argv):
    what = argv[0].lower()
    if what in ALIAS:
        act = argv[1].lower() if len(argv) > 1 else 'status'
        act = {'out': 'on', 'in': 'off'}.get(act, act)
        argv = [ALIAS[what], act] + list(argv[2:]); what = argv[0]
    if what == 'status': return 'STATUS'
    if what == 'all':    return 'ALL OFF'
    ch = int(what)
    if not 1 <= ch <= 4: raise SystemExit('relay 1..4')
    act = argv[1].upper() if len(argv) > 1 else 'STATUS'
    secs = argv[2] if len(argv) > 2 else ''
    return ('R%d %s %s' % (ch, act, secs)).strip()

def via_serial(port, cmd):
    import serial
    s = serial.Serial(port, 115200, timeout=1.0, dsrdtr=False, rtscts=False)
    s.dtr = False; s.rts = False           # the CH340 would otherwise reset the board
    time.sleep(0.15); s.reset_input_buffer()
    s.write((cmd + '\n').encode())
    reply, t0 = [], time.time()
    while time.time() - t0 < 1.5:
        l = s.readline().decode(errors='replace').strip()
        if l: reply.append(l)
        if any(x.startswith(('OK', 'ERR')) for x in reply): break
    s.close()
    return reply

def via_http(host, cmd):
    import urllib.request, urllib.parse
    url = 'http://%s/cmd?c=%s' % (host, urllib.parse.quote(cmd))
    with urllib.request.urlopen(url, timeout=2.5) as r:
        return [x.strip() for x in r.read().decode(errors='replace').splitlines() if x.strip()]

def via_mqtt(cmd):
    import paho.mqtt.client as mqtt
    reply = []
    def on_msg(c, u, m):
        reply.append('%s %s' % (m.topic.rsplit('/', 1)[1], m.payload.decode(errors='replace')))
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.on_message = on_msg
    c.connect(MQTT_HOST, MQTT_PORT, 30)
    c.subscribe('relay/%s/reply' % DEVICE_ID, 1)
    c.subscribe('relay/%s/ev' % DEVICE_ID, 1)
    c.loop_start()
    time.sleep(0.3)
    c.publish('relay/%s/cmd' % DEVICE_ID, cmd, qos=1)
    t0 = time.time()
    while time.time() - t0 < 4.0:
        if any(x.startswith('reply') for x in reply): time.sleep(0.2); break
        time.sleep(0.05)
    c.loop_stop(); c.disconnect()
    return reply

def main():
    argv = sys.argv[1:]
    port = None; host = LOCAL_HOST
    if argv and argv[0] == '--serial':
        port = argv[1]; argv = argv[2:]
    elif argv and argv[0] == '--ip':
        host = argv[1]; argv = argv[2:]
    if not argv:
        print(__doc__); return 2
    day = datetime.date.today().strftime('%Y%m%d')
    outdir = os.path.join(HERE, 'runs', day); os.makedirs(outdir, exist_ok=True)
    logp = os.path.join(outdir, 'marks.log')
    def log(m):
        line = '%s  %s' % (datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3], m)
        print(line)
        with open(logp, 'a') as fh: fh.write(line + '\n')
    if argv[0].lower() == 'mark':
        log('MARK ' + ' '.join(argv[1:])); return 0
    cmd = build_cmd(argv)
    reply, path = [], ''
    if port:
        try: reply, path = via_serial(port, cmd), 'serial'
        except Exception as e: log('%s -> serial FAILED %s: %s' % (cmd, type(e).__name__, e)); return 1
    else:
        hosts = [host] + ([LOCAL_IP] if host != LOCAL_IP else [])   # mDNS can fail for a moment: try the IP too
        for h in hosts:
            try: reply, path = via_http(h, cmd), 'local'; break
            except Exception as e: print('   local path (%s) failed: %s' % (h, e))
        if not reply:
            try: reply, path = via_mqtt(cmd), 'cloud'
            except Exception as e2: log('%s -> FAILED local+cloud: %s' % (cmd, e2)); return 1
    log('%s -> [%s] %s' % (cmd, path, ' | '.join(reply) if reply else 'NO REPLY'))
    return 0 if any('OK' in x for x in reply) else 1

if __name__ == '__main__':
    sys.exit(main())
