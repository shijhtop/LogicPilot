---
description: Run built-in RTL source audit for risky synthesizable-code patterns
argument-hint: "[optional: note/focus area]"
---
Run the source audit before lint/sim/synth:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" audit --config flow.toml
```

Use `hardware-rtl-audit` to interpret the JSON. Focus: $ARGUMENTS

## After running, read

- `status` — `pass` / `fail` / `blocked`; `blocked` = source files unreadable, **not** a clean audit
- `summary` — `{high, medium, low}` counts by severity
- `findings[*]` — `{severity, rule, file, line, message}`; treat every `severity: high` as a review blocker unless waived with an explicit architectural reason
- `warnings` — parser-level issues (file unreadable, encoding); fix the input rather than ignoring

This stage does **not** write a log file, so there is no `tail`. Full schema: `docs/JSON-CONTRACT.md`.
