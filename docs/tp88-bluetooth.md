# TP88 (QUIN / Phomemo) — Bluetooth print path

Reverse-engineered and **confirmed on hardware** (2026-06-12): a full A4 raster printed
correctly over Bluetooth LE from Linux. The job bytes are identical to the USB path
(see [`tp88-protocol.md`](tp88-protocol.md)); only the transport differs. Tool:
[`src/tp88_ble.py`](../src/tp88_ble.py) (bleak).

## Radio identity

The TP88 advertises as a **dual-mode** device but is reached over **BLE GATT**:

- BLE address `9B:03:D7:07:E1:DD`, name `TP88`, appearance `printer`, RSSI ~ -55 dBm.
- Advertised service UUIDs: `0x1101` (SPP), `0x1126` (HCRP Print), `0x1812` (HID over
  GATT), `0xaf30` (vendor). The `0x1101`/`0x1126` are **Classic** profile UUIDs declared
  in the LE advert — the chip is dual-mode — but the device is **not** in BR/EDR page scan
  (classic inquiry finds nothing), so in practice it is LE-only.
- Advertising flags `0x0A` = LE General Discoverable + "Simultaneous LE+BR/EDR", and BlueZ
  records the address type as **public**. Manufacturer data: company `0x7262` →
  `3232 7878 …` = ASCII `"22xx"` (a model/family tag).

## GATT layout (the print path)

| Handle | UUID     | Props                                  | Role                       |
|--------|----------|----------------------------------------|----------------------------|
| svc    | `0xff00` | —                                      | data service               |
| char   | `0xff02` | `write`, `write-without-response`      | **raster data sink**       |
| char   | `0xff03` | `notify`                               | reception acks / status    |

Plus the standard `0x1800` (GAP), `0x1801` (GATT), `0x180a` (Device Info) services.
(`0xaf30` is advertised but not exposed as a writable GATT service — ignore it.)

This is the well-known Phomemo `ff00/ff02/ff03` profile.

## The "won't pair" problem — and the fix

**Bonding is mandatory.** An *unbonded* LE link is dropped by the printer ~1 s after
connect (measured: connect @1.2 s → disconnect @1.5 s, idle, zero writes), and `ff02`
accepts only a few unencrypted command-writes before the link tears down; acknowledged
writes and `ff03` notify-subscribe both return ATT `Unlikely Error (0x0E)` while unbonded.
That is exactly why the vendor Android app *demands pairing before printing*.

The pairing failures people hit on Linux/BlueZ have two causes, both fixable:

1. **BlueZ tries BR/EDR first.** Because the advert declares Classic profiles + a public
   address, `Device.Connect` attempts a BR/EDR link and fails with
   `org.bluez.Error.Failed: br-connection-not-supported`, never falling back to LE.
   Fix: force the controller LE-only — set `ControllerMode = le` in
   `/etc/bluetooth/main.conf` and `systemctl restart bluetooth`.
   (This disables Classic BT for other devices until reverted. Irrelevant to an Android
   app, where the LE GATT path below is what matters.)
2. **No pairing agent / not pairable.** A bare `BleakClient.pair()` returns
   `AuthenticationFailed`, and the controller defaults to `Pairable: no`. The printer uses
   **Just-Works** pairing, which needs an agent to complete.
   Fix (one time):
   ```bash
   bluetoothctl pairable on
   bt-agent -c NoInputNoOutput &              # bluez-tools; Just-Works agent
   bluetoothctl --timeout 8 scan le           # discover "TP88"
   bluetoothctl pair  9B:03:D7:07:E1:DD        # -> "Pairing successful", Bonded: yes
   bluetoothctl untrust 9B:03:D7:07:E1:DD      # see "auto-reconnect" gotcha below
   ```

The bond persists across reconnects (and, in our testing, across a printer power-cycle —
no re-pairing needed).

### Auto-reconnect gotcha

A **trusted** bonded device is auto-reconnected by BlueZ, which holds the ACL and stops
the device advertising — then bleak's scan can't find it and a direct connect hangs.
Keep the device **untrusted** (the bond still works) so it advertises and bleak can grab
the connection. `src/tp88_ble.py` also falls back to connecting by raw address.

## Sending a job

Once bonded:

1. Connect over LE; negotiate MTU 512 (see below) → 509-byte writes.
2. Subscribe to `ff03` notifications (the printer immediately emits `0x0107` then
   `0x02f400` status, then a stream of `0x0101` per-packet reception acks).
3. Write the job bytes to `ff02` with **write-without-response**, paced to **~12 KB/s**
   (the head's drain rate — faster stalls; see Throughput).
4. The job's terminating bytes (the luck_normal `1b 4a 90`+`10 ff f1 45` footer, or, for a
   native job, the final raster block) trigger the print.

The **same byte dialects as USB** apply over BLE: `ff02` carries either the TiMini
`luck_normal` job we send today or a future native-QY job; the native status queries map to
the `ff03` notify channel (= the USB back-channel). See
[`tp88-protocol.md`](tp88-protocol.md) and [`../src/qy_native.py`](../src/qy_native.py).

```bash
# build the job (identical bytes to USB), then stream it over BLE:
.venv/bin/python src/tp88_print.py IMAGE.png --profile luck_a40 \
    --paper-mode tattoo --blackening 5 --dump job.bin
.venv/bin/python src/tp88_ble.py send job.bin          # MTU 512, ~12 KB/s (defaults)
```

## Throughput, MTU, and flow control

**Negotiate a large MTU.** The printer supports **ATT MTU 512** (509-byte write payloads),
but BlueZ defaults to 23 (20-byte payloads) until an MTU exchange is triggered. bleak only
does the exchange lazily — call `await client._backend._acquire_mtu()` right after connect.
This cuts a 324 KB page from ~16,000 writes to ~636 and is the single biggest speed win.
`src/tp88_ble.py` does this automatically.

**Pace to the head's sustained drain.** The printer has no usable flow-control credit (see
below), so it drops the link or stalls if you outrun the print head. `src/tp88_ble.py`
paces to a target throughput (`--rate-kbps`, default **12** ≈ the head's sustained rate).
Confirmed streaming a 323,608-byte A4 page (MTU 512):

| Config                  | Throughput  | Result                                                 |
|-------------------------|-------------|--------------------------------------------------------|
| **12 KB/s** fixed       | ~11.3 KB/s  | **reliable & fast** — full page in ~29 s, acks 1:1     |
| 8 KB/s fixed            | ~7.7 KB/s   | reliable but slower (~42 s)                             |
| 16 KB/s fixed           | "done" 21 s | host buffers ahead of the head → physical print stutters|
| ack-paced (window N)    | ~21 KB/s    | bursts fast then **stalls** mid-page (see below)        |
| MTU 23, 5 ms/chunk      | ~2.4 KB/s   | reliable but very slow (~133 s)                         |

The head **bursts** above its sustained rate briefly (buffer + momentum) then must throttle,
so anything much over ~12 KB/s either stutters (fixed) or stalls (ack-paced). `ff03`'s
`0x0101` is a per-packet **reception** ack and, under heavy write load, arrives *delayed
behind our own traffic* — so gating the send rate on acks (a sliding window) misreads a
busy head as a stall and blocks. Fixed-rate pacing at ~12 KB/s is therefore both the
simplest and the most reliable; it tracks acks 1:1 and finishes a page in ~29 s.
