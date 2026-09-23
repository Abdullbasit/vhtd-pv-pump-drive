# Data and code for "Field-Validated Voltage-Headroom Torque Droop for Riding Through DC-Link Collapse in PV-Direct Sensorless Pump Drives"

A. H. Ahmed, B. M. Saied, Y. M. Ameen — College of Engineering, University of Mosul.

Everything the paper's Data Availability statement refers to is in this tree:
the firmware that ran on the drive, the binaries that were actually flashed,
the raw instrument records of every test, the scripts that turn those records
into the figures, and the hardware design files.

The plant is a 22 kW IGBT inverter of our own design driving a 15 kW
submersible set — a Chetak 6C-20A motor on an eight-stage Marshal Gold SP 60 —
70 m down a well, supplied directly from a 21.96 kWp LONGi Hi-MO 7 array with
no battery.

## Reproducing a figure

    pip install numpy matplotlib pandas
    python tools/fig02_iv.py          # writes figures/fig02_iv.png

The scripts read the logs in `logs/` by date and write into `figures/`. They
need no drive and no network.

## Where every figure comes from

| fig | file | script | data |
|---|---|---|---|
| 1 | `fig01_block.png` | — | drawing, no data |
| 2 | `fig_capture_chain.png` | — | drawing, no data |
| 3 | `fig_cpl_loop.png` | — | drawing, no data |
| 4 | `fig_steps_5_10kW.png` | `tools/fig_ab_pairs.py` | `logs/20260910/ring/ring_105802.csv`, `ring_111527.csv` |
| 5 | `fig14_E2_vf_vs_vhtd.png` | `tools/e2_vf_log.py` output, plotted | `logs/20260914_e2/` |
| 6 | `fig02_iv.png` | `tools/fig02_iv.py` | `logs/20260910/solar_day_20260910.csv` |
| 7 | `fig13_B13_isr_rate_collapse.png` | script not retained | frozen trip ring of B13, `logs/20260914/ring/` (1.6 ms) |
| 8 | `fig_ab_B3_A6.png` | `tools/fig_ab_pairs.py` | `logs/20260910/ring/` (B3 and A6 pulls) |
| 9 | `fig_vmargin.png` | `tools/fig_vmargin.py` | `logs/20260910/solar_day_20260910.csv` |
| 10 | `fig03_cloud_edge_20260905.png` | script not retained | `logs/20260905/solar_day_20260905.csv` |
| 11 | `fig04_dawn_probes.png` | `tools/paper_figs.py` | `logs/20260908/` |
| 12 | `fig05_limit_cycle.png` | `tools/fig05_limit_cycle.py` | `logs/20260908/ring/ring_065[3-8]*.csv` |
| 13 | `fig16_cloudy_day_20260911.png` | `tools/fig16_cloudy_day.py` | `logs/20260911/solar_day_20260911.csv`, `ring/index.csv` |
| 14 | `fig12_A12_observer_through_shed.png` | script not retained | ring of shot A12, `logs/20260914/ring/` (40 ms) |
| 15 | `fig16_setup_composite.png` | `tools/fig_setup_composite.py` | photographs + `fig15_setup_schematic.py` |

Three figures were plotted before the figure scripts were kept under version
control. Their data files are named above, so they can be redrawn; the missing
piece is the plotting code, not the measurement.

## Where every table comes from

| table | what it is | data |
|---|---|---|
| I | representative prior work | literature only |
| II | plate data of the motor and the pump | manufacturer plates, transcribed |
| III | every FOC shot | `logs/2026091[014]/marks.log`, `pair.log` |
| IV | the two-axis matrix | the same, the single-disturbance shots |
| V | every V/f shot | `logs/20260914_e2/` |
| VI | the four arms compared | `logs/2026091[014]/`, both firmwares |
| VII | flow-metered yield blocks | `logs/20260914/`, `tools/yield_block.py` |
| VIII | the complete shot log | `logs/2026091[014]/marks.log`, `pair.log` |

**The shot tallies in the paper can be checked directly.** `marks.log` is the
relay box's own record: every command it received, time-stamped on the same
clock as the drive log, with the state of the drive before the disturbance and
its outcome after. Counting the `COMBINED` marks of 2026-09-10, 09-11 and
09-14 gives 14 shots with the droop enabled and 11 with it disabled, which is
the 0/14 against 10/11 reported in Section X. The eleventh droop-off shot, B9,
did not trip; `marks.log` shows why, and the paper says so.

## The tree

    firmware/
      source/         pointer to the firmware source (FOC: repository root; V/f: hs300_src_0826_ota)
      foc_binaries/   FOC app images by CRC-32: foc_F852A2A6 (r1), foc_40E27437 (r2), foc_r3_18E22A85 (r3)
      vf_binaries/    vf_baseline_D2E21DF2, vf_retreat_BC331C8F
      bootloader/     OTA bootloader 18274D72 (.hex/.bin at 0x08000000); apps link at 0x08001000
    hardware/
      schematics/     MCU, gate drivers, measurement, plus ERRATA.txt
      gerber/         Gerber manufacturing files
      bom_cpl_jlcpcb/ bill of materials and component placement, JLCPCB format
    logs/
      2026MMDD/       solar_day_*.csv  3 s telemetry of the whole day
                      marks.log        relay box commands and shot outcomes
                      cmd.log          logger command echo
                      pair.log         the unattended pair script
                      ring/            capture-ring pulls and frozen trip rings; index.csv lists them
      20260914_e2/    the V/f arms: polled logs of every shot and the yield blocks
    relay_box/        ESP32 four-relay box firmware
    tools/            logging, OTA, relay control, the pair script, the V/f loggers, the figure scripts
    dashboard/        source of the interactive record, page_template.html + per-day JSON
    figures/          every figure of the manuscript as PNG

Verify a binary against its name:

    python -c "import zlib;print('%08X'%(zlib.crc32(open('firmware/foc_binaries/foc_r3_18E22A85.bin','rb').read())&0xffffffff))"

`MDK-ARM/build/VERSIONS.md` in the firmware repository carries one row per
build — timestamp, board, CRC-32, size, a digest of the sources that fed it,
and what changed — so any image here can be traced to the code that produced
it.

## Before you run the relay box

The WiFi credentials and the OTA password in
`relay_box/esp_relay/src/main.cpp` and `platformio.ini` are placeholders
(`SSID_1`, `PASSWORD_1`, `SET_YOUR_OWN`). Put your own in before building.

## Licence

Code (firmware, tools, relay box): MIT — see `LICENSE`.
Data (logs, figures, hardware files): CC BY 4.0 — see `LICENSE-data`.

Attribution: cite the paper, and cite this deposit by its DOI.

## Citing

> A. H. Ahmed, B. M. Saied and Y. M. Ameen, "Field-Validated Voltage-Headroom
> Torque Droop for Riding Through DC-Link Collapse in PV-Direct Sensorless Pump
> Drives", [journal], [year]. Data and code: [DOI].
