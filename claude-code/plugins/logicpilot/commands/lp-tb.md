---
description: Review or scaffold a SystemVerilog verification platform
argument-hint: "[DUT/protocol/test goal]"
---
Use `systemverilog-verification-platform`.

Produce or review the TB architecture: interface/modports, clocking blocks,
virtual interface wiring, transaction type, generator/sequencer, driver,
monitor, reference model, scoreboard, assertions, functional coverage, seed
logging, and regression PASS/FAIL policy.

For an existing TB, run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" tb-audit --config flow.toml
```

Target/focus: $ARGUMENTS

## After running `tb-audit`, read

- `status` — `blocked` = TB sources unreadable; `fail` = audit found issues
- `summary` — `{high, medium, low}` counts
- `findings[*]` — `{severity, rule, file, line, message}`; common high-severity rules: no self-checking, unseeded random, no PASS/FAIL marker, no scoreboard, no assertions
- `warnings` — parser-level only

This stage does not write a log; there is no `tail`. Full schema: `docs/JSON-CONTRACT.md`.
