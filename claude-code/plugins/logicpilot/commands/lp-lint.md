---
description: Run lint/static checks through the flow driver
argument-hint: "[optional: focus file/module]"
---

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" lint --config flow.toml
```

Use `hardware-rtl-audit` and `hardware-synthesizable-coding` to interpret the
JSON. Focus: $ARGUMENTS

## After running, read

- `status` — `blocked` means lint tool not on PATH, **not** a clean design (report env issue, do not declare pass)
- `tool` — which lint engine actually ran (verilator, slang, iverilog, …); record it
- `warnings` — driver-elevated flags (`latch inferred`, `multi-driver`, check failures) even on returncode 0
- `metrics.warnings_count` / `metrics.errors` — tool's own counts; cross-check against `warnings`
- `tail` — last 25 log lines; first failing rule usually here

Latch / multi-driver in `warnings` is a structural defect even when the tool exits 0. Full schema: `docs/JSON-CONTRACT.md`.
