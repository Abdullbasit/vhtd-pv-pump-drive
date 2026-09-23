# Disaster recovery copy - well_drive_15kW

Taken 20260919_194646 from COM11 at 9600 baud (rs485).
Drive state at the time: OFF, bus 604 V.

## Files

- `eeprom.bin` - raw EEPROM 0x0000..0x0226. Everything the drive was
  configured with: ADC offsets, all settings, lifetime counters, FOC store.
- `eeprom.txt` - the same decoded, so it can be read without a tool.
- `app.bin` - the application as read back out of flash.

## Putting it back

**Firmware** - flash `app.bin` with the OTA tool, plain form, app alive:

    python hs300_ota.py COM11 app.bin --rs485 --baud 9600

Do NOT pass `--no-enter` while the app answers: it skips the handover and the
board hangs until a power cycle.

**EEPROM** - there is no bulk restore, on purpose. Write back only what is
actually lost, with `SET_EE_ADDR` + `CMD_EE_WRITE16`, then `CMD_EE_APPLY_OFFS`
for the D-block or `CMD_RELOAD_EEPROM` for the rest. Note the write fence:
0x0040..0x007F and 0x0200..0x0222 refuse raw writes because a later
CMD_SAVE_SETTINGS would overwrite them - restore those with `write_setting`
plus `CMD_SAVE_SETTINGS` instead.

The FOC store at 0x0180/0x01C0 is a ping-pong pair with a sequence number and
CRC; restore BOTH blocks, or the drive will pick whichever survives.

## The machine this drive was running

FOC STORE A (0x0180)  magic 0x464F4331 ver 2 tuned 1 seq 112 crc 0x842D
  Rs 0.873000  Rr 0.300000  Lm 0.057200  Lls 0.002832  Llr 0.003766  vdead 0.0000
  plate 15.00 kW 380 V 50 Hz 34.00 A  pp 1  2900 rpm  sig 0x278101BD
FOC STORE B (0x01C0)  magic 0x464F4331 ver 2 tuned 1 seq 113 crc 0x7F2E
  Rs 0.873000  Rr 0.300000  Lm 0.057200  Lls 0.002832  Llr 0.002832  vdead 0.0000
  plate 15.00 kW 380 V 50 Hz 34.00 A  pp 1  2900 rpm  sig 0x278101BD
