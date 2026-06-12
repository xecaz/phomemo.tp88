# Phomemo / QUIN TP88 — reverse-engineering project

## Goal

Understand the **QUIN TP88** thermal tattoo-stencil printer and decode the protocol it
speaks over USB, so we can drive it ourselves (eventually from a custom **Android app**)
and stop depending on the paywalled bundled app.

This is a reverse-engineering / understanding project — **not** a CUPS/printer-setup task.

## The device (established by read-only probing)

- USB `0483:5740` (STMicro STM32 "Virtual COM Port" base descriptor), composite.
  Manufacturer `QUIN`, product `TP88`, serial `000000140000`. It is a Phomemo TP88 /
  M08F-class A4 tattoo printer (also rebadged Phomemo / LabelCreate / Zodzi).
- Interfaces:
  - `1-6:1.0` + `1-6:1.1` → CDC-ACM **virtual COM port** → `/dev/ttyACM0` (root:dialout).
    Role unconfirmed — likely vendor diagnostic/config + firmware update. **Do not write
    to it until characterized.**
  - `1-6:1.2` → USB **printer class** (bInterfaceClass 07, bidirectional) → bound to the
    `usblp` kernel driver → **`/dev/usb/lp0`** (root:lp). This is our print path.
- IEEE-1284 device ID: `CMD:XPP,XL; MDL:TP88; CLS:PRINTER; DES:LABEL PRINTER`.
  `XPP` = proprietary raster language (not ESC/POS/ZPL/PCL/PS).
- Specs: 203 dpi, A4/Letter width, ~15 mm/s, thermal, USB + Bluetooth (PC = USB only).
- The auto-created CUPS queue `TP88` is bound to "Generic Text-Only Printer" → cannot
  rasterize images → **useless for stencils; ignore it.** We talk raster straight to the device.

## Approach

Reuse **TiMini-Print** (`github.com/Dejniel/TiMini-Print`, Python, Apache-2.0) — it already
models M08F/TP88-class A4 tattoo printers (`protocol/families/luck_normal_a4.py` has a
`PaperMode.TATTOO`). It drives printers over **Bluetooth (BLE/SPP via bleak), not USB**, so
we reuse its render/encode/job-building layers and add a thin **USB transport** that writes
the (transport-agnostic) job bytes to `/dev/usb/lp0`.

Locked decisions: protocol source = reference + experiment; test prints = free (spare paper);
device access = udev rule for `0483:5740`.

## Repo layout / environment

- `TiMini-Print/` — cloned upstream (Apache-2.0; preserve attribution).
- `TiMini-Print/.venv/` — **all Python work happens in this venv.** Use `.venv/bin/python`
  and `.venv/bin/pip`, never system Python.
  - Installed: Pillow, pypdfium2, bleak, crc8, pyserial, pytest. **Skipped `python-lzo`**
    (needs `liblzo2-dev`; only used by the unrelated `v5c` compressed-job family).
  - Baseline: `383 passed` (`.venv/bin/python -m pytest -q`).
- Plan: `~/.claude/plans/i-have-a-usb-deep-quokka.md`.

### Key TiMini-Print files for us
- `timiniprint/data/printer_profiles.json`, `data/printer_detection_rules.json` — model→profile.
- `timiniprint/protocol/families/luck_normal_a4.py`, `luck_normal_core.py` — A4 tattoo recipes.
- `timiniprint/protocol/{commands,encoding,job}.py`, `timiniprint/raster.py` — byte-level job.
- `timiniprint/transport/` — transport interface (we add a USB backend here).
- `tests/fixtures/protocol_golden.json` — byte-level oracle to diff our output against.

## Device access (udev)

Needs sudo (password required in this env — run yourself). Install
`/etc/udev/rules.d/99-tp88.rules` (staged at `/tmp/99-tp88.rules`), then:
`sudo cp /tmp/99-tp88.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger`,
replug, verify `/dev/usb/lp0` is writable by your user. We write raw bytes to `/dev/usb/lp0`
(usblp handles the bulk transfer — no need to detach the kernel driver). pyusb to the bulk-OUT
endpoint of interface 2 is the fallback if usblp misbehaves.

## Important caveat: TP88 is NOT auto-supported upstream

TiMini-Print's README lists `M08F and clones: TP81, TP84, TP85, TP86, TP87, TP88`
under **"Potential future support"** — i.e. recognized but not implemented. Its BLE
detection has no `TP88` rule. So cloning gives us the right *family* and pipeline, but
**the exact TP88 profile (compressed vs raw, width, density, paper/init handshake) is
what we confirm by experiment.** Closely related, *supported* A4 tattoo models in the
same `luck_normal_a4` family: TPA46, ITP05/06, DP_A4, APA46Y, A40/A41/A42.

## Decoded protocol (byte-level, from built payloads)

> **⚠️ Verified against the official driver (2026-06-12).** The official QY Linux driver is
> a local reference at `QY_Printer-2.1.0.3/` (gitignored; `c/rastertoM08F.cxx` + 75 PPDs).
> Cross-check results — see **`docs/tp88-protocol.md`** (authoritative native protocol),
> **`docs/tp88-models.md`** + **`src/qy_models.json`** (146-model registry + auto-detect),
> **`src/qy_native.py`** (native command constants):
> - The `10 ff …` wrapper + `1b 4a 90` feed footer below are the **TiMini `luck_normal`
>   dialect we emit** — the firmware accepts it, but it is **not** the native protocol. Native
>   = `1F 11 xx` control cmds (density `1F 11 02`, compression-off `1F 11 35 00`, antiwrinkle
>   `1F 11 88`, status `1F 11 09/07/11/12`) + `GS v 0`, **no `10 ff` wrapper, no feed footer**.
> - The `1f 10 00` "compressed, preferred for A4" claim below is **WRONG** — that opcode does
>   not exist; real compression is **LZO1X via `1F 11 35 01`** (other models only; TP88 uses
>   raw, confirmed: compressed fed blank).
> - **Mirror gotcha:** tattoo PPDs default `OemMirror=ON`; the vendor flips stencils
>   horizontally (applied face-down). Our output is un-mirrored → flipped vs vendor. Fixed via
>   `tp88_print.py --mirror` (default on for tattoo).
> - `ttyACM0` has **no print role** — the driver reads status in-band over the usblp
>   back-channel. USB `MDL:` field = authoritative model id for auto-detect.

Family `luck_normal_a4`, A4 width **1728 device dots = 216 bytes/line** (`paper`=1600
usable), 200 dpi. Job layout:
- **Header / init**: `10 ff 10 00 01  10 ff f1 03 00 …  1f 80 01 10` (Luck-normal wrapper).
- **Raster**, two encodings:
  - `luck_normal_raw`: standard ESC/POS **`GS v 0`** → `1d 76 30 00 d8 00 81 00 <data>`
    (`d8 00` = 216 bytes/line LE; next 16-bit = line count). ~27.9 KB for a 1600×120 page.
  - `luck_normal_compressed` (tattoo profiles): Luck opcode `1f 10 00 d8 00 81 00 <rle>` —
    same dims, compresses 27.9 KB → ~2 KB. Preferred for A4 rasters.
- **Footer / feed+end**: `… 1b 4a 90` (ESC J, feed 0x90 dots) `10 ff f1 45`.
- Grayscale (`gray4`/`gray8`) supported by the family for shading, not just 1-bit.

## Our code (added to the cloned repo; upstream is Apache-2.0)

- `TiMini-Print/tp88_usblp.py` — `UsblpConnector`/`UsblpConnection`: writes
  `ProtocolJob.payload` to `/dev/usb/lp0` in profile stream chunks (mirrors
  `SerialConnection`, minus pyserial termios). One-way pipe (no runtime/notify channel).
- `TiMini-Print/tp88_print.py` — CLI: build a job from an image/PDF/txt for a chosen
  profile, then `--dump OUT` (offline, no hardware) and/or `--send` to the printer.
  `--list-profiles` shows TP88 candidates. Run from the repo dir with `.venv/bin/python`.

Quick checks (offline, verified working):
```
cd TiMini-Print
.venv/bin/python tp88_print.py --list-profiles
.venv/bin/python tp88_print.py /tmp/tp88_test.png --profile luck_a4_compressed_tattoo --dump /tmp/job.bin
```

## Device access status (UNRESOLVED — resume here)

The udev rule `/etc/udev/rules.d/99-tp88.rules` is installed and **matches**, but
`/dev/usb/lp0` still has **no ACL for xecaz** (still root:lp 0660). Diagnosis:
- `/dev/ttyACM0` DID get `user:xecaz:rw-` via uaccess; `/dev/dri/card0` too. So uaccess
  works on this seat (seat0, wayland, active).
- `/dev/usb/lp0` has the `uaccess` tag but the ACL was never applied because our rule is
  numbered **99** — it adds `TAG+="uaccess"` *after* `73-seat-late.rules` already ran the
  `uaccess` builtin. CDC-ACM ports are uaccess-tagged by a stock rule (hence ttyACM0
  worked); the usblp char device is not, so only our too-late rule tags it.

Resume options (in order of preference):
1. **User is logging out/in** — logind re-applies uaccess ACLs to uaccess-tagged devices
   on session activation, and lp0 now has the tag, so this may grant access. First check
   on return: `getfacl /dev/usb/lp0 | grep xecaz` or `[ -w /dev/usb/lp0 ] && echo ok`.
2. **Persistent correct fix** (staged at `/tmp/72-tp88.rules`): numbered 72 (before
   seat-late) and grants via the `plugdev` group (xecaz is a member). Install:
   `sudo cp /tmp/72-tp88.rules /etc/udev/rules.d/ && sudo rm -f /etc/udev/rules.d/99-tp88.rules && sudo udevadm control --reload && sudo udevadm trigger`, then **replug**.
3. **Immediate, non-persistent**: `sudo setfacl -m u:xecaz:rw /dev/usb/lp0` (instant).

## First test print (once /dev/usb/lp0 is writable)

```
cd TiMini-Print
.venv/bin/python tp88_print.py /tmp/tp88_test.png --profile luck_a4_compressed_tattoo --send
```
`/tmp/tp88_test.png` is a 1600×120 test strip (border + diagonals + text). If nothing
prints or output is garbled, try `--profile luck_a40` (raw GS v 0) and other tattoo
profiles; tune `--blackening 1..5`, `--paper-mode tattoo|plain`. Then write the spec
(task 6) from what works.

## ✅ CONFIRMED WORKING (2026-05-30)

The TP88 prints correctly via USB with:
```
.venv/bin/python tp88_print.py IMAGE.png --profile luck_a40 --paper-mode tattoo --blackening 5 --send
```
- Profile **`luck_a40`**, encoding **`luck_normal_raw`** (ESC/POS `GS v 0`), 1728 dots,
  paper-mode **tattoo**, blackening 5. Test strip printed full-width, correct geometry.
- The **`luck_normal_compressed`** encoding (`luck_a4_compressed_tattoo*`) fed **blank** —
  the TP88 firmware does not decode it. **Use raw.**
- `tp88_print.py` default profile is now `luck_a40`.
- Full byte-level spec written to `TiMini-Print/docs/tp88-protocol.md`.

Real-image test: `tinytestprint.png` (916×312, project root) printed **excellently** with
the same config. The render pipeline scales/places automatically; raw `GS v 0` payload
was 126184 bytes.

Access: **RESOLVED & persistent.** `/etc/udev/rules.d/72-tp88.rules` (plugdev group) is
installed; `/dev/usb/lp0` comes up `root:plugdev` 0660, writable by xecaz across replugs.
The old `99-tp88.rules` was removed. (History: the 99 rule's `uaccess` tag applied too
late — after `73-seat-late.rules` ran the uaccess builtin — so the ACL never landed on
the usblp node; the 72-prefixed plugdev rule sidesteps uaccess timing entirely.)

## Sierpiński full-page test (2026-05-31) — REVISIT SOON

A "future app idea" probe: render a Sierpiński gasket at native device resolution and
print it. Generator added: **`tools/make_sierpinski.py`** (run with the venv). Outputs a
1-bit PNG at device pixels (no resampling); print via the confirmed path
(`luck_a40` / tattoo / blackening 5 / `--no-dither`).

Key flags: `--equilateral` (true 60° triangle, `height = base·√3/2`, centered),
`--depth N`, `--line-width W` (default 2), `--fill` (solid triangles, old look).
Default canvas 1600×2338 (usable width × A4 height @ 200 dpi).

Lessons learned (all confirmed visually from generated PNGs; **print quality TBD on return**):
- **Aspect**: a page-*filling* triangle (base 1600, height 2338) is stretched ~1.69× and
  looks wrong. Use `--equilateral` for correct proportions (span 1591×1379).
- **Lines, not fills**: solid-filled triangles merge fine sub-structure into chunky blobs.
  Draw outlines (default now) with `--line-width 2`. Filled mode wastes ink on a stencil.
- **The depth ↔ line-width ↔ 200 dpi floor**: with 2 px lines the smallest triangle must
  stay big enough to keep a white gap. depth 8 → ~6.2 px leaf edge = practical limit for
  2 px. Deeper (depth 9, ~3 px) needs `--line-width 1`. `--depth 7` (~12 px) is the safe
  fallback if the innermost triangles fill in on paper.
- Last sent: `/tmp/sierpinski_lines.png` (equilateral, depth 8, lw 2), payload 323 KB.

**Open question to revisit**: did the depth-8 / 2 px print keep the smallest triangles
crisp, or did the innermost ones fill in? That answer sets the real detail floor for the
Android app's render path.

## ✅ BLUETOOTH CONFIRMED WORKING (2026-06-12)

Full A4 raster printed over **BLE GATT** — same job bytes as USB. Tool: `src/tp88_ble.py`.
Full writeup: `docs/tp88-bluetooth.md`. Key facts:
- Print path is **BLE** (not the advertised Classic SPP/HCRP): service `0xff00`, write char
  `0xff02` (write-without-response), notify `0xff03`.
- **Bonding is mandatory** — unbonded links are dropped after ~1 s (this is the "won't
  pair/print" symptom). Fix: `ControllerMode = le` in main.conf (BlueZ otherwise tries
  BR/EDR → `br-connection-not-supported`), `bluetoothctl pairable on`, a Just-Works agent
  (`bt-agent -c NoInputNoOutput`), then `pair`. Leave **untrusted** so BlueZ doesn't
  auto-reconnect and steal the advertisement. Bond survives printer power-cycle.
- **Speed (resolved):** negotiate MTU 512 via `client._backend._acquire_mtu()` (BlueZ
  defaults to 23!) → 509-byte packets. Pace to a fixed `--rate-kbps` **12** (≈ the head's
  sustained drain): full A4 page in **~29 s**, acks track 1:1, stable. The head bursts
  faster briefly then throttles, so >12 either stutters (fixed) or stalls (ack-paced);
  `0x0101` is a reception ack that lags under load, so ack-gating is unreliable — fixed
  rate wins.
- **Android note:** bonding is firmware-enforced (any client must pair once), but the
  BlueZ-specific hacks (LE-only mode, bt-agent, pairable, untrust) are NOT needed on
  Android — its BLE stack bonds natively with one tap. The protocol (ff00/ff02/ff03,
  MTU 512, 12 KB/s) carries over unchanged.

## Status

- [x] Clone TiMini-Print + venv + baseline tests pass (383 passed)
- [x] TP88 mapped to `luck_normal_a4` family; protocol decoded at byte level
- [x] USB transport adapter (`tp88_usblp.py`) + CLI (`tp88_print.py`)
- [x] Device access — persistent udev rule `72-tp88.rules` (plugdev), survives replug
- [x] **First successful print** — raw GS v 0 / tattoo / blackening 5 (test strip)
- [x] **Real image printed** — `tinytestprint.png`, looked great
- [x] `docs/tp88-protocol.md` spec written
- [x] **BLE printing** — bonded, MTU 512, ~12 KB/s; `src/tp88_ble.py` (`docs/tp88-bluetooth.md`)
- [x] **Verified vs official driver** (`QY_Printer-2.1.0.3/`) — native protocol documented,
      `1f 10 00` claim corrected, mirror gotcha found; `src/qy_native.py` constants
- [x] **Model registry + auto-detect** — `src/qy_models.json` (146 models, 3 families),
      `docs/tp88-models.md`
- [x] **App backlog** — `TODO.md` (from Google reviews; Project/scale-lock concept)
- [~] **Sierpiński full-page test** — `tools/make_sierpinski.py` written. **REVISIT detail floor.**
- [~] **Mirror fix** — `tp88_print.py --mirror` (default on for tattoo); confirm on paper.
- [ ] Future: native-protocol sender (`qy_native.py`); grayscale/line-weight tuning;
      **Android app** (reuse spec — BLE GATT ff00/ff02/ff03 or USB-OTG bulk, identical bytes)
