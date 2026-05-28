---
description: Scaffold a new LogicPilot project in the current directory
---
Scaffold the workspace via the driver. Two modes:

```bash
FLOW="${LOGICPILOT_FLOW:-}"
if [ -z "$FLOW" ]; then
  if [ -f ./codex/flow/logicpilot.py ]; then
    FLOW="./codex/flow/logicpilot.py"
  else
    FLOW="${CODEX_HOME:-$HOME/.codex}/logicpilot/flow/logicpilot.py"
  fi
fi

# Minimal: flow.toml + .gitignore + src/ + tb/
python3 "$FLOW" --init --hdl systemverilog --target open-fpga --scope block --top my_ip

# With templates: also docs/{spec,uarch,plan}.md with <<FILL:>> placeholders
python3 "$FLOW" --init --with-templates \
    --hdl systemverilog --target open-fpga --scope block --top my_ip
```

Codex tip: prefer flags over interactive prompts (Codex sessions don't
always have an interactive stdin). `--non-interactive` skips all prompts
and uses defaults for missing fields.

**Safe to re-run.** Existing files appear in `skipped`, never overwritten.

## After running, read

JSON envelope per `docs/JSON-CONTRACT.md`. Key fields:

- `status: pass` — at least one new file was created.
- `status: blocked` — everything already existed (re-run on populated repo).
- `mode` — `minimal` or `with-templates`.
- `created[]` — list of new file paths.
- `skipped[]` — list of paths that already existed.
- `next_step` — multi-line banner; show verbatim to the user.

If `--with-templates`: the immediate next `/lp-front` will fail at
plan-check because `<<FILL:>>` placeholders need real content. That's
**intentional** — drive the brainstorm round via the
`hardware-design-planning` skill to fill them in.
