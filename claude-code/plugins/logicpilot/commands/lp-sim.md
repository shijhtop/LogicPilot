---
description: Run RTL simulation through the flow driver
argument-hint: "[optional: testbench or module to focus on]"
---

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" tb-audit --config flow.toml
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" sim      --config flow.toml
```

Use `hardware-simulation` and `systemverilog-verification-platform`. Focus area: $ARGUMENTS

## Simulator recommendation (advisory, not enforced)

Pick the stack that matches the user's scope. If the preferred tool isn't installed, fall back to whatever IS installed — but **say so in the report**.

| Scope | Recommended | Notes |
|---|---|---|
| Small module / quick unit test | `iverilog` + plain TB | cheapest spin-up, no build step |
| Large module / project-level | `verilator` + cocotb (open) or `vcs` + cocotb (commercial) | speed + Python TB reuse |
| Full regression / sign-off | `vcs` + UVM | **caution**: only when project is in final debug OR user explicitly asks. Do NOT default mid-development work into UVM. |

Always read JSON `tool` to learn what actually ran. "Passed under verilator" ≠ "passed under vcs+UVM".

## After running, read (each stage)

- `status` — `pass` / `fail` / `blocked` / `timeout`; `blocked` = simulator missing, not a passing sim
- `warnings` — verification-specific: no PASS/FAIL marker in log, unseeded random run, coverage merged from failing seed
- `tail` — last 25 log lines; locate the first failing cycle here, then trace back to RTL
- `metrics.errors` / `metrics.warnings_count` — simulator's own counts

A `pass` with `warnings: ["no PASS/FAIL marker in log"]` is **not** a passing self-checking TB — it ran without asserting anything. Full schema: `docs/JSON-CONTRACT.md`.
