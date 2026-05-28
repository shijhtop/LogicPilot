---
name: hardware-verification
description: >-
  Reference for verifying hardware/HDL designs: self-checking testbench architecture, SVA/PSL assertions, functional & code coverage, constrained-random stimulus, formal verification (SymbiYosys), equivalence checking, gate-level X-handling, and frameworks (cocotb, UVM, OSVVM, UVVM, VUnit). Consult when planning verification, writing a testbench, or interpreting coverage.
---

# Hardware Verification Knowledge

Verification answers one question: *does the design meet its spec, and how do we
know we checked enough?* Two orthogonal axes: **how you check** (self-checking
sim, assertions, formal, equivalence) and **how you know you're done**
(coverage). Both matter — stimulus without checking proves nothing, and checking
without coverage doesn't tell you what you missed.

## Allocation audit first

Before picking a verification approach, audit `docs/uarch.md`'s per-module test
allocation. Produce an Allocation Audit table that mirrors the File list
row-for-row:

| path | uarch allocation | gap | action |
|------|------------------|-----|--------|

Fill `gap` if any of:

- **Missing row** — a module from the File list has no obligation in the
  `test` column.
- **Mis-tagged integration** — a module with independent state, transformation,
  arbitration, protocol rule, or failure mode is tagged only `integration`.
  Integration has a strict definition in `hardware-design-planning`; mis-tagged
  glue is the #1 abuse.
- **Missing golden** — a module tagged `reference-model` (alone or in combination)
  has no named golden source in the `artifact` column.
- **Missing invariant headline** — a module tagged `property/invariant` (alone or
  in combination) has no one-line invariant statement in the `artifact` column.
- **Missing top-test name** — a module tagged `integration` has no named
  top-level test file or coverage point in the `artifact` column. Bare "skip"
  or "trivial; top TB covers" is not a name.
- **Self-contradiction** — an integration row references a unit testbench. By
  definition integration means no unit TB.

For each gap, `action` is "submit patch to docs/uarch.md, do not start TB".
Do NOT silently fill gaps in the TB — inventing a TB after the fact loses
the architectural input that should have shaped the module boundary.

Once the audit is clean (zero gaps), map allocation to verification approach
(a module may carry more than one obligation; do both):

- **reference-model** — directed + constrained-random + bit-exact diff against
  the named golden. Pick DPI-C, cocotb, or offline-vectors-from-file for the
  reference. Coverage target = input-space sweep of the documented ranges.
- **property/invariant** — SVA on the headlined invariants; consider formal
  (SymbiYosys) for FIFOs, arbiters, CDC handshakes where bounded-depth proof
  is reachable. Add a scoreboard only when end-to-end data correctness is also
  at stake.
- **integration** — write no unit TB. **Verify the named top-level test or
  coverage point actually exists** in the top regression; if it doesn't,
  either add it (with a covergroup or directed-test record), or escalate back
  to planning that the obligation is unsatisfiable.

## Choosing an approach

This knowledge is target-agnostic: simulation, assertions, coverage, and formal
apply to BOTH FPGA and ASIC verification. ASIC sign-off adds STA (setup AND
hold, multi-corner), DRC/LVS, and DFT/ATPG — those are back-end stages and
out of scope for this plugin.

- **Directed self-checking sim** — start here for any block. Drive known
  stimulus, compare against expected/reference, fail loudly. (→
  `references/testbench-architecture.md`)
- **Assertions (SVA/PSL)** — encode invariants and protocol rules that get
  checked on every cycle of every test; also the input to formal. (→
  `references/assertions-and-formal.md`)
- **SystemVerilog verification platform** — interfaces, clocking blocks,
  virtual interfaces, class-based components, transactions, scoreboards,
  constrained random, functional coverage, threads, and DPI. (→
  `systemverilog-verification-platform`)
- **Constrained-random + functional coverage** — when the input space is too
  large to enumerate; let randomization explore, let coverage tell you what was
  hit. (→ `references/coverage-and-crv.md`)
- **Formal property verification** — prove (not sample) that an assertion holds
  for all reachable states; great for control logic, FIFOs, arbiters, CDC, and
  for finding deep corner cases. Open-source: SymbiYosys. (→
  `references/assertions-and-formal.md`)
- **Equivalence checking** — prove two netlists/RTL are logically the same
  (post-synth/opt sign-off). (→ `references/assertions-and-formal.md`)

A typical FPGA block uses directed sim + assertions, adds constrained-random for
data paths, and uses formal for tricky control. Pick per risk, not dogma.

## The non-negotiable principles

1. **Self-checking only.** A test that a human eyeballs in a waveform isn't a
   regression. Encode the expected result and let the test pass/fail itself.
2. **Coverage is meaningless without checking.** Failed tests must not count
   toward coverage; build the checkers before trusting coverage numbers (ref:
   coverage-driven verification methodology).
3. **Check at multiple levels.** End-to-end scoreboard + protocol assertions +
   inline checks catch different bug classes.
4. **Reproducibility.** Seed random runs and log the seed; a failing seed must
   replay deterministically. **Use the `LOGICPILOT_SEED=<n>` marker
   convention** (v0.7b+): testbenches MUST print exactly
   `$display("LOGICPILOT_SEED=%0d", seed);` (SystemVerilog/Verilog) or
   `print(f"LOGICPILOT_SEED={seed}")` (cocotb) once at simulation start.
   The driver recognises this single canonical pattern and stops trying
   to regex-guess vendor-specific seed log formats. Setting
   `[verification].require_seed_log = true` in `flow.toml` upgrades a
   missing marker on a randomised test from warning to hard fail.

## Frameworks

cocotb (Python), UVM (SystemVerilog, IEEE 1800.2), OSVVM and UVVM (VHDL), and
VUnit (unit-test runner for VHDL/SV) — what each is for and when to reach for it
is in `references/frameworks.md`. For open-source hardware flows, cocotb + SymbiYosys
cover most needs without a commercial simulator.

## Gate-level & X issues

Post-synthesis sim (GLS) and equivalence sign-off, plus the X-optimism /
X-propagation traps that make RTL sim pass while GLS fails, are covered in
`references/gate-level-and-x.md`. GLS itself is a back-end stage and out
of scope here; the reference is kept so RTL-stage authors can preempt the
common X traps before handing off.

## Using this in review

Before trusting a simulation regression, run `tb-audit` when a testbench is present:

```bash
python3 <flow>/logicpilot.py tb-audit --config flow.toml
```

When reviewing a verification plan or testbench, check: is it self-checking? are
the spec's features each tied to a check and a coverage point? are protocol
rules asserted? is randomization seeded and logged? for high-risk control logic,
is formal used? Report gaps as concrete missing checks/cover points, not vague
"add more tests".

## Race-aware SystemVerilog verification

For SystemVerilog testbenches, avoid races with DUT RTL:

- Drive DUT inputs on a clocking block or away from the active edge the DUT
  samples.
- Sample outputs after the DUT has updated, not in the same active-region race.
- Put reusable protocol assertions in separate bind files when modifying RTL is
  undesirable; `bind` lets the checker live outside the DUT while observing its
  internal or interface signals.
- Prefer assertions for invariants (stable-while-valid, no read-on-empty, no
  write-on-full, legal FSM states) and scoreboards for end-to-end data
  correctness.

For class-based or coverage-driven SystemVerilog environments, use `systemverilog-verification-platform`. See also `references/sv-race-avoidance.md`.
