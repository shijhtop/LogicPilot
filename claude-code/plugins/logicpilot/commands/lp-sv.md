---
description: Review or author SystemVerilog design/modeling code
---
Review or write SystemVerilog RTL/modeling code with emphasis on packages,
compile order, type-safe RTL, enums, arrays/structs, procedural blocks, FSMs,
interfaces/modports, and RTL-vs-model boundaries.

Use these skills:

- `systemverilog-design-modeling`
- `hardware-synthesizable-coding`
- `hardware-fsm-design`
- `hardware-interfaces`

Then run the built-in audit when a `flow.toml` exists:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" audit --config flow.toml
```

Report concrete findings, required code changes, and any tool-support assumptions.

## After running `audit`, read

- `summary.{high, medium, low}` — counts by severity
- `findings[*]` — `{severity, rule, file, line, message}`; for SV modeling, watch for missing `default_nettype`, package-import shadowing, ambiguous wire/logic, FSM enum-coverage gaps
- `status` — `blocked` only when source files are unreadable

Full schema: `docs/JSON-CONTRACT.md`.
