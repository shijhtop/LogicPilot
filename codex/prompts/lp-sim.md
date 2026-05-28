---
description: Run RTL simulation and report PASS/FAIL
---
Run `FLOW="${LOGICPILOT_FLOW:-}"
if [ -z "$FLOW" ]; then
  if [ -f ./codex/flow/logicpilot.py ]; then
    FLOW="./codex/flow/logicpilot.py"
  else
    FLOW="${CODEX_HOME:-$HOME/.codex}/logicpilot/flow/logicpilot.py"
  fi
fi; python3 "$FLOW" sim --config flow.toml`, then use the
`hardware-simulation` and `systemverilog-verification-platform` skills to
interpret the result.

## Simulator recommendation (advisory)

Pick by scope; fall back if preferred tool missing, and state what ran.

- Small module / quick unit test → `iverilog` + plain TB
- Large module / project-level → `verilator` + cocotb (open) or `vcs` + cocotb (commercial)
- Full regression / sign-off → `vcs` + UVM (only late-stage debug OR explicit user request — do NOT default mid-development work into UVM)

## After running, read

- `status` — `blocked` = simulator missing (env issue), not a passing sim
- `warnings` — verification flags: `"no PASS/FAIL marker in log"`, `"unseeded random run"`, `"coverage merged from failing seed"` — treat as soft fail
- `tail` — last 25 log lines; locate first failing cycle here, then trace back to RTL
- `metrics.errors`

Exit code 0 alone is **not** a pass — `pass` + `warnings: ["no PASS/FAIL marker in log"]` means the TB ran without asserting anything. Full schema: `../../docs/JSON-CONTRACT.md`.
