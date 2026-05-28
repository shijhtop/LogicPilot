---
name: hardware-simulation
description: >-
  Run and debug RTL simulation for hardware/HDL projects. Use to simulate, test, verify behavior, write a testbench, or debug a waveform, or when the user mentions iverilog, verilator, vvp, ghdl, nvc, cocotb, xsim, or VCD; verify functional correctness before synthesis.
---

# FPGA Simulation

Prove the RTL does what the spec says, at the behavioral level, before
spending time on synthesis and timing.

## Workflow

1. Ensure a self-checking testbench exists under `tb/` (matching the `tb`
   globs in `flow.toml`). A good TB drives stimulus, checks expected outputs
   with `$display`/assertions, and ends with a clear PASS/FAIL line and
   `$finish`. It should dump waves to `build/wave.vcd`.
2. For non-trivial TBs, run the built-in TB audit first:
   ```
   python3 <flow>/logicpilot.py tb-audit --config flow.toml
   ```
   Treat missing self-checks, missing seed logging, and coverage-without-checkers as verification gaps.
3. Run the sim stage:
   ```
   python3 <flow>/logicpilot.py sim --config flow.toml
   ```
4. Read the JSON. `status: pass` is necessary but NOT sufficient — also scan
   `tail` for the PASS/FAIL line your TB prints. A sim can "pass" (exit 0) while
   the DUT is wrong if the TB doesn't actually check anything.
5. On failure: open `build/wave.vcd` (gtkwave) or add targeted `$display`s,
   localize the first cycle where actual≠expected, fix RTL (via
   `hardware-rtl-design`) or the TB, rerun.

## Writing effective testbenches

- Make it self-checking: compare against a reference model or expected vector,
  fail loudly (`$error`/`$fatal`) — don't rely on eyeballing waves.
- Cover reset, then directed cases, then edge cases (overflow, back-to-back,
  stall/backpressure).
- For SystemVerilog TBs, prefer interface + clocking block + transaction/driver/monitor/scoreboard structure when the protocol is non-trivial.
- For non-trivial blocks prefer constrained-random + a scoreboard, or cocotb
  (Python) if the project uses it.
- Keep the TB synthesis-agnostic; `#delay`, `initial`, `$random` are fine here.

## Simulator selection & priority

You do not pick the simulator by hand. The preset defines an ordered list of
candidate simulators per stage; the driver resolves the project HDL (Verilog/SV
vs VHDL, auto-detected or declared as `[project] hdl`), filters candidates to
those that support that language, and runs the FIRST one installed on PATH.
The chosen tool comes back in the JSON `tool` field — always report it, since
"passed under verilator" and "passed under iverilog" are not identical claims.

### Recommended pairing by verification scope (advisory)

This is the project's preferred ordering when MULTIPLE candidates would all
work. **Not enforced** — when a recommended tool isn't installed, fall back
to whatever IS, and report what ran.

| Verification scope | Recommended stack | Why |
|---|---|---|
| Small module / quick unit test | **iverilog + plain testbench** | Cheapest to spin up; no build step; instant feedback on a single module. |
| Large module / project-level | **verilator + cocotb** (open) OR **vcs + cocotb** (commercial) | Verilator's compile-then-run is much faster on big designs; cocotb lets you write the TB in Python and reuse it across both simulators. |
| Full regression / sign-off | **vcs + UVM** | Heaviest but most thorough. **Use with caution**: only when the project is in its last debug pass OR the user explicitly asks for UVM. Do NOT default new projects into this stack — UVM startup cost rarely pays off mid-development. |

Decision rule for the agent:
1. Look at what the user is doing (one module? whole subsystem? final regression?).
2. Pick the recommended row.
3. If that row's preferred tool is missing, use the next-best installed candidate from the same row, then any installed candidate at all.
4. Report which tool ran AND whether it matched the recommendation, so the user can decide whether to install the preferred tool.

VHDL has its own ordering: `nvc` then `ghdl` (open) — commercial VHDL
simulators (Questa, RivieraPRO) are added per project.

To change priority or add a licensed simulator (Questa/VCS), redeclare the
`sim` stage candidates in `flow.toml` — see flow.toml.example. If a stage
comes back `status: blocked / needs-install`, no candidate for the project's
language is installed; tell the user exactly which tool to install (the
`reason` field lists them).

You always invoke through the `sim` stage so the result is one consistent JSON
shape regardless of which simulator was selected.

## Definition of done

A passing `sim` status AND a TB whose own PASS/FAIL output confirms the checked
behavior. Report both to the user before advancing to `hardware-synthesis`.
