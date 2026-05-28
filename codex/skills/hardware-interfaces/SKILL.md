---
name: hardware-interfaces
description: >-
  Design and review on-chip interfaces and buses: valid/ready handshake rules, streaming (AXI4-Stream), memory-mapped/register interfaces (AXI4, AXI4-Lite, APB, AHB-Lite, Avalon-MM, Wishbone), and interconnect (arbitration, address decode, backpressure). Use when connecting blocks with handshakes, AXI, a register map, or a bus.
---

# On-chip Interfaces & Buses

Most integration bugs are interface bugs: a backpressure path that deadlocks, a
bus sampled while unstable, a combinational `ready→valid` loop. Get the
handshake right first; the named protocols (AXI, APB, Avalon, Wishbone) are all
built on the same flow-control idea.

## The valid/ready handshake — cardinal rules

This is the universal point-to-point flow control (AXI made the names famous,
but it's protocol-independent). A **source** presents data + `valid`; a
**destination** asserts `ready` when it can accept. **A transfer happens on a
rising clock edge when `valid` AND `ready` are both high.**

The rules that prevent deadlock and timing loops:

1. **`valid` must NOT depend on `ready`.** The source asserts `valid` as soon as
   it has data, without waiting to see `ready`. A source that waits for `ready`
   before asserting `valid`, while the destination waits for `valid` before
   asserting `ready`, **deadlocks**.
2. **`ready` MAY depend on `valid`.** A destination is allowed to wait until it
   sees `valid` before asserting `ready` (and many do).
3. **Once `valid` is asserted, hold it — and keep the payload stable —** until
   the transfer completes (both high). Don't drop `valid` or change the data
   because `ready` is still low.
4. **No combinational path from `ready` straight to `valid`** (and avoid long
   combinational `ready` chains across a fabric). When you need to break such a
   path or pipeline backpressure, insert a **skid buffer / register slice** (a
   2-deep buffer that registers both directions without losing throughput).

If you remember nothing else: source can't wait for ready; destination can wait
for valid; hold valid+data until accepted. See
`references/handshake-and-streaming.md`.

## Picking an interface

- **Streaming, no addresses, master→slave data flow** (DSP pipelines, video,
  packet data) → **AXI4-Stream** (or Avalon-ST). Just valid/ready + data, with
  `last` for packet boundaries. → `references/handshake-and-streaming.md`.
- **Control/status registers, occasional single accesses** → **AXI4-Lite**,
  **APB**, **Avalon-MM**, or **Wishbone (classic)**. APB/Wishbone-classic are the
  simplest to implement. → `references/memory-mapped.md`.
- **High-throughput memory access with bursts, multiple outstanding, out-of-
  order** → **full AXI4** (or AHB for pipelined single-master). →
  `references/memory-mapped.md`.
- **Connecting many masters/slaves** (arbitration, address decode, topology) →
  `references/interconnect.md`.

Choice is usually dictated by the ecosystem: AMBA/AXI on Xilinx & ARM SoCs,
Avalon on Intel/Nios II, Wishbone on OpenCores/open designs.

## SystemVerilog interface note

For repeated protocol bundles, SystemVerilog `interface` + `modport` can reduce wiring mistakes and make roles explicit.

- Define `modport`s for every role that connects to the interface.
- Keep synthesizable interface contents simple and verify tool support.
- Interface methods used by RTL should be `automatic`.
- Clocking blocks and virtual interfaces are testbench constructs; do not place
  them in synthesizable RTL source globs.
- Use interfaces to clarify protocol ownership, not to hide combinational
  feedback or timing-critical backpressure paths.

## Designing or reviewing an interface — checklist

- Handshake obeys all four cardinal rules (no `valid`←`ready` dependency, no
  combinational `ready→valid`, payload stable while `valid`).
- Backpressure actually propagates: if the downstream stalls, does the upstream
  stop without dropping data? Test a destination that holds `ready` low.
- Reset: both sides come out of reset with `valid`/`ready` deasserted; no
  spurious transfer on the first cycle.
- Crossing a clock domain? The handshake/bus does **not** make it CDC-safe by
  itself — use `hardware-cdc` (async FIFO or a properly synchronized handshake).
- Verification: write protocol **assertions** (valid stable until ready, no
  data change while valid, no transfer in reset) — see `hardware-verification`.
- Constrain async crossings and declare clock relationships — see
  `hardware-constraints`.

## Definition of done

The handshake follows the cardinal rules; backpressure and reset are correct;
the chosen named protocol's required signals/ordering are honored; CDC and
constraints are handled where the interface crosses domains; protocol assertions
are in place. State which protocol and why.
