# phomemo-tp88

Reverse-engineering and a working Linux driver for the **QUIN / Phomemo TP88** thermal
tattoo-stencil printer (an M08F-class A4 unit, 203 dpi, 1728-dot head), so it can be
driven without the paywalled vendor app — and as the basis for a future Android app.

**Status: working.** Real images print correctly over USB. See
[`docs/tp88-protocol.md`](docs/tp88-protocol.md) for the byte-level protocol.

## How it works

The TP88 exposes a USB printer-class interface (kernel `usblp` → `/dev/usb/lp0`). Its
raster language is a Luck-normal wrapper around standard ESC/POS `GS v 0` (216 bytes/line
= 1728 dots). Rather than re-derive the whole stack, this repo reuses
[TiMini-Print](https://github.com/Dejniel/TiMini-Print) (vendored as a git submodule) for
rendering and job building, and adds:

- [`src/tp88_usblp.py`](src/tp88_usblp.py) — a USB printer-class transport that writes a
  `ProtocolJob` to `/dev/usb/lp0` (TiMini-Print itself only ships Bluetooth/serial).
- [`src/tp88_print.py`](src/tp88_print.py) — a CLI: render an image/PDF/text and dump the
  bytes or send them to the printer.

TiMini-Print lists the TP88 only under "potential future support", so the exact profile
was confirmed by experiment: **`luck_a40`** (raw `GS v 0`) prints; the compressed tattoo
encoding fed blank paper.

## What we found about the TP88

- **USB identity:** `0483:5740` (STMicro STM32 VCP base), composite device, mfr `QUIN`,
  product `TP88`. IEEE-1284 ID: `CMD:XPP,XL; MDL:TP88; CLS:PRINTER; DES:LABEL PRINTER` —
  `XPP` is a proprietary raster language (not stock ESC/POS/ZPL/PCL/PS).
- **Two interfaces:** a USB **printer-class** interface (→ `usblp` → `/dev/usb/lp0`, the
  print path) and a **CDC-ACM** virtual COM port (→ `/dev/ttyACM0`, role uncharacterized —
  likely vendor diagnostic/firmware; we don't write to it).
- **Family & geometry:** matches TiMini-Print's `luck_normal_a4` family — **1728 device
  dots wide = 216 bytes/line**, 200/203 dpi, ~1600 usable dots.
- **Encoding (key result):** the printer decodes the **raw `GS v 0`** raster
  (`luck_normal_raw`, profile `luck_a40`). The **compressed** variant
  (`luck_normal_compressed`, the `luck_a4_compressed_tattoo*` profiles) made it **feed
  blank paper** — so this firmware does not implement that compression.
- **Working settings:** `--paper-mode tattoo --blackening 5` printed cleanly on tattoo
  stencil paper; geometry was full-width and correctly oriented.
- **Job shape:** Luck-normal header → one or more `1d 76 30 00 <bytes/line LE> <lines LE>`
  raster blocks → `1b 4a 90` feed + `10 ff f1 45` end. Full detail in
  [`docs/tp88-protocol.md`](docs/tp88-protocol.md).
- **Transport-agnostic:** these are the same bytes the vendor app would send over
  Bluetooth SPP, so the spec maps directly to a future Android app (USB-OTG bulk or BT).

## What TiMini-Print provides vs. what we added

- **TiMini-Print (submodule, Apache-2.0):** image/PDF/text rendering, the `luck_normal_a4`
  protocol family + `GS v 0` job building, profile catalog, and Bluetooth/serial transports.
- **This repo (ours, MIT):** the USB `usblp` transport TiMini-Print lacks, a TP88-focused
  CLI, the confirmed TP88 profile/settings, the udev access rule, and the protocol spec.

## Setup

```bash
git clone --recursive <this-repo-url> phomemo.tp88
cd phomemo.tp88
# or, if already cloned without --recursive:
git submodule update --init

python3 -m venv .venv
.venv/bin/pip install -r TiMini-Print/requirements.txt   # python-lzo is optional, skip if it fails
```

### Device access (udev)

`/dev/usb/lp0` is root-owned by default. Install the rule (grants the `plugdev` group,
which your user is typically in) and replug:

```bash
sudo cp udev/72-tp88.rules /etc/udev/rules.d/
sudo udevadm control --reload
# then unplug/replug the printer
```

## Usage

```bash
# confirmed-working print (raw GS v 0, tattoo paper, max darkness):
.venv/bin/python src/tp88_print.py examples/tinytestprint.png \
    --profile luck_a40 --paper-mode tattoo --blackening 5 --send

# inspect the exact bytes without a printer:
.venv/bin/python src/tp88_print.py examples/tinytestprint.png --profile luck_a40 --dump job.bin

# list candidate profiles:
.venv/bin/python src/tp88_print.py --list-profiles

# regenerate the synthetic test strip:
.venv/bin/python tools/make_test_strip.py tp88_test.png
```

Tuning: `--blackening 1..5` (darkness), `--paper-mode plain|tattoo|tag|black_tag|folder`,
`--rotate`, `--no-dither`. If a profile fed blank, try `luck_a41_luckp` / `luck_a42_luckp`
(also raw).

## Layout

```
src/         our transport + CLI (+ _bootstrap.py path shim)
docs/        tp88-protocol.md — byte-level protocol spec
udev/        72-tp88.rules — device access rule
tools/       make_test_strip.py — test image generator
examples/    tinytestprint.png — a sample that prints well
TiMini-Print/ git submodule (Apache-2.0) — rendering + protocol engine
CLAUDE.md    working notes / project state
```

## Credits & license

Built on [TiMini-Print](https://github.com/Dejniel/TiMini-Print) by Dejniel (Apache-2.0),
included as a submodule. Our original code is MIT (see [LICENSE](LICENSE)).
