# TP88 (QUIN / Phomemo, M08F-class) print protocol

Reverse-engineered and **confirmed on hardware** (2026-05-30, USB; 2026-06-12, BLE), then
**cross-checked against the official QY Linux driver** (local reference `QY_Printer-2.1.0.3/`)
(2026-06-12). Goal: enough detail to reimplement the print path anywhere (e.g. an Android app)
without the paywalled vendor app.

There are **two byte dialects** that both print on this firmware:
- the **native QY protocol** (what the vendor driver emits) — documented first, below;
- the **TiMini `luck_normal` dialect** (what our `src/tp88_print.py` currently emits) — also
  accepted by the firmware, documented second.

The raster core (`GS v 0`, 216 bytes/line, raw) is identical in both.

## Hardware / transport

- USB `0483:5740` composite device, manufacturer `QUIN`, product `TP88`.
  - Interface 2 = USB printer class (**bidirectional**) → kernel `usblp` → `/dev/usb/lp0`.
    **This is the print path.** A job is a flat byte stream written to this node; status
    replies are read back over the same usblp **back-channel**.
  - Interfaces 0/1 = CDC-ACM virtual COM port → `/dev/ttyACM0`. **Not used for printing** —
    the driver does all status in-band over usblp, which is why we never needed ttyACM0.
- IEEE-1284 ID: `CMD:XPP,XL; MDL:TP88; CLS:PRINTER; DES:LABEL PRINTER`. The **`MDL:` field is
  the authoritative model id for USB auto-detect** (see [`tp88-models.md`](tp88-models.md)).
- **Bluetooth is BLE GATT, not SPP**: service `0xff00`, write char `0xff02`, notify `0xff03`.
  The same job bytes work over BLE. Full transport details (pairing/bonding, MTU 512, pacing)
  in [`tp88-bluetooth.md`](tp88-bluetooth.md).
- Print head: 203 dpi, **1728 dots wide = 216 bytes/line** (the official PPD declares the A4
  *page* as 595 pt → 1678 dots → 210 B/line; the head is 216 mm so 216 B/line also prints —
  the extra is margin). ~15 mm/s.

## Native QY protocol (authoritative — from `QY_Printer-2.1.0.3/c/rastertoM08F.cxx`)

The vendor's `rastertoM08F` filter drives the M08F/TP86/TP88 family. Command bytes (verbatim,
`@line`); the Python constants are mirrored in [`src/qy_native.py`](../src/qy_native.py):

| Purpose                | Bytes                               | Notes                                  |
|------------------------|-------------------------------------|----------------------------------------|
| Query paper status     | `1F 11 11`                          | → reply `1A 06 <flag>`                 |
| Query cover status     | `1F 11 12`                          | → `1A 05 <flag>`                       |
| Query serial number    | `1F 11 09`                          | → `1A 08 <15 ASCII>` (no model in it)  |
| Query firmware version | `1F 11 07`                          | → `1A 07 <maj> <min> <patch>`          |
| Antiwrinkling          | `1F 11 88 <v>`                      | Better→2, Weak→1, Close(default)→3     |
| Density / darkness     | `1F 11 02 <v>`                      | Fine→1, Medium→2, Thick→4              |
| Density max ("special")| `1F 11 37 96`                       | used for the top "Dedicated" level     |
| Compression OFF        | `1F 11 35 00`                       | **M08F/TP88 always send this**         |
| Compression ON         | `1F 11 35 01`                       | LZO1X; *other* models only, not TP88   |
| Paper type             | `1B 4E 17 <t>`                      | plain0 / tattoo1 / label2 / gap3 / cont4 |
| Print-mode block       | `1B 4E 62 0A 20 00 00 00 1E 00 01 00 02 00 06 00 C8 00 2D` | 19 bytes (sibling models) |
| **Raster (GS v 0)**    | `1D 76 30 00 <bplLE16> <hLE16> <bitmap>` | one block for the whole page      |

**Native page sequence** (M08F/TP86/TP88, `@L12190–12301`, `@L14730–14790`):
1. **Status handshake** — poll `1F 11 11` / `1F 11 12` until paper-ready & cover-closed.
2. **Antiwrinkling** `1F 11 88 <v>` (if option set).
3. **Density** `1F 11 02 <v>` (or `1F 11 37 96` for max), if Darkness ≠ Default.
4. **Mirror the bitmap** if `OemMirror` — **default ON for tattoo** (vendor flips horizontally;
   stencils are applied face-down). See the mirror gotcha below.
5. **Compression OFF** `1F 11 35 00`.
6. **Raster** `1D 76 30 00 <216 LE> <height LE>` + raw bitmap (MSB-first, threshold ≤128 = burn).
7. **No explicit feed** for M08F (firmware handles it); a final `1F 11 11` paper query.

There is **no `10 ff …` wrapper and no `1b 4a` feed footer** in the native protocol, and **no
model-id command** anywhere on the wire (serial/version carry no model).

> **Mirror gotcha:** every tattoo PPD (TP81–88, M08F-WS) sets `*DefaultOemMirror: 1`, and the
> driver flips the raster horizontally. Our pipeline prints **un-mirrored**, so our stencils
> come out **laterally flipped vs the vendor app** — fixed by `tp88_print.py --mirror`
> (default on for `--paper-mode tattoo`).

## TiMini `luck_normal` dialect (what `src/tp88_print.py` currently emits)

This is **not** the native protocol — it's TiMini-Print's `luck_normal_a4` framing, which this
firmware *also* accepts (confirmed printing). It wraps the same `GS v 0` raster in a different
header/footer. Multi-byte raster dims are 16-bit LE; bit order MSB-first.

```
HEADER (Luck-normal wrapper / init):
  10 ff 10 00 01            session/begin marker          (no analogue in the native protocol)
  10 ff f1 03 00 00 .. 00   init block (zero-padded)
  1f 80 01 10               mode/setup
  ... (speed / energy / density bytes derived from profile tuning) ...

RASTER (ESC/POS GS v 0 bit image), one or more blocks:   <-- identical to native
  1d 76 30 00  xL xH  yL yH  <bitmap>
    xL xH = bytes per line, LE → 0x00d8 = 216 (= 1728 dots / 8)
    yL yH = raster lines in this block, LE
    <bitmap> = lines * 216 bytes, 1 bit/dot, MSB first, 1 = burn

FOOTER (feed + end):
  1b 4a 90                  ESC J 0x90 → feed 0x90 dots    (native protocol sends no feed)
  10 ff f1 45               end/finalize marker
```

Profile `luck_a40`, encoding `luck_normal_raw`. The **`luck_normal_compressed`** encoding
(`luck_a4_compressed_tattoo*`) fed **blank** — TiMini's RLE is not what this firmware decodes
(the firmware's own compression is LZO1X via `1F 11 35 01`, used only by other models). Use raw.

## Reproduce

```
# build + send (USB), or --dump for offline byte inspection:
.venv/bin/python src/tp88_print.py IMAGE.png --profile luck_a40 --paper-mode tattoo --blackening 5 --send
.venv/bin/python src/tp88_print.py IMAGE.png --profile luck_a40 --paper-mode tattoo --dump job.bin
# over BLE (same bytes): src/tp88_ble.py send job.bin   (see tp88-bluetooth.md)
```

## Open / next

- A **native-protocol sender** (status handshake → `1F 11 02` density → `1F 11 35 00` → GS v 0,
  no luck_normal wrapper) — cleaner for the Android port. Constants ready in `qy_native.py`.
- Confirm whether the 15-char serial (`1F 11 09`) carries a model prefix (BLE auto-detect aid).
- Line weight: thin source strokes print thin — thicken art / use grayscale for fills.
