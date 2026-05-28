---
description: Health check — 'can I run LogicPilot here?' (project + machine + config in one shot)
---
Run the doctor:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" --doctor --config flow.toml
```

Unlike `/lp-tools` (which answers "what's installed") `/lp-doctor` answers
"given this project + this machine + this config, can the user actually
run the flow today, and if not, what's the cheapest fix". It is the
first thing to run after `/lp-init`, after pulling a project from
elsewhere, or when a stage is mysteriously failing.

`--doctor` runs even when `flow.toml` is missing — that's one of the
gaps it diagnoses. Do not refuse to invoke it just because the config
isn't there yet.

## After running, read

```json
{
  "stage": "doctor",
  "status": "pass | warn | fail | blocked",
  "summary": {"pass": N, "warn": N, "fail": N, "blocked": N},
  "checks": [
    {"name": "python_version",   "status": "pass", "detail": "..."},
    {"name": "flow_toml",        "status": "warn", "detail": "...", "warnings": [...]},
    {"name": "workspace_trust",  "status": "warn", "detail": "...", "hint": "..."},
    {"name": "stage:lint",       "status": "blocked", "install_hint": {...}},
    {"name": "smoke_test",       "status": "pass", "detail": "..."}
  ],
  "install_hint": { ... aggregated across all blocked stages ... }
}
```

- `status` precedence: `fail` > `blocked` > `warn` > `pass`. Use the
  top-level `status` for go/no-go; use individual `checks[*]` rows to
  tell the user what to fix.
- `install_hint` at top level is the **union** of per-stage hints, so
  the user gets one consolidated install line instead of having to scan
  rows. Prefer showing it over scanning individual `checks[*].install_hint`.
- A `flow_toml` row with `status: warn` and a `warnings` array means
  `flow.toml` parsed but has typos (unknown sections, misspelled
  preset names). Fix the typos before assuming downstream readings
  are reliable.
- `workspace_trust: warn` is non-fatal — project-local stage commands
  will be skipped. Only escalate to the user if they explicitly want
  to run project-defined shell.

Full envelope schema: `docs/JSON-CONTRACT.md`.
