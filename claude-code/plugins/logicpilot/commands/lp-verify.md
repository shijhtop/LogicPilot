---
description: Run verification checks: testbench audit then simulation
argument-hint: "[optional: testbench/module/focus area]"
---
Run the verification front-end:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" tb-audit --config flow.toml
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" sim      --config flow.toml
```

Use `systemverilog-verification-platform` for SV TB structure and
`hardware-verification` for assertions, coverage, formal, and scoreboarding.
Focus: $ARGUMENTS

## After running, read

### `tb-audit`
- `status`, `summary.{high,medium,low}`, `findings[*]`
- Common high findings to fail-fast on: no self-checking, unseeded random, no PASS/FAIL marker, no assertions

### `sim`
- `status` — `blocked` = simulator missing, **not** pass
- `warnings` — verification flags: `"no PASS/FAIL marker in log"`, `"unseeded random run"`, `"coverage merged from failing seed"`
- `tail` — locate first failing cycle here
- `metrics.errors`

A `sim` `pass` with `warnings: ["no PASS/FAIL marker in log"]` is NOT a passing self-checking TB. Full schema: `docs/JSON-CONTRACT.md`.
