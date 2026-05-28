# Assertions, Formal Property Verification & Equivalence

## Assertions (SVA / PSL)

Assertions encode rules the design must always obey, checked continuously in
simulation and used as the proof target in formal. SystemVerilog Assertions
(SVA, defined within **IEEE 1800**) are the most common (~45% of FPGA projects);
PSL (**IEEE 1850**, also incorporated into VHDL **IEEE 1076-2019**) is also used,
and VHDL designs often add SVA via `bind` or use PSL/`assert`.

Two kinds:
- **Immediate** — checked when reached, like a procedural `if`. Good for inline
  sanity checks.
- **Concurrent** — clocked temporal properties. The workhorse.

```systemverilog
// req must be granted within 1..3 cycles
property p_grant;
  @(posedge clk) disable iff (!rst_n)
  req |-> ##[1:3] gnt;
endproperty
assert property (p_grant);          // checks it
cover  property (p_grant);          // records that the scenario occurred
```

Patterns worth asserting: one-hot/onecold state, no overflow on full, handshake
ordering (`req` before `ack`), FIFO never reads when empty / writes when full,
no X on control signals, stable-while-valid (data must not change while held).

Use `assume` for input constraints (especially in formal — they bound the
environment), `assert` for design obligations, `cover` to confirm interesting
scenarios are reachable.

## Formal property verification (SymbiYosys)

Formal *proves* a property over all reachable states instead of sampling it with
stimulus. Open-source flow: SymbiYosys (sby) drives Yosys + an SMT solver
(Yices/Boolector/Z3). It supports:

- **Bounded model checking (BMC)** — prove safety (assertions) hold for N cycles
  from reset; finds shallow bugs fast, gives a counterexample trace (VCD).
- **Unbounded / k-induction (`prove`)** — prove a property holds for *all* time.
- **Cover** — find a trace that reaches a `cover` statement (also a way to
  auto-generate stimulus that hits a scenario).
- **Liveness** — prove "something eventually happens" (no deadlock/starvation).

Typical `.sby`:
```
[options]
mode bmc
depth 20
[engines]
smtbmc
[script]
read -sv design.sv
prep -top dut
[files]
design.sv
```

Where formal shines: arbiters, FIFOs, CDC handshakes, protocol adapters, state
machines — small-to-medium control logic with deep corner cases. Where it
struggles: wide datapaths/multipliers (state explosion) — verify those with
simulation + a reference model, and reserve formal for the control around them.

A counterexample is a gift: it's a concrete trace to the bug. Reproduce it in
your simulator, fix, re-prove.

## Equivalence checking (sign-off)

Prove two representations are logically identical — RTL vs synthesized netlist,
or pre- vs post-optimization. Combinational equivalence (CEC) and sequential
equivalence (SEC) are provided by ABC (inside Yosys) and by the `equiv_*`
commands; the flow's `lec` stage uses `equiv_make`/`equiv_simple`/`equiv_status
-assert`. This catches synthesis/optimization bugs that GLS might miss, and is
faster than re-running the full testbench on the netlist. Note `equiv` is
combinational-scope; retiming/sequential changes need SEC or GLS to catch.
