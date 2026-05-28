# cdc_top — microarchitecture

## Block diagram

```
                  ┌────────────────┐                ┌────────────────┐
   wr_clk ──────► │ wr-side ptrs   │                │ rd-side ptrs   │ ◄────── rd_clk
   wr_rst_n ────► │ wr_ptr_bin     │                │ rd_ptr_bin     │ ◄────── rd_rst_n
   wr_en ───────► │ wr_ptr_gray    │ ─── sync_2ff ─►│ in-rd-clk copy │
   wr_data ─────► │ mem write port │                │ mem read port  │ ──────► rd_data
                  │ full = …       │ ◄── sync_2ff ──│ rd_ptr_gray    │ ──────► empty
                  └────────────────┘                └────────────────┘
```

## Pointer scheme (Cummings async FIFO style)

- Both `wr_ptr_bin` and `rd_ptr_bin` are `AW+1` bits wide (1 extra bit
  to distinguish full from empty).
- Their gray equivalents `wr_ptr_gray` / `rd_ptr_gray` are computed
  combinationally as `(bin >> 1) ^ bin`.
- The gray pointers are the ONLY values that cross the clock domain.
  This guarantees that only one bit at a time changes, so the
  synchronized value is monotone even when a flop catches a transition
  and goes metastable for one cycle.

## CDC summary

| From      | To        | Signal              | Sync depth | Verdict |
|-----------|-----------|---------------------|------------|---------|
| `wr_clk`  | `rd_clk`  | `wr_ptr_gray`       | 2          | safe    |
| `rd_clk`  | `wr_clk`  | `rd_ptr_gray`       | 2          | safe    |

Recorded in `docs/cdc-inventory.json`; validated by `lp cdc-check`.

## Reset strategy

- Active-low, async-assert / sync-release per domain.
- Each domain owns its own reset; no cross-domain reset is asserted by
  the FIFO itself. The synchronizers reset to all-zeros on the
  destination domain's reset.
- `set_clock_groups -asynchronous {wr_clk} {rd_clk}` is assumed in the
  consumer SDC. `set_clock_groups_declared: true` in
  `docs/cdc-inventory.json` records this.

## Memory inference

`mem` is a 8 × 8 array driven inside `always @(posedge wr_clk)`.
yosys / Vivado will infer distributed RAM (one write port, async read)
because there is no separate read clock on the memory itself; the
read pointer indexes it combinationally.

## Failure modes the design intentionally tolerates

- **Pointer metastability** — addressed by gray-coding + sync_2ff.
- **Reset skew between domains** — each domain's logic ignores the
  other's reset state; on power-on both pointers go to 0 and the
  FIFO comes out empty.

## Failure modes the design does NOT cover

- **Concurrent reset assertion mid-transfer** that races with a
  metastable sync — out of scope for the demo; real designs need a
  reset synchronizer per domain.
- **Power gating** — not modeled.
