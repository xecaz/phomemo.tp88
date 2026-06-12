"""Native QY/Phomemo print-protocol command vocabulary (M08F / TP88 family).

Reference constants extracted **verbatim** from the official QY Linux driver vendored at
`QY_Printer-2.1.0.3/c/rastertoM08F.cxx` (command arrays @L11347-11363; M08F/TP86/TP88
StartPage @L12190-12301; raster-out @L14730-14790; mirror @L14152). This is the *native*
protocol the vendor app/driver speaks — distinct from the TiMini `luck_normal` dialect that
`tp88_print.py` currently emits (which the firmware also accepts). See
`docs/tp88-protocol.md` and `docs/tp88-bluetooth.md`.

This module is documentation-as-code: a single source of truth for the byte vocabulary so a
future native encoder (or the Android app) doesn't have to re-derive it. It has no side
effects and does not change the existing print path.

Transport note: identical bytes go to `/dev/usb/lp0` (USB) or the BLE `ff02` characteristic.
Status replies come back over the usblp back-channel (USB) or the `ff03` notify (BLE).
"""
from __future__ import annotations

# --- Control commands (1F 11 xx family + 1B 4E xx) -------------------------------------
COMPRESSION_OFF = bytes([0x1F, 0x11, 0x35, 0x00])  # M08F/TP88 always send this (raw raster)
COMPRESSION_ON = bytes([0x1F, 0x11, 0x35, 0x01])   # LZO1X; used by S821/M04S/P832Pro/Q302/S822
DENSITY_SPECIAL = bytes([0x1F, 0x11, 0x37, 0x96])  # max darkness ("Dedicated")

# Print-mode block (19 bytes) and paper-type command, used by sibling models.
MODE_BLOCK = bytes([0x1B, 0x4E, 0x62, 0x0A, 0x20, 0x00, 0x00, 0x00, 0x1E, 0x00,
                    0x01, 0x00, 0x02, 0x00, 0x06, 0x00, 0xC8, 0x00, 0x2D])
PAPER_TYPE_CMD = bytes([0x1B, 0x4E, 0x17, 0x00])   # last byte = paper type (see PAPER_TYPE)

# --- Status / identity queries (request -> response). Responses are `1A <subcode> [payload]`.
# IMPORTANT: none of these return a model identifier; model identity must come from the USB
# IEEE-1284 MDL field, the BLE advertised name, or the user. See docs/tp88-models.md.
QUERY_PAPER = bytes([0x1F, 0x11, 0x11])    # -> 1A 06 <paper-present flag>
QUERY_COVER = bytes([0x1F, 0x11, 0x12])    # -> 1A 05 <cover-open flag>
QUERY_SERIAL = bytes([0x1F, 0x11, 0x09])   # -> 1A 08 <15 ASCII chars>
QUERY_VERSION = bytes([0x1F, 0x11, 0x07])  # -> 1A 07 <major> <minor> <patch>
QUERY_READY = bytes([0x1F, 0x11, 0x43])    # -> 1A 0F <ready flag>

# Density: PPD "Darkness" choice -> 1F 11 02 <value> (or DENSITY_SPECIAL for max).
DENSITY_BY_DARKNESS = {0: 0x01, 1: 0x02, 2: 0x04}  # Fine, Medium, Thick; 3 -> DENSITY_SPECIAL

# Antiwrinkling (TP86/87/88; transfer-paper anti-curl): PPD choice -> 1F 11 88 <value>.
ANTIWRINKLE_BY_CHOICE = {0: 0x02, 1: 0x01, 2: 0x03}  # Better, Weak, Close(default)

# Paper type: 1B 4E 17 <type>.
PAPER_TYPE = {"plain": 0x00, "tattoo": 0x01, "label": 0x02, "gap": 0x03, "continuous": 0x04}


def density_cmd(darkness: int) -> bytes:
    """Build the density command for a PPD Darkness level (0=Fine,1=Medium,2=Thick,3=max)."""
    if darkness == 3:
        return DENSITY_SPECIAL
    return bytes([0x1F, 0x11, 0x02, DENSITY_BY_DARKNESS[darkness]])


def antiwrinkle_cmd(choice: int) -> bytes:
    """Build the antiwrinkling command for a PPD Antiwrinkling choice (0/1/2)."""
    return bytes([0x1F, 0x11, 0x88, ANTIWRINKLE_BY_CHOICE[choice]])


def paper_type_cmd(kind: str) -> bytes:
    """Build the paper-type command (kind in PAPER_TYPE)."""
    return bytes([0x1B, 0x4E, 0x17, PAPER_TYPE[kind]])


def gsv0_header(bytes_per_line: int, height_lines: int) -> bytes:
    """ESC/POS GS v 0 raster header: 1D 76 30 00 <bytesPerLine LE16> <height LE16>.

    Followed immediately by the raw 1-bit bitmap (MSB-first, threshold <=128 = black),
    bytes_per_line * height_lines bytes. For A4 the head is 216 bytes/line (1728 dots).
    """
    if not (0 <= bytes_per_line <= 0xFFFF and 0 <= height_lines <= 0xFFFF):
        raise ValueError("width/height must fit in 16 bits")
    return bytes([0x1D, 0x76, 0x30, 0x00,
                  bytes_per_line & 0xFF, (bytes_per_line >> 8) & 0xFF,
                  height_lines & 0xFF, (height_lines >> 8) & 0xFF])


# Native M08F/TP88 page sequence (order the driver emits), for reference:
#   1. status handshake: poll QUERY_PAPER / QUERY_COVER until ready
#   2. antiwrinkle_cmd(...)        (if option set)
#   3. density_cmd(...)            (if Darkness != Default; else firmware default)
#   4. [mirror the bitmap if OemMirror — default ON for tattoo]
#   5. COMPRESSION_OFF
#   6. gsv0_header(bytes_per_line, height) + raw bitmap
#   7. no explicit feed for M08F (firmware handles it); final QUERY_PAPER
STARTPAGE_ORDER = (
    "status-handshake", "antiwrinkle?", "density?", "mirror?", "compression-off",
    "gsv0+bitmap", "final-paper-query",
)
