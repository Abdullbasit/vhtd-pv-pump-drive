import os, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Circle

os.chdir(r'D:\dnld\stm32\hs300v2_foc_ota_001')
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 6.5})
ACC, GREY, LG, BLUE = '#b3541e', '#666666', '#bbbbbb', '#2f5f8f'
fig, ax = plt.subplots(figsize=(7.0, 5.5))
fig.subplots_adjust(0, 0, 1, 1)
ax.set_xlim(0, 101); ax.set_ylim(0, 78); ax.axis('off')

def box(x, y, w, h, text='', fc='white', ec='black', lw=0.9, ls='-', fs=6.0, tc='black', round_=True, va='center', bold=False):
    if round_:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.15,rounding_size=0.8', fc=fc, ec=ec, lw=lw, ls=ls))
    else:
        ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw, ls=ls))
    if text:
        ax.text(x + w / 2, y + h / 2 if va == 'center' else y + h - 0.8, text, ha='center', va=va, fontsize=fs,
                color=tc, linespacing=1.25, fontweight='bold' if bold else 'normal')

def line(pts, color='black', ls='-', lw=0.9):
    ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color, ls=ls, lw=lw, solid_capstyle='round', solid_joinstyle='round')

def arrow(p0, p1, color='black', ls='-', lw=0.9):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle='-|>', mutation_scale=7, lw=lw, color=color, ls=ls, shrinkA=0, shrinkB=0))

def switch(x, y, w=3.0, color=ACC, closed=False):
    """relay contact drawn open (the shot state) unless closed"""
    ax.add_patch(Circle((x, y), 0.35, fc='white', ec=color, lw=0.9)); ax.add_patch(Circle((x + w, y), 0.35, fc='white', ec=color, lw=0.9))
    if closed:
        line([(x + 0.35, y), (x + w - 0.35, y)], color=color, lw=1.1)
    else:
        line([(x + 0.3, y), (x + w - 0.6, y + 1.6)], color=color, lw=1.1)

ax.text(1, 74.5, '(a)', fontsize=8, fontweight='bold', va='center')

# ---------------- PV array: exactly three strings of 12 modules ----------------
ax.text(2, 72.2, 'PV array: 36 × LONGi Hi-MO 7 610 W, 12S3P, 21.96 kWp\nV_oc 519–535 V; 13.8–14.3 kW at the MPP on the test days', fontsize=5.9, va='center')
rows = [65.0, 59.0, 53.0]
for r, y in enumerate(rows):
    for k in range(12):
        ax.add_patch(Rectangle((3 + k * 2.15, y), 1.85, 3.6, fc='#e9eef4', ec=BLUE, lw=0.5))
        line([(3 + k * 2.15 + 0.92, y), (3 + k * 2.15 + 0.92, y + 3.6)], color=BLUE, lw=0.25)
    line([(28.7, y + 1.8), (30, y + 1.8)], lw=0.8)
    ax.text(29.2, y - 0.2, 'string %d: 12 in series' % (r + 1), fontsize=4.6, color=GREY, ha='right', va='top')
# string 1 goes through the isolator R2 (normally-closed, opened for a shot)
switch(30.4, 66.8, w=3.2)
ax.text(36.5, 69.3, 'R2  string isolator — normally-closed contact,\nso a box failure returns the string (one of three strings)', fontsize=5.4, color=ACC, ha='left', va='center')
line([(33.6, 66.8), (35.5, 66.8)], lw=0.8)
line([(30, 60.8), (35.5, 60.8)], lw=0.8); line([(30, 54.8), (35.5, 54.8)], lw=0.8)
line([(35.5, 66.8), (35.5, 54.8)], lw=1.2)                      # combiner
ax.text(37.5, 50.4, 'combiner: 3 strings in parallel', fontsize=5.0, color=GREY, ha='center')
# DC bus to the inverter
line([(35.5, 60.8), (52, 60.8)], lw=1.8)
ax.text(43.7, 62.1, 'DC bus  450–535 V', fontsize=6, ha='center', va='bottom')

# ---------------- inverter cabinet ----------------
box(52, 47, 22, 20, round_=False, lw=1.0)
ax.text(63, 65.7, '22 kW IGBT inverter', fontsize=6.3, ha='center', va='center', fontweight='bold')
box(53.2, 60.4, 19.6, 4.2, 'DC-link capacitors\n2S2P × 1500 µF, C = 1.5 mF', fs=5.5)
box(53.2, 53.6, 19.6, 6.0, 'FS100R12KT3 IGBT six-pack\n1200 V / 100 A\n5 kHz, 4 µs dead time', fs=5.3)
box(53.2, 48.4, 19.6, 4.6, 'STM32F334 control board\nFOC / V/f firmware, RS485', fs=5.5)
line([(52, 60.8), (53.2, 60.8)], lw=1.8)

# ---------------- resistor bank on the DC bus through R1 ----------------
line([(41, 60.8), (41, 40)], lw=1.0)
switch(41 - 1.5, 44.0, w=3.0)
ax.text(43.8, 44.6, 'R1  bank contact', fontsize=5.8, color=ACC, ha='left', va='center')
line([(41, 44.0), (41, 40)], lw=1.0)
ax.add_patch(Circle((41, 38.2), 1.5, fc='white', ec='black', lw=0.8)); ax.text(41, 38.2, 'A', fontsize=5.5, ha='center', va='center')
ax.text(43.2, 38.2, 'DC clamp meter', fontsize=5.5, va='center')
line([(41, 36.7), (41, 33)], lw=1.0); line([(32, 33), (50, 33)], lw=1.0)
bank_x = [33.5, 38.0, 42.5, 47.0]; kw = ['2.8 kW', '5.1 kW', '7.9 kW', '10.4 kW']
for x, k in zip(bank_x, kw):
    line([(x, 33), (x, 31)], lw=0.8)
    switch(x - 1.2, 29.6, w=2.4, color='black', closed=(k != '2.8 kW'))
    line([(x, 29.6), (x, 27.5)], lw=0.8)
    ax.add_patch(Rectangle((x - 1.1, 22.5), 2.2, 5, fc='white', ec='black', lw=0.8))
    for zz in range(4):
        line([(x - 1.1, 23.2 + zz * 1.2), (x + 1.1, 23.8 + zz * 1.2)], lw=0.4, color=GREY)
    ax.text(x, 18.7, k, fontsize=5.4, ha='center', va='top')
    line([(x, 22.5), (x, 19.5)], lw=0.8)
line([(32, 19.5), (50, 19.5)], lw=1.0)
ax.text(41, 16.0, 'graded resistor bank — breakers select the step; ~75 Ω per bank hot,\nmeasured with the clamp at 440–455 V', fontsize=5.4, ha='center', va='top', color=GREY)

# ---------------- relay box ----------------
box(2, 36, 22, 9, 'ESP32 relay box at the array\n4 channels (R1 bank, R2 string, R3, R4)\nLAN ≈100 ms, MQTT fallback; every\ncommand time-stamped → marks.log', fs=5.4)
line([(24, 42.5), (32.4, 42.5), (32.4, 66.8)], color=ACC, ls='--', lw=0.8)      # to R2
line([(24, 40.0), (36.5, 40.0), (36.5, 44.0), (39.5, 44.0)], color=ACC, ls='--', lw=0.8)  # to R1

# ---------------- laptop / data logger: a proper block with three connections ----------------
LX, LY, LW, LH = 54, 27, 26, 13.5
box(LX, LY, LW, LH, round_=False, lw=1.0)
ax.text(LX + LW / 2, LY + LH - 1.4, 'Laptop — data logger', fontsize=6.4, ha='center', va='center', fontweight='bold')
ax.text(LX + 1.2, LY + LH - 3.6, '• drive telemetry every 3 s + capture ring\n   1.6–80 ms  (RS485, 9600)', fontsize=5.3, ha='left', va='top', linespacing=1.25)
ax.text(LX + 1.2, LY + LH - 7.4, '• flow meter, Modbus, same RS485 bus', fontsize=5.3, ha='left', va='top')
ax.text(LX + 1.2, LY + LH - 9.6, '• relay-box commands over LAN/MQTT,\n   all time-stamped (marks.log)', fontsize=5.3, ha='left', va='top', linespacing=1.25)
# 1. RS485 to the inverter
line([(60, LY + LH), (60, 47)], color=GREY, lw=1.0); ax.text(60.8, 44, 'RS485 to the drive', fontsize=5.3, color=GREY, va='center')
# 2. RS485 to the flow-meter transmitter (below the borehole, up the right edge)
line([(72, LY), (72, 5.5), (97.5, 5.5), (97.5, 62)], color=GREY, lw=1.0)
ax.text(73, 4.7, 'RS485 (Modbus) to the flow-meter transmitter', fontsize=5.3, color=GREY, ha='left', va='top')
# 3. LAN to the relay box (dashed accent)
line([(13, 36), (13, 12.5), (66, 12.5), (66, LY)], color=ACC, ls='--', lw=0.8)
ax.text(28, 11.8, 'LAN / MQTT to the relay box', fontsize=5.3, color=ACC, ha='center', va='top')

# ---------------- well, motor, pump, delivery ----------------
line([(76, 58), (100, 58)], color=GREY, lw=1.0)                      # ground
ax.text(100.5, 56.6, 'ground', fontsize=5.2, color=GREY, va='top', ha='right')
for x in range(77, 100, 3):
    line([(x, 58), (x - 1.2, 56.8)], color=LG, lw=0.5)
ax.add_patch(Rectangle((84.5, 6), 6, 56.5, fc='#f5f5f5', ec=GREY, lw=0.9))   # borehole casing (above ground to 62.5)
ax.text(87.5, 40, 'borehole', fontsize=5.4, color=GREY, ha='center', va='center', rotation=90)
box(85, 7, 5, 9, '', round_=False, lw=0.9, fc='white')
ax.text(87.5, 11.5, 'SP 60/8\npump +\n15 kW\nmotor', fontsize=5.0, ha='center', va='center')
line([(74, 56.2), (80, 56.2), (80, 61), (84.5, 61)], lw=1.0)          # 3-phase cable to the wellhead
line([(86.2, 61), (86.2, 16)], lw=0.8)                               # down-hole cable
ax.text(81.5, 61.8, '3-phase cable U V W', fontsize=5.2, ha='center', va='bottom')
line([(88.8, 16), (88.8, 64.5), (95, 64.5), (95, 65.2)], color=BLUE, lw=1.6)     # delivery pipe
ax.text(89.6, 30, 'delivery pipe', fontsize=5.2, color=BLUE, ha='left', va='center', rotation=90)
# clamp-on transducers on the pipe at the well head
for yy in (63.0, 64.0):
    pass
ax.add_patch(Rectangle((87.9, 62.3), 1.8, 0.9, fc='white', ec=BLUE, lw=0.6)); ax.add_patch(Rectangle((87.9, 63.6), 1.8, 0.9, fc='white', ec=BLUE, lw=0.6))
ax.text(88.0, 65.4, 'clamp-on transducers', fontsize=4.4, color=BLUE, ha='right', va='bottom')
box(89, 65.2, 12, 5.6, 'ultrasonic flow meter\nclamp-on, transit-time\nModbus unit 1', fs=4.7, ec=BLUE)
arrow((95, 70.8), (95, 73.2), color=BLUE, lw=1.2)
ax.text(95, 73.6, 'to the alfalfa field\n(sprinkler irrigation)', fontsize=5.2, ha='center', va='bottom', color=BLUE)
# depth dimension
line([(92.5, 58), (92.5, 16)], color=GREY, lw=0.6); line([(91.8, 58), (93.2, 58)], color=GREY, lw=0.6); line([(91.8, 16), (93.2, 16)], color=GREY, lw=0.6)
ax.text(93.0, 45, '70 m', fontsize=5.6, color=GREY, ha='left', va='center')

# ---------------- legend / note ----------------
ax.text(1, 1.5, 'Accent: the two disturbance actuators. A shot = R2 opens one of the three strings (a third of I_sc), R1 closes the bank 0.4 s later (a resistive step scaled to the sun),\n'
        '90 s hold, bank off, string back. Drive, flow meter and laptop share one RS485 bus; the relay box is on the LAN; relay commands and drive records carry one clock.',
        fontsize=5.3, color=GREY, va='center')
fig.savefig('paper_figs/fig15_setup_schematic.png', dpi=300)
print('fig15 saved')
