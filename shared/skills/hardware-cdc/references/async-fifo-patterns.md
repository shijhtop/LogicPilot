# Async FIFO and CDC patterns

## Single-bit control

Use a 2FF synchronizer in the destination domain. The first flop must directly
sample the asynchronous signal; do not put combinational logic before it.

## Pulse crossing

A one-cycle pulse in the source domain can be missed by a slower destination
clock. Convert pulse to a toggle, synchronize the toggle, then edge-detect in
the destination, or use a req/ack handshake.

## Multi-bit data

Safe choices:

- Async FIFO for streams and sustained throughput.
- Req/ack handshake that holds the bus stable until acknowledged.
- Gray-coded counter/pointer when only adjacent values are observed.

Unsafe: N parallel 2FF synchronizers for N data bits.

## Async FIFO skeleton

- `wbin` / `rbin`: binary pointers for addressing local memory.
- `wgray` / `rgray`: Gray-coded pointers for crossing domains.
- `rgray_sync_to_wclk`: synchronized read pointer used to compute `full`.
- `wgray_sync_to_rclk`: synchronized write pointer used to compute `empty`.

Full / empty are detected by comparing the **next** local pointer value
(`wgraynext` / `rgraynext`) against the synced opposite pointer and
**registering the result on the same edge** the flag becomes true. Computing
flags from the registered local pointer alone delays them by one cycle and
permits overflow / underflow.

### Two equivalent pointer implementations

| Style | Register holds | Increment path | FFs | Use when |
|---|---|---|---|---|
| **#1** | Gray only | Gray → binary → +1 → binary → Gray | fewer | tight FF budget |
| **#2** | binary AND Gray (binary counter + binary→Gray XOR) | binary + 1 in parallel with one-XOR Gray | ~2× | FPGA default — shorter combinational depth, higher Fmax |

Both use synced-pointer comparison. An alternative async-comparator style
saves sync FFs but breaks STA-friendliness and DFT — avoid unless you've
explicitly signed off on those trade-offs.

### Pessimistic full / empty flag removal

- **Assertion** of full / empty is exact (compared against the local pointer
  at the moment it catches up).
- **De-assertion** is **pessimistic by 2 sync stages** — the flag stays
  asserted for a couple extra local-clock edges after the opposite pointer
  actually moves, because removal waits on the synced pointer.

This never causes overflow / underflow (the sender just sees the FIFO
"still full" for 2 extra cycles); it does mean useable depth is slightly
less than physical depth, so **size with margin**.

### Reset symmetry

- **Assertion** of FIFO pointer reset can be async and is safe: reset means
  "no valid data", and simultaneous multi-bit pointer transitions to zero
  are fine.
- **Deassertion** is the hazard: both domains must come out of reset cleanly
  so the FIFO comes up empty on **both** sides. Use async-assert /
  sync-deassert per domain (one synchronizer per domain, fed by the common
  raw reset).

Verify: no write when full, no read when empty, data order preserved across
random clock ratios, and flags recover correctly after reset.
