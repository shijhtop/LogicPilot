# Handshake & streaming interfaces

## valid/ready in depth

Signals (generic names; AXI prefixes them T/AW/W/etc.):
- `valid` — source: "payload is valid this cycle."
- `ready` — destination: "I will accept a transfer this cycle."
- payload — the data/control, valid only while `valid` is high.

Transfer = the cycle where `valid && ready` at the rising edge.

The four legal waveforms:
- `valid` before `ready` — source has data, waits (holding valid+data) until the
  destination is ready.
- `ready` before `valid` — destination is waiting; transfer happens the cycle
  the source asserts valid.
- both same cycle — single-cycle transfer.
- back-to-back — `valid` and `ready` stay high → one transfer per cycle (full
  throughput).

### Throughput vs combinational coupling

A simple destination computes `ready` combinationally from its own state — fine.
The trap is a long combinational `ready` that fans back through several stages
to a `valid`, creating a critical path or a loop. Break it with a **skid buffer**
(a.k.a. register slice): two storage slots so you can register `valid`/`ready`
in both directions and still accept a new item every cycle when not stalled.
Registering only one direction (e.g. just the data) without the second slot
drops throughput to one-every-other-cycle or loses data on stall.

### Common bugs

- Source deasserts `valid` (or changes data) before the transfer completes →
  lost/duplicated data.
- `valid` derived combinationally from `ready` → deadlock or a timing loop.
- Destination asserts `ready` but isn't actually able to store → overflow.
- No skid buffer where backpressure must be pipelined → throughput collapse.

## AXI4-Stream (streaming, master → slave)

Unidirectional data flow, no addresses. Core signals:
- `TVALID`/`TREADY` — the handshake.
- `TDATA` — the payload (width is a multiple of 8 bits).
- `TLAST` — marks the last beat of a packet/frame (boundary).
- `TKEEP`/`TSTRB` — per-byte qualifiers (which bytes are valid / data vs
  position bytes).
- `TID`/`TDEST` — stream identifier / routing destination (for interconnect).
- `TUSER` — user sideband, carried alongside the beat.

Rules mirror the cardinal handshake: `TVALID` must not wait for `TREADY`; once
`TVALID` is high, hold `TVALID`, `TDATA`, `TLAST` stable until `TREADY`. Use
`TLAST` to frame packets; downstream blocks that re-frame must respect it.

Avalon-ST is the Intel equivalent: `valid`/`ready` + `data`, with
`startofpacket`/`endofpacket` (and `empty` for partial final words). Same flow
control, different names; bridging is mechanical.

### A correct minimal source skeleton (concept)

- Assert `valid` whenever the FIFO/producer has a beat.
- Hold `data`/`last` stable while `valid`.
- Advance (pop) only on `valid && ready`.
- Never gate `valid` with `ready`.
