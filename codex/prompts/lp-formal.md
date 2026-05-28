---
description: Run formal verification on SystemVerilog assertions; gated behind --experimental-formal
---

Run `FLOW="${LOGICPILOT_FLOW:-}"
if [ -z "$FLOW" ]; then
  if [ -f ./codex/flow/logicpilot.py ]; then
    FLOW="./codex/flow/logicpilot.py"
  else
    FLOW="${CODEX_HOME:-$HOME/.codex}/logicpilot/flow/logicpilot.py"
  fi
fi; python3 "$FLOW" --experimental-formal formal --config flow.toml`, then use the `hardware-verification` skill to interpret the result.

## Backend recommendation (advisory)

Dispatches to whichever backend is on `PATH`:

- `sby` (SymbiYosys, open source) — **fully implemented**; recommended default
- `jaspergold` (Cadence) / `vcf` (Synopsys) / `qverify` (Siemens) — dispatch + envelope frozen, parser is a stub today; contribute via GitHub issue

Pin a specific backend with `[formal].backend = "..."` in `flow.toml`.

## After running, read

- `status` — `pass` / `fail` / `blocked` / `timeout`
- `tool` — backend that ran
- `properties` — per-assertion `PASS|FAIL|UNKNOWN`
- `counterexamples` — `[{property, trace, depth_hit}]` for every FAIL
- `summary` — `{pass, fail, unknown}` counts

`UNKNOWN` means the solver couldn't decide — NOT safe to treat as pass. `status: pass` with 0 FAILs and 0 UNKNOWNs is a real proof.

Full schema: `../../docs/JSON-CONTRACT.md`.
