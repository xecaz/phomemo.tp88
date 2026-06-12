"""Drive the TP88 over **Bluetooth LE** (GATT) using bleak.

The TP88 is a dual-mode BT device but its print path is BLE GATT:
  service 0xff00 → write char 0xff02 (write-without-response), notify char 0xff03.
The bytes written to 0xff02 are the *same* job bytes as the USB path (build them with
`tp88_print.py --dump job.bin`, profile `luck_a40`).

CRITICAL: the printer terminates any **unbonded** LE link after ~1 s and rejects
acknowledged writes / notify subscription until bonded. You must pair first (one-time):

    bluetoothctl pairable on
    bt-agent -c NoInputNoOutput &          # Just-Works pairing agent (bluez-tools)
    bluetoothctl --timeout 8 scan le       # let it discover "TP88"
    bluetoothctl pair  <ADDR>              # -> Paired/Bonded: yes
    # leave it UNtrusted so BlueZ doesn't auto-reconnect and steal the advertisement:
    bluetoothctl untrust <ADDR>

Then:
    python tp88_ble.py enum                 # list GATT services/characteristics
    python tp88_ble.py send job.bin         # stream a job to the printer

Notes / findings:
  * The printer supports ATT MTU 512 (509-byte writes) but BlueZ defaults to 23 until an
    MTU exchange is triggered; this tool calls `_backend._acquire_mtu()` after connect,
    cutting a 324 KB page from ~16k writes to ~636 (the main speed win).
  * 0xff03 emits 0x0101 after *every* received packet (a reception ack, ~1:1 with writes)
    plus 0x0107 / 0x02f400 status at start. 0x0101 is NOT a drain credit, so it can't pace
    a sliding window — the printer overruns and drops the link if you send faster than it
    prints. So we pace to a target throughput (--rate-kbps); ~8 KB/s reliably completes a
    full A4 page in ~42 s.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import time

from bleak import BleakClient, BleakScanner

DEFAULT_ADDR = "9B:03:D7:07:E1:DD"
SERVICE = "0000ff00-0000-1000-8000-00805f9b34fb"
DATA_CHAR = "0000ff02-0000-1000-8000-00805f9b34fb"   # write-without-response
NOTIFY_CHAR = "0000ff03-0000-1000-8000-00805f9b34fb"  # reception acks / status


async def get_device(addr: str):
    """Find the advertising device; fall back to the raw address (bonded device that
    BlueZ already knows). A bonded+connected device does not advertise."""
    for attempt in range(2):
        dev = await BleakScanner.find_device_by_address(addr, timeout=8.0)
        if dev:
            return dev
        print(f"  scan miss {attempt + 1}/2, falling back to direct connect...")
        await asyncio.sleep(1.0)
    return addr


async def do_enum(addr: str):
    dev = await get_device(addr)
    async with BleakClient(dev, timeout=25.0) as c:
        print("CONNECTED:", c.is_connected, " MTU:", c.mtu_size)
        for s in c.services:
            print(f"[service] {s.uuid}")
            for ch in s.characteristics:
                print(f"   [char] {ch.uuid}  props={ch.properties}")


async def do_send(addr: str, path: str, rate_kbps: float, use_notify: bool):
    data = open(path, "rb").read()

    dev = await get_device(addr)
    async with BleakClient(dev, timeout=25.0) as c:
        # Negotiate a large ATT MTU (printer supports 512). Without this bleak defaults
        # to 23 -> 20-byte packets, which is ~25x slower.
        try:
            await c._backend._acquire_mtu()
        except Exception as e:
            print("MTU negotiation failed, using default:", e, flush=True)
        chunk = max(20, c.mtu_size - 3)
        nchunks = (len(data) + chunk - 1) // chunk
        # Pace to a target throughput so we don't outrun the printer's drain (it has no
        # usable flow-control credit and drops the link on overrun). delay per chunk:
        delay = chunk / (rate_kbps * 1000.0) if rate_kbps else 0.0
        print(f"CONNECTED MTU={c.mtu_size} chunk={chunk}B, {len(data)} bytes / {nchunks} "
              f"chunks, target {rate_kbps} KB/s ({delay*1000:.0f} ms/chunk)", flush=True)
        ch = c.services.get_characteristic(DATA_CHAR)
        if ch is None:
            raise SystemExit("ff02 data characteristic not found (paired & bonded?)")

        acks = {"n": 0}
        if use_notify:
            def on_notify(_h, val):
                if bytes(val) == b"\x01\x01":
                    acks["n"] += 1
            try:
                await c.start_notify(NOTIFY_CHAR, on_notify)
                print("notify ff03 enabled", flush=True)
            except Exception as e:  # needs a bonded link; fatal-ish but keep going
                print("notify enable failed (not bonded?):", e, flush=True)

        sent = 0
        t0 = time.monotonic()
        try:
            for n, i in enumerate(range(0, len(data), chunk), 1):
                await c.write_gatt_char(ch, data[i:i + chunk], response=False)
                sent += len(data[i:i + chunk])
                if delay:
                    await asyncio.sleep(delay)
                if n % 100 == 0 or n == nchunks:
                    el = time.monotonic() - t0
                    print(f"  {n}/{nchunks} chunks, {sent}/{len(data)} bytes, {el:.1f}s, "
                          f"{sent/el/1000:.1f} KB/s, acks={acks['n']}, conn={c.is_connected}",
                          flush=True)
        except Exception as e:
            el = time.monotonic() - t0
            print(f"  !! stopped at {sent}/{len(data)} bytes after {el:.1f}s: "
                  f"{type(e).__name__}: {e}", flush=True)
            raise SystemExit(1)
        print("done; waiting for trailing acks...", flush=True)
        await asyncio.sleep(3.0)


def main():
    ap = argparse.ArgumentParser(description="Drive the TP88 over Bluetooth LE (GATT).")
    ap.add_argument("--addr", default=DEFAULT_ADDR, help="printer BLE address")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("enum", help="list GATT services/characteristics")
    sp = sub.add_parser("send", help="stream a job (built by tp88_print.py --dump) to ff02")
    sp.add_argument("payload", help="raw job bytes to send")
    sp.add_argument("--rate-kbps", type=float, default=8.0,
                    help="target throughput; the printer drops the link if outrun (default 8)")
    sp.add_argument("--no-notify", action="store_true",
                    help="do not subscribe to the ff03 ack/status channel")
    args = ap.parse_args()

    if args.cmd == "enum":
        asyncio.run(do_enum(args.addr))
    else:
        asyncio.run(do_send(args.addr, args.payload, args.rate_kbps, not args.no_notify))


if __name__ == "__main__":
    main()
