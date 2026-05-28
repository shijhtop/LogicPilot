# Bus & interconnect design

An interconnect connects several masters and slaves. Beyond the per-port
protocol, you are designing three things: **address decode**, **arbitration**,
and **how backpressure/responses route back** — without breaking the handshake
rules or creating combinational loops.

## Topology

- **Shared bus** — one data path, one master active at a time (after
  arbitration). Cheap, low area; bandwidth is shared, so it bottlenecks under
  contention. Fine for control/register fabrics (APB-style).
- **Crossbar** — every master can reach every slave concurrently (full or
  partial). High bandwidth, more area/routing; used for AXI memory fabrics.
- **Layered / hierarchical** — a fast bus (AXI/AHB) for memory and a slow bus
  (APB) for peripherals, joined by a bridge. The common SoC pattern: don't put a
  slow peripheral on the high-speed fabric.

## Address decode

- Give each slave an address range; the decoder selects the target from the
  high address bits. Keep ranges **non-overlapping** and ideally power-of-two
  aligned so the decode is a few bit-compares, not a big comparator tree.
- Provide a **default slave** that returns an error response for unmapped
  addresses — otherwise an access to a hole hangs the master waiting for a
  response that never comes.

## Arbitration

- **Fixed priority** — simplest; starves low-priority masters under load. Use
  only when priorities are genuinely strict.
- **Round-robin** — fair; each master gets a turn. Good default for equal peers.
- **Weighted / least-recently-granted** — tune fairness vs throughput.
- Decide **when** arbitration re-evaluates: per transfer (fair, more overhead)
  vs per burst/lock (better throughput, can hold the bus). Honor lock/atomic
  signals where the protocol defines them.

## Backpressure & responses (the part that bites)

- Backpressure must propagate end-to-end: if the chosen slave deasserts `ready`,
  the master's `ready` upstream must reflect it so nothing is dropped. Verify by
  stalling a slave and checking no data is lost anywhere in the fabric.
- **Don't build a combinational `ready`/`valid` path through the whole fabric.**
  A master-to-slave `valid` that combinationally depends on the slave's `ready`
  across decode + arbitration + mux is both a deadlock risk and a long timing
  path. Insert **register slices / skid buffers** at fabric boundaries to pipeline
  it (this is exactly what AXI register-slice IP does).
- For protocols with **out-of-order** completion (full AXI with IDs), the
  interconnect must route responses back to the right master by ID and preserve
  per-ID ordering — a real source of fabric bugs.
- Match wait-state/response semantics when bridging protocols (e.g. APB
  `PREADY`, Avalon `waitrequest`, Wishbone `ACK`/`STALL`, AXI `B`/`R` channels).

## Clock domains in a fabric

If masters and slaves run on different clocks, the interconnect needs proper CDC
(async FIFOs or clock-converter bridges) — a shared bus does **not** make a
crossing safe. See `hardware-cdc`, and declare the async clock relationships in
`hardware-constraints` (`set_clock_groups -asynchronous`).

## Review checklist

- Address map non-overlapping; default slave returns an error, not a hang.
- Arbitration fairness matches the use case; no unintended starvation.
- Backpressure propagates; a stalled slave never causes data loss.
- No combinational valid/ready loop across the fabric; register slices at
  boundaries.
- Out-of-order responses routed/ordered correctly (if IDs are used).
- Cross-domain paths handled by CDC + constraints, not assumed safe.
