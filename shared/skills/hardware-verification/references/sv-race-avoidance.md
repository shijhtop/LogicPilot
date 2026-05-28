# SystemVerilog event regions, race avoidance, and bind files

## Race avoidance

A race exists when testbench and DUT read/write the same signal in the same
simulation time slot without a deterministic ordering. Symptoms include tests
that pass or fail depending on simulator, seed, or small code rearrangements.

Practical rules:

- DUT sequential RTL updates with nonblocking assignments on the clock edge.
- Testbench drivers should not change DUT inputs at the same edge the DUT
  samples unless using a clocking block with defined skew.
- Monitors should sample after the DUT has updated.
- Avoid `#0` as a race fix; it moves the problem to another event region.

## Bind-file methodology

Use SVA bind files when you want protocol/internal assertions without editing
the DUT RTL.

```systemverilog
module fifo_sva #(parameter int DEPTH = 16) (
  input logic clk, rst_n, wr_en, rd_en, full, empty
);
  assert property (@(posedge clk) disable iff (!rst_n) !(wr_en && full));
  assert property (@(posedge clk) disable iff (!rst_n) !(rd_en && empty));
endmodule

bind fifo fifo_sva #(.DEPTH(DEPTH)) u_fifo_sva (.*);
```

Keep assertions synthesizable-neutral and simulation/formal friendly. For formal,
separate environmental `assume` constraints from design `assert` obligations.
