# Reset patterns and anti-patterns

## Recommended patterns

### Synchronous reset

Use when reset is generated inside the same clock domain, when you want reset to
be sampled only on clock edges, or when ASIC DFT/scan conventions prefer it.

```systemverilog
always_ff @(posedge clk) begin
  if (!rst_n) q <= '0;
  else        q <= d;
end
```

### Asynchronous assert, synchronous deassert

Use for external reset / POR when reset must assert immediately but release
must be safe relative to the destination clock. The canonical tie-high 2-FF
form:

```systemverilog
logic rff1, srst_n;
always_ff @(posedge clk or negedge arst_n) begin
  if (!arst_n) {srst_n, rff1} <= 2'b00;
  else         {srst_n, rff1} <= {rff1, 1'b1};
end
```

`rff1`'s D-input is implicitly `1'b1`; on release, both FFs see a clean
`0 → 1` transition aligned to `clk`. Add stages by extending the shift on
the right side, not by chaining the synchronizer into another one.

### Reset-valid split

Reset the `valid` bit and let data pipeline registers be don't-care until
`valid` is high. This improves FPGA timing/resource inference.

```systemverilog
always_ff @(posedge clk) begin
  if (!rst_n) begin
    valid_o <= 1'b0;
  end else if (ready_o) begin
    valid_o <= valid_i;
    data_o  <= data_i;   // no reset needed when valid_o==0
  end
end
```

## Anti-patterns

- Combinational reset expressions feeding async reset pins.
- One reset synchronizer reused across unrelated clocks.
- Resetting only some bits of a multi-bit state or pointer.
- Reset deassertion used as a data/control pulse without synchronization.
- Global reset applied to large datapaths that only need a reset valid bit.
- Testbench that only checks reset at time zero; reset must also be tested after
  activity if the system can assert it in the field.

## Constraint notes

- The async assertion path gets a false path on the synchronizer's clear
  pins (e.g. `set_false_path -to [get_pins <sync>/rff1/CLR]`), but the
  recovery / removal check from the synchronizer Q to every destination FF
  **must remain enabled** so STA still times the release. Verify
  `enable_recovery_removal_arcs true` (DC) and
  `timing_disable_recovery_removal_checks false` (PT).
- Protect the synchronizer flops from optimization with a vendor `dont_touch`
  / `keep` / `ASYNC_REG` attribute if required, and constrain the raw async
  input only to the first stage.
- DFT treatment of the synchronizer FFs (exclude from scan vs constrain
  the async reset during capture) is vendor / flow dependent — coordinate
  with DFT engineer rather than blindly excluding.
