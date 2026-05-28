---
description: Health check — answers 'can I run LogicPilot here?' in one shot
---
Run the health check via the LogicPilot driver:

```bash
FLOW="${LOGICPILOT_FLOW:-}"
if [ -z "$FLOW" ]; then
  if [ -f ./codex/flow/logicpilot.py ]; then
    FLOW="./codex/flow/logicpilot.py"
  else
    FLOW="${CODEX_HOME:-$HOME/.codex}/logicpilot/flow/logicpilot.py"
  fi
fi
python3 "$FLOW" --doctor --config flow.toml
```

Unlike `--tools` (which answers "what's installed on this machine"),
`--doctor` answers **"given this project + this machine + this config,
can the user actually run the flow today, and if not, what's the
cheapest fix"**.

`--doctor` runs even when `flow.toml` is missing — that's one of the
gaps it diagnoses. Do not refuse to invoke it just because the config
isn't there yet.

## After running, read

JSON envelope per `docs/JSON-CONTRACT.md` with a `checks: [...]` row
per probe. Order:

1. `python_version` — runtime supports the driver (3.11+ native, or
   3.10 + tomli).
2. `flow_toml` — present + parses + schema-clean. `status: warn` means
   typos found; the `warnings` array carries did-you-mean suggestions.
3. `workspace_trust` — project trusted on this machine? `warn` means
   project-local stage commands will be skipped (safe-preset mode).
4. `stage:<name>` — per declared project stage: runnable / blocked.
   Blocked rows carry `install_hint` per missing tool.
5. `smoke_test` — built-in report stage smoke (proves driver wiring).

Top-level `install_hint` is the union of all per-stage hints — show
that to the user instead of scanning rows.

Use the top-level `status` (fail > blocked > warn > pass) for go/no-go.
The prefix `[DEPRECATION-WILL-FAIL-IN-vX.Y]` may appear in any
`warnings[]` array — treat such a result as "pending deprecation, fix
before next milestone".
