# Verification Frameworks — What to Use When

| framework | language | best for | notes |
|-----------|----------|----------|-------|
| **cocotb** | Python | open-source FPGA, fast TB authoring, reuse SW models | coroutine-based, drives many simulators (iverilog, verilator, ghdl, vendor) via VPI/VHPI/FLI; pairs with cocotb-coverage for CRV |
| **UVM** | SystemVerilog | large/complex, industry-standard, reusable VIP | IEEE 1800.2; heavyweight; needs full SV simulator; de-facto for ASIC, used on high-density FPGA |
| **OSVVM** | VHDL | VHDL shops wanting CRV + coverage incrementally | readable, add capability step by step |
| **UVVM** | VHDL | VHDL, structured bus VIP, ESA-backed | strong BFM library |
| **VUnit** | VHDL / SV | unit-test runner + CI automation | not a methodology; orchestrates compile/run/report, great for regressions |

## How to choose

- Open-source FPGA, want momentum fast → **cocotb** (write the model in Python,
  reuse it as the reference). Add `cocotb-coverage` when you need functional
  coverage / constrained random.
- VHDL design team → **OSVVM** or **UVVM**; add **VUnit** to run the regression
  and produce pass/fail reports in CI.
- Large SV verification effort with reusable VIP across projects → **UVM**, but
  only if the complexity justifies the ramp-up; a lightweight SV scoreboard is
  often enough for a single FPGA block.
- Any of the above can coexist with **formal** (SymbiYosys) for control logic and
  with **assertions** sprinkled in the RTL/interfaces.

Don't adopt a heavy methodology by default. Match the framework to the design's
size, the team's language, and whether VIP reuse across projects is a real need.

## cocotb shape (for reference)

A cocotb test is a Python coroutine that awaits clock edges and drives/reads DUT
signals; the "expected" result comes from plain Python. To wire it into this
flow, add a `sim` candidate whose `cmd` invokes the cocotb makefile/runner with
the project's simulator, and keep the Python reference model under `tb/`.

---

# Gate-Level Simulation & X Handling

(Reference for RTL-stage authors to preempt X traps before the design
hands off to back-end GLS.)

## Why GLS finds bugs RTL sim doesn't

- **X-optimism (RTL):** RTL `if`/`case` can resolve an unknown `x` optimistically
  (e.g., taking a branch) so sim looks fine, while the gate netlist propagates
  the X and exposes that some state was never properly reset/initialized.
- **X-pessimism (gates):** conversely the gate model can show X where real
  silicon would resolve — usually a reset/init gap to fix, not a tool bug.
- **Init/reset differences:** FPGA FFs may power up to a defined value the RTL
  assumed via `initial`; if reset doesn't cover that state, GLS diverges.
- **SDF-annotated GLS:** with timing back-annotation, setup/hold violations show
  as Xs at the violating registers — that's a *timing* problem (send back to
  timing closure), not a functional one.

## Method

Run the same testbench against the synthesized netlist + cell models. A mismatch
that passed at RTL almost always means: incomplete reset, reliance on `initial`
that didn't carry, an X masked in the TB, or (with SDF) a timing violation. Fix
the reset/init in RTL — never mask the X in the testbench. Use equivalence
checking (see assertions-and-formal) as a faster complementary sign-off.
