---
description: Auto-generate baseline SDC from the CDC inventory + project clocks
---

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" constraints --config flow.toml
```

Use `hardware-constraints`. The generator reads `[project].clock_mhz`,
`[clocks]`, and `docs/cdc-inventory.json`, then writes
`build/auto.sdc` (or `[constraints].output`).

## What gets generated

- `create_clock` per declared clock (period from `clocks[].period_ns`,
  fallback to `[project].clock_mhz`).
- `set_clock_groups -asynchronous` for every distinct cross-domain
  pair in the inventory.
- `set_max_delay` for safe multi-bit CDC bus crossings through a
  2FF / 3FF synchronizer — with a **`<TODO:>` placeholder** for the
  destination sync-flop's first-FF D pin (the inventory doesn't carry
  the leaf instance; user finishes the `-to` clause).
- `set_false_path` for crossings explicitly waived
  (`verdict: waived` + `synchronizer: none`), with the recorded
  rationale as a comment.

## What is NOT generated (user must supply)

- `set_input_delay` / `set_output_delay` — board-dependent.
- `create_generated_clock` for PLLs / dividers — needs RTL parsing.
- `set_multicycle_path` — your slow-path annotations.

## After running, read

- `status` — `pass` / `blocked` / `fail` / `dry-run`.
- `sdc_path` — relative path where the SDC was written.
- `summary` — `{clocks_declared, clock_groups_declared,
  max_delays_declared, false_paths_declared, todo_placeholders}`.
- `warnings` — `todo_placeholders > 0` means the SDC isn't sign-off
  ready; fill the placeholders before handing off.
- `tail` — last 25 lines of the generated SDC.

The stage is **opt-in**: add `constraints` to `[pipeline].order`
(typically right after `cdc-check` and before `synth`) when you want
the auto-generated SDC. Projects with a hand-maintained SDC ignore it.

Full schema: `docs/JSON-CONTRACT.md`. Vendor-by-vendor template
reference: `hardware-constraints/references/sdc-templates.md`.
