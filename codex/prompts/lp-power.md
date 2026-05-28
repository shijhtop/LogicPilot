---
description: Run optional power analysis and report assumptions
argument-hint: "[optional: SAIF/VCD/activity note]"
---
Run `FLOW="${LOGICPILOT_FLOW:-}"
if [ -z "$FLOW" ]; then
  if [ -f ./codex/flow/logicpilot.py ]; then
    FLOW="./codex/flow/logicpilot.py"
  else
    FLOW="${CODEX_HOME:-$HOME/.codex}/logicpilot/flow/logicpilot.py"
  fi
fi; python3 "$FLOW" power --config flow.toml`, then use the
`hardware-power-analysis` skill. Focus: $ARGUMENTS

## After running, read

- `status` — `blocked` = power tool / activity file missing
- `metrics.total_power_w` / `metrics.dynamic_w` / `metrics.leakage_w`
- `assumptions` — **always state this when reporting power**: SAIF-annotated / VCD-annotated / vectorless default / propagated activity. A vectorless estimate is not a sign-off number.
- `warnings` — budget overrun when `[power].total_budget_w` is configured, plus any model-quality flags

Label vectorless / default activity as an early estimate; only SAIF/VCD
activity tied to representative traffic is actionable. Full schema:
`../../docs/JSON-CONTRACT.md`.
