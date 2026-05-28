---
description: Run the configured hardware flow or a single stage
argument-hint: "[optional: stage]"
---
Run the flow through the LogicPilot driver and report JSON results.

If a single stage is given (`$ARGUMENTS`), validate it is a single stage-name
token before running it (this prevents shell injection from the argument):

```bash
FLOW="${LOGICPILOT_FLOW:-}"
if [ -z "$FLOW" ]; then
  if [ -f ./codex/flow/logicpilot.py ]; then
    FLOW="./codex/flow/logicpilot.py"
  else
    FLOW="${CODEX_HOME:-$HOME/.codex}/logicpilot/flow/logicpilot.py"
  fi
fi
if printf '%s' "$ARGUMENTS" | grep -qE '^[A-Za-z0-9_-]+$'; then
  python3 "$FLOW" "$ARGUMENTS" --config flow.toml
else
  echo "refusing: stage must be a single token matching [A-Za-z0-9_-]; got: $ARGUMENTS"
fi
```

Otherwise run the configured pipeline:
`FLOW="${LOGICPILOT_FLOW:-}"
if [ -z "$FLOW" ]; then
  if [ -f ./codex/flow/logicpilot.py ]; then
    FLOW="./codex/flow/logicpilot.py"
  else
    FLOW="${CODEX_HOME:-$HOME/.codex}/logicpilot/flow/logicpilot.py"
  fi
fi; python3 "$FLOW" all --config flow.toml`

**v0.6 deprecation note**: the default `all` run now includes `plan-check`
in soft mode (warn-only, exit 0). Warnings carrying the prefix
`[DEPRECATION-WILL-FAIL-IN-v0.7b]` mark issues that will hard-fail in
v0.7b. Two escape hatches:
- `--no-plan-gate` — skip the planning gate entirely (= v0.5.x behavior)
- `LOGICPILOT_STRICT=1` (env) — preview v0.7b hard-fail today

## After running, read

Single-stage mode prints one JSON object; pipeline mode (`all`) prints a
top-level `{pipeline, overall, results: [...]}`.

- `status` per stage — `pass` / `fail` / `blocked` / `timeout`. **`blocked` is
  environment (tool/file/preset missing), `fail` is design/config/test** —
  never report them interchangeably.
- `overall` (pipeline) — derived: any `fail` ⇒ `fail`; else any `timeout` ⇒
  `timeout`; else any `blocked` ⇒ `blocked`; else `pass`.
- `warnings` per stage — auto-elevated flags (timing miss WNS<0, latch,
  multi-driver, no PASS/FAIL marker, check failures); `pass` + `warnings`
  is a soft fail.
- `metrics` per stage — Fmax/WNS/TNS, LUT/FF/BRAM/DSP, power numbers, error
  counts.
- `tail` per stage — first failing line usually here.

Report passed / failed / blocked stages, utilization, Fmax/WNS, power
metrics + `assumptions`, and the first actionable warning. **Confirm
testbench PASS/FAIL, not just tool exit codes.** Full schema:
`../../docs/JSON-CONTRACT.md`.
