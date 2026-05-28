---
description: Summarize generated flow logs and parsed metrics
---
Summarize existing reports/logs:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" report --config flow.toml
```

## After running, read

- `status` — `pass` / `blocked` (no logs aggregated)
- `log_dir` — where logs were aggregated from
- `reports[*]` — one entry per stage that produced a log:
  - `reports[*].stage` — stage name
  - `reports[*].metrics` — parsed numbers (timing, utilization, errors, …)
  - `reports[*].warnings` — driver-elevated flags from that stage
  - `reports[*].tail` — last log lines from that stage
- `warnings` — aggregation issues (no logs found, partial run, stage logs missing)

Produce a concise engineering summary from `reports[*]`. Do **not** claim
sign-off from a missing log; state which stages have not been run. Full
schema: `docs/JSON-CONTRACT.md`.
