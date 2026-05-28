# Golden vendor-log fixtures

High-fidelity samples of the actual output from EDA tools we parse. Used
by `tests/test_vendor_log_contracts.py` as a regression net: when a tool
upgrades its output format, the contract test catches the drift before
our envelope silently reports `None` / wrong values.

## How to add a new fixture

1. Capture a small but representative slice of the tool's stdout / log
   (~30 lines is plenty — the parser only consumes specific markers).
2. Trim project-specific names; the fixture should be reusable.
3. Save under this directory with a `<tool>_<scenario>.log` filename.
4. Add a contract assertion in `test_vendor_log_contracts.py` listing
   the exact metric keys + value ranges the parser should extract.

## How to update an existing fixture

If a vendor upgrade changes log format and the contract test fails:

1. **Don't** silently update the fixture to "make the test pass".
2. First verify the parser regex in `logicpilot_flow/metrics.py` or
   `logicpilot_flow/formal.py` is still correct for the **new** format —
   loosen / extend regex as needed.
3. Then update the fixture to a fresh sample from the new tool version.
4. Bump the comment header in the fixture noting the tool version.

## Coverage matrix

| Fixture | Parser | Scenario |
|---|---|---|
| `vivado_synth.log` | `metrics.parse_metrics` (synth stage) | LUT / FF / BRAM / DSP utilization + WNS |
| `vivado_power.log` | `metrics.parse_metrics` (power stage) | total / dynamic / static + Tj |
| `yosys_synth_ice40.log` | `metrics.parse_metrics` (synth stage) | SB_LUT4 / SB_DFF / SB_RAM cell counts |
| `nextpnr_route.log` | `metrics.parse_metrics` (pnr stage) | Max frequency for clock |
| `sby_pass.log` | `formal._parse_sby_output` | DONE(PASS) + engine identification |
| `sby_fail_with_depth.log` | `formal._parse_sby_output` | 2 failed assertions, each with distinct step depth |
| `sby_unknown.log` | `formal._parse_sby_output` | DONE(UNKNOWN) + backfill to `<all>: UNKNOWN` |
