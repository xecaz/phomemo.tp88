"""Drive the TP88 over USB (/dev/usb/lp0) using TiMini-Print's protocol pipeline.

Examples:
    # Build a job and dump the raw bytes (no hardware needed) for inspection:
    python tp88_print.py image.png --profile luck_a4_compressed_tattoo --dump out.bin

    # Send a job to the printer over USB:
    python tp88_print.py image.png --profile luck_a4_compressed_tattoo --send

    # List candidate profiles:
    python tp88_print.py --list-profiles

Profile is selected manually because TP88/M08F is not yet auto-detected upstream;
the closest supported family is luck_normal_a4 (1728-dot A4 tattoo printers).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import _bootstrap  # noqa: F401  (puts the TiMini-Print submodule on sys.path)
from timiniprint.devices import PrinterCatalog
from timiniprint.printing.builder import PrintJobBuilder
from timiniprint.printing.runtime.prepare import prepare_connection_runtime
from timiniprint.printing.settings import PrintSettings
from timiniprint.protocol import PaperMode

from tp88_usblp import DEFAULT_DEVICE_PATH, UsblpConnector

# Profiles for the TP88 (A4 tattoo, luck_normal_a4 family).
# CONFIRMED on hardware: luck_a40 (raw GS v 0) prints correctly with --paper-mode tattoo.
# The luck_normal_compressed encodings (luck_a4_compressed_tattoo*) fed BLANK paper on
# this unit, so raw is first/default. Others kept as fallbacks for tuning.
CANDIDATE_PROFILES = [
    "luck_a40",                       # raw GS v 0 — confirmed working
    "luck_a41_luckp",                 # raw GS v 0 variant
    "luck_a42_luckp",                 # raw GS v 0 variant
    "luck_a4_compressed_tattoo",      # compressed — fed blank on TP88
    "luck_a4_compressed_tattoo_96",   # compressed — untested
]

PAPER_MODES = {m.name.lower(): m for m in PaperMode}


def build_job(args, catalog):
    device = catalog.device_from_profile(args.profile)
    settings = PrintSettings(
        blackening=args.blackening,
        feed_padding=args.feed_padding,
        rotate_90_clockwise=args.rotate,
        dither=not args.no_dither,
        paper_mode=PAPER_MODES.get(args.paper_mode) if args.paper_mode else None,
    )
    job = PrintJobBuilder(device, settings=settings).build_from_file(args.file)
    return device, job


async def send_job(device, job, path):
    connection = await UsblpConnector(path).connect(device)
    try:
        await prepare_connection_runtime(device, connection)
        await connection.send(job)
    finally:
        await connection.disconnect()


def main(argv=None):
    p = argparse.ArgumentParser(description="Drive the TP88 over USB via TiMini-Print")
    p.add_argument("file", nargs="?", help="image/PDF/txt file to print")
    p.add_argument("--profile", default=CANDIDATE_PROFILES[0],
                   help=f"profile key (default: {CANDIDATE_PROFILES[0]})")
    p.add_argument("--device", default=DEFAULT_DEVICE_PATH, help="USB char device path")
    p.add_argument("--paper-mode", choices=sorted(PAPER_MODES), help="override paper mode")
    p.add_argument("--blackening", type=int, default=3, help="darkness 1-5 (default 3)")
    p.add_argument("--feed-padding", type=int, default=12, help="trailing feed dots")
    p.add_argument("--rotate", action="store_true", help="rotate 90° clockwise")
    p.add_argument("--no-dither", action="store_true", help="threshold instead of dither")
    p.add_argument("--dump", metavar="OUT", help="write payload bytes to file (no printing)")
    p.add_argument("--send", action="store_true", help="send the job to the printer")
    p.add_argument("--list-profiles", action="store_true",
                   help="list candidate TP88 profiles and exit")
    args = p.parse_args(argv)

    catalog = PrinterCatalog.load()

    if args.list_profiles:
        for key in CANDIDATE_PROFILES:
            prof = catalog.require_profile(key)
            print(f"{key:30} {prof.default_protocol_family.value:16} "
                  f"{prof.default_image_pipeline.encoding.value:24} "
                  f"print={prof.print_size}dots dpi={prof.dev_dpi}")
        return 0

    if not args.file:
        p.error("a file is required unless --list-profiles is given")
    if not args.dump and not args.send:
        p.error("choose --dump OUT (offline) and/or --send (to printer)")

    device, job = build_job(args, catalog)
    print(f"profile={device.profile.profile_key} family={device.protocol_family.value} "
          f"encoding={device.image_pipeline.encoding.value} payload={len(job.payload)} bytes",
          file=sys.stderr)

    if args.dump:
        with open(args.dump, "wb") as fh:
            fh.write(job.payload)
        print(f"wrote {len(job.payload)} bytes to {args.dump}", file=sys.stderr)

    if args.send:
        asyncio.run(send_job(device, job, args.device))
        print(f"sent to {args.device}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
