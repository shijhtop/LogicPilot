---
description: Validate the CDC inventory against the v1 schema + truth table
---
Run the cdc-check stage via the driver:

```bash
FLOW="${LOGICPILOT_FLOW:-}"
if [ -z "$FLOW" ]; then
  if [ -f ./codex/flow/logicpilot.py ]; then
    FLOW="./codex/flow/logicpilot.py"
  else
    FLOW="${CODEX_HOME:-$HOME/.codex}/logicpilot/flow/logicpilot.py"
  fi
fi
python3 "$FLOW" cdc-check --config flow.toml
```

To also enable the AST-only rules (R7 / R8) below, prepend
`--experimental-ast` (requires `verible-verilog-syntax` on PATH):

```bash
python3 "$FLOW" --experimental-ast cdc-check --config flow.toml
```

Without the flag, the envelope's `audit_engine` field is `regex` and
R7/R8 are silently skipped.

`cdc-check` reads `docs/cdc-inventory.json` (override via
`[cdc].inventory` in `flow.toml`) and validates:

1. Schema shape (required top + per-crossing keys).
2. Truth table — `payload_kind × synchronizer` membership.
3. `verdict: unsafe` requires `rationale`; `verdict: waived` requires
   `rationale + evidence{file, line}`.
4. `set_clock_groups_declared: false` + crossings non-empty → fail.
5. `synchronizer: "none"` always implies unsafe unless waived.

**Workflow**: Produce the inventory first by walking the RTL with the
reviewer pattern (Codex prompt `/lp-cdc-review` once shipped, or hand-
craft following `docs/schemas/cdc-inventory.schema.json`). Then run
`cdc-check` to verify.

`cdc-check` is **opt-in** — it's built-in but NOT in the default `all`
pipeline. Run it explicitly when CDC matters (any design with 2+
unrelated clocks, gated clocks, or async resets).

## After running, read

JSON envelope per `docs/JSON-CONTRACT.md`. Key fields:

- `status: blocked` ⇒ inventory file missing.
- `status: fail` ⇒ each `findings[*]` row has `rule` + `message` +
  optional `crossing_index` for the offending entry.
- `by_verdict` summarizes the inventory (`safe`, `unsafe`, `waived`).
- `summary` totals findings by severity.

If you see the `[DEPRECATION-WILL-FAIL-IN-vX.Y]` prefix in `warnings[]`,
treat it as "pending deprecation" regardless of the top-level `status`.

AST-only rules (require `--experimental-ast` + `verible-verilog-syntax`):

- **R7** — flags signals whose LHS clocked drivers span ≥2 clock
  domains when no inventory row mentions the signal. Catches
  accidental multi-clock writes / dual-port memory writes from two
  domains. **Does NOT catch** write-in-A-read-by-sync-in-B CDC (needs
  RHS-read traversal; deferred).
- **R8** — warns when an inventory crossing references a signal AST
  can't find any clocked driver for (likely a stale row).

Without the flag the envelope's `audit_engine` is `regex` and R7/R8
do not run.
