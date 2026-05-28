---
description: Auto-generate baseline SDC from the CDC inventory + project clocks
---

Run `FLOW="${LOGICPILOT_FLOW:-}"
if [ -z "$FLOW" ]; then
  if [ -f ./codex/flow/logicpilot.py ]; then
    FLOW="./codex/flow/logicpilot.py"
  else
    FLOW="${CODEX_HOME:-$HOME/.codex}/logicpilot/flow/logicpilot.py"
  fi
fi; python3 "$FLOW" constraints --config flow.toml`, then use the `hardware-constraints` skill to read the envelope and decide whether the SDC needs hand edits.

## Generated

- `create_clock` per clock from `cdc-inventory.json` (or
  `[project].clock_mhz` fallback)
- `set_clock_groups -asynchronous` for every cross-domain pair
- `set_max_delay` for safe 2FF / 3FF CDC bus crossings (with `<TODO>`
  for the destination sync-flop instance — the inventory doesn't pin it)
- `set_false_path` for waived unprotected crossings (rationale shown)

## Not generated (user must supply)

- I/O delay (board timing)
- `create_generated_clock` for PLLs
- `set_multicycle_path`

## After running, read

- `status` — `pass` / `blocked` / `fail`
- `sdc_path` — where the SDC landed
- `summary.todo_placeholders > 0` ⇒ SDC NOT sign-off ready;
  finish the `<TODO:>` placeholders first
- `warnings`, `tail`

Full schema: `../../docs/JSON-CONTRACT.md`.
