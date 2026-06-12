# QY/Phomemo model registry & auto-detect

Built from the official driver (local reference `QY_Printer-2.1.0.3/`, gitignored) — 75 PPDs in `ppds/` + the
146-model installer list in `c/qyInstall.c`). The machine-readable version the app should
consume is **[`src/qy_models.json`](../src/qy_models.json)** (regenerate with
`tools/`-style parsing of the PPDs). This doc is the human summary + the auto-detect strategy.

## Three protocol families (one per CUPS filter)

Each filter is a distinct on-wire encoder; an app needs all three to cover the catalogue.

| Family (`filter`)      | Models | DPI         | Page B/line classes | Notes                                   |
|------------------------|:------:|-------------|---------------------|-----------------------------------------|
| **`rastertoM08F`**     |   53   | 203, 300    | 210, 212, 310       | A4 photo/tattoo. ESC/POS **GS v 0** raster; native control cmds in [`qy_native.py`](../src/qy_native.py). **TP81–88, M08F* live here.** |
| **`rastertolabelmxxx`**|   20   | 180,203,300 | 18, 40, 48, 71, 72  | Thermal **label** printers (M1xx/M2xx); density 1–15; cut/gap/black-mark. |
| **`rastertoD480`**     |    2   | 180         | 16                  | Receipt (D480BT, P780).                 |

75 models have a PPD; the installer lists **146** (71 are variants without their own PPD —
see `installer_models_without_ppd` in the JSON). `rastertoM08F` models:
A28x/A88x, B821, G100*, H83x, M04S, M08*, M83x, P83x, PR20, Q30x, S82x, SP20, T08*, T831,
**TP81–TP88**.

## Width = bytes/line (what the encoder declares)

The GS v 0 header carries the line width we choose (`bytesPerLine`); the firmware prints that
many bytes/line. Distinct PPD-derived widths across the catalogue: **16, 18, 40, 48, 71, 72,
210, 212, 310 B/line**. An app can pre-size buffers for these classes.

> **210 vs 216 nuance (A4 / M08F):** the PPD declares A4 = 595 pt → 1678 dots → **210 B/line**
> (what the *official* driver sends). The physical print head is **216 mm = 1728 dots = 216
> B/line**; our pipeline sends 216 and it prints correctly (the extra is margin). Either width
> works on the head — the registry records the PPD-derived value per model.

## TP8x / M08F family detail (our printer)

All 203 dpi, `rastertoM08F`, Tattoo-A4 (595×842 pt → 210 B/line page; 216 B/line head),
Darkness `0/Fine 1/Medium 2/Thick` (+Default), Antiwrinkling `0/Better 1/Weak 2/Close`, and
**Mirror Print defaults ON** (`*DefaultOemMirror: 1`) on every tattoo model:

| Model | cupsModelNumber | mirror default |
|-------|-----------------|----------------|
| TP81  | 21              | ON |
| TP82  | 831             | ON |
| TP83  | 21              | ON |
| TP84  | 848086          | ON |
| TP85  | 831             | ON |
| TP86  | 848086          | ON |
| TP87  | 848086          | ON |
| **TP88** | **848086**   | **ON** |
| M08F-WS | 21            | ON |
| M08F / M08FS | 21       | (no mirror option — non-tattoo variant) |

(TP88 shares `cupsModelNumber 848086` with TP86/TP87, so the driver treats them identically.)

## Auto-detect strategy

**There is no model-ID command on the wire** (confirmed in the driver): the status queries
return serial (`1F 11 09` → `1A 08` + 15 ASCII), firmware version (`1F 11 07` → `1A 07` + 3
bytes), and paper/cover/ready flags — **none carry a model**. The official driver itself never
auto-detects; it trusts the user-selected PPD. So identity must come from metadata, layered:

1. **USB → authoritative.** Parse the IEEE-1284 Device ID `MDL:` field (we already read
   `MDL:TP88`). Exact model, no ambiguity.
2. **BLE → advertised name.** Match the GATT device name (e.g. `TP88`) against the registry.
   Primary signal, but per field reports it can be generic/wrong, so don't trust it blindly.
3. **Serial-prefix heuristic.** Query `1F 11 09` and test whether the 15-char serial string
   carries a model prefix. *Unconfirmed* — verify the real format on a few devices; if it
   holds, it's a good BLE tiebreaker.
4. **User picker (fallback).** Offer a model list filtered by what we *can* infer (family /
   width class). Because the print protocol is identical within a `family + dpi + width` class,
   a class-correct choice prints correctly even if the exact submodel is wrong — so
   mis-detection is low-risk as long as the family/width is right.

The resolved model selects: **encoder family** (which filter's protocol), **width** (B/line),
**dpi**, **density map**, and the **mirror default** (ON for tattoo). For our TP88 over BLE,
the name match + `rastertoM08F`/216 B/line/203 dpi/mirror-on profile is what we use today.
