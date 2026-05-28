# cdc_top — functional spec

## Purpose

`cdc_top` is an 8-deep × 8-bit asynchronous FIFO with separate write
and read clocks. It exists as a LogicPilot demo: small enough to
fit in a head, large enough to exercise the multi-clock, CDC, and
audit paths of the driver.

## Interfaces

| Port        | Width | Direction | Domain   | Purpose                                 |
|-------------|-------|-----------|----------|-----------------------------------------|
| `wr_clk`    | 1     | in        | producer | Write-side clock                        |
| `wr_rst_n`  | 1     | in        | producer | Active-low async reset, sync release    |
| `wr_en`     | 1     | in        | producer | Push request; honored only when `!full` |
| `wr_data`   | 8     | in        | producer | Push data                               |
| `full`      | 1     | out       | producer | Backpressure to producer                |
| `rd_clk`    | 1     | in        | consumer | Read-side clock                         |
| `rd_rst_n`  | 1     | in        | consumer | Active-low async reset, sync release    |
| `rd_en`     | 1     | in        | consumer | Pop request; ignored when `empty`       |
| `rd_data`   | 8     | out       | consumer | Pop data                                |
| `empty`     | 1     | out       | consumer | No data available                       |

## Behavioral requirements

1. Writes ordered by `wr_clk` posedge; pops ordered by `rd_clk` posedge.
2. `full` and `empty` use gray-coded pointer comparison, never the
   ordinary binary count (so they remain monotone across the CDC).
3. After both resets release, the first 8 push-after-reset operations
   must succeed; the 9th must observe `full == 1` and be ignored.
4. Drain order matches push order (FIFO discipline) within the limits
   of the demo testbench, which is intentionally not vigorous about
   data-path correctness — see `tb/cdc_top_tb.v`.

## Non-requirements

- No depth other than 8. No width other than 8.
- No first-word fall-through. `rd_data` valid one `rd_clk` cycle after
  `rd_en` is sampled high while `!empty`.
- No multi-bit error checking, no parity, no AXI wrapping.

## Performance assumptions

| Knob       | Value             | Source                              |
|------------|-------------------|--------------------------------------|
| `wr_clk`   | 100 MHz (10 ns)   | Stated in the testbench `always`    |
| `rd_clk`   | ~37 MHz (27 ns)   | Intentionally async to `wr_clk`     |
| FIFO depth | 8                 | `parameter DEPTH = 8` in `async_fifo` |
