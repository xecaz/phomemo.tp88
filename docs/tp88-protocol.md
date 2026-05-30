# TP88 (QUIN / Phomemo, M08F-class) print protocol

Reverse-engineered and **confirmed on hardware** (2026-05-30) by driving the printer
over its USB printer-class interface from Linux. Goal: enough detail to reimplement the
print path anywhere (e.g. an Android app) without the paywalled vendor app.

## Hardware / transport

- USB `0483:5740` composite device, manufacturer `QUIN`, product `TP88`.
  - Interface 2 = USB printer class (bidirectional) → kernel `usblp` → `/dev/usb/lp0`.
    **This is the print path.** A job is a flat byte stream written to this node.
  - Interfaces 0/1 = CDC-ACM virtual COM port → `/dev/ttyACM0` (role: vendor
    diagnostic/firmware, not needed for printing; not yet characterized).
- IEEE-1284 ID: `CMD:XPP,XL; MDL:TP88; CLS:PRINTER; DES:LABEL PRINTER`.
- Also has Bluetooth (the vendor app uses it); profiles mark these models `use_spp:true`.
  The **payload below is transport-agnostic** — identical bytes over USB bulk or BT SPP.
- Print head: 203 dpi (profile dev_dpi 200), **1728 dots wide = 216 bytes/line**,
  ~1600 usable dots. ~15 mm/s.

## What works (confirmed)

- Base profile: **`luck_a40`** (TiMini-Print), family **`luck_normal_a4`**,
  encoding **`luck_normal_raw`** (ESC/POS `GS v 0`).
- Paper mode: **TATTOO**. Blackening 5 gave clean output on tattoo stencil paper.
- The **`luck_normal_compressed`** encoding (the `luck_a4_compressed_tattoo*` profiles)
  fed **blank** paper on this unit — i.e. the TP88 firmware does not decode that
  compressed raster. Use raw.

## Job byte layout (raw / `GS v 0`)

A job is: **header → (raster block)+ → footer**. Multi-byte raster dims are 16-bit
little-endian. Bit order is MSB-first per byte for this family (`lsb_first = not a4xii`,
and a4xii is false here).

```
HEADER (Luck-normal wrapper / init):
  10 ff 10 00 01            session/begin marker
  10 ff f1 03 00 00 .. 00   init block (zero-padded)
  1f 80 01 10               mode/setup
  ... (speed / energy / density / paper-mode bytes derived from profile tuning) ...

RASTER (ESC/POS GS v 0 bit image), one or more blocks:
  1d 76 30 00  xL xH  yL yH  <bitmap>
    1d 76 30 00 = GS v 0, mode 0 (normal)
    xL xH       = bytes per line, LE  → 0x00d8 = 216  (= 1728 dots / 8)
    yL yH       = number of raster lines in this block, LE
    <bitmap>    = yL..yH * 216 bytes, 1 bit per dot, MSB first, 1 = burn
  (Large pages are split into blocks; line count per block fits the 16-bit field.)

FOOTER (feed + end):
  1b 4a 90                  ESC J 0x90  → print and feed 0x90 (144) dots
  10 ff f1 45               end/finalize marker
```

Energy/density/speed come from the profile `tuning` (image energy ~10000 at blackening
5). Grayscale (`gray4`/`gray8`) is supported by the family for shading but the confirmed
path above is 1-bit (`bw1`).

## Reproduce

```
cd TiMini-Print
.venv/bin/python tp88_print.py IMAGE.png --profile luck_a40 --paper-mode tattoo --blackening 5 --send
# offline inspection of the exact bytes:
.venv/bin/python tp88_print.py IMAGE.png --profile luck_a40 --paper-mode tattoo --dump job.bin
```

The byte stream is produced by `timiniprint`'s `PrinterProtocol`/`PrintJobBuilder` for the
`luck_a40` profile; our `tp88_usblp.py` writes it to `/dev/usb/lp0` in the profile's
stream chunks. For another platform, build the same `header + GS v 0 blocks + footer` and
send it over whatever transport (USB bulk OUT on interface 2, or BT SPP).

## Open / next

- Confirm exact init/tuning bytes vs the vendor app (BT HCI snoop) if byte-perfect parity
  is needed; current raw job already prints correctly.
- Line weight: thin source strokes print thin — thicken art / use grayscale for fills.
- Characterize `/dev/ttyACM0` (likely firmware/diagnostic; do not write blindly).
