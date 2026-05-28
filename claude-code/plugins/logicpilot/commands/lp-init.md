---
description: Scaffold a new LogicPilot project (flow.toml + src/ + tb/; optionally docs templates)
---
Scaffold the workspace:

```bash
# Minimal — flow.toml + .gitignore + src/ + tb/ (no docs templates)
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" --init

# With templates — also docs/{spec,uarch,plan}.md with <<FILL:>> placeholders
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" --init --with-templates
```

By default the driver prompts on stdin for HDL / target / scope / top.
Pass any combination via flags to skip those prompts:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" --init \
    --hdl systemverilog --target open-fpga --scope block --top my_ip
```

`--non-interactive` skips all stdin prompts and uses defaults for any
unspecified field (handy in CI / non-tty contexts).

**Safe to re-run.** Existing files are NOT overwritten — they appear in
the `skipped` array. The user can rerun `--init` on a populated repo
without losing work.

## After running, read

```json
{
  "stage": "init",
  "status": "pass | blocked",
  "mode": "minimal | with-templates",
  "choices": {"hdl": "...", "target": "...", "scope": "...", "top": "..."},
  "created": ["flow.toml", "src/.gitkeep", "tb/.gitkeep", ".gitignore"],
  "skipped": [],
  "next_step": "Next step: …"
}
```

- `status: pass` ⇒ at least one new file was created.
- `status: blocked` ⇒ everything already existed (probably a re-run on
  an already-scaffolded repo). Not an error — just nothing to do.
- `next_step` is a multi-line banner; show it to the user verbatim so
  they know what to do next (immediate plan-check failures from
  `<<FILL:>>` placeholders are **intentional** — surface that fact
  so they don't think they hit a bug).

If `--with-templates` was used and `created` includes `docs/*.md`,
the next `/lp-front` will fail at plan-check because the placeholders
need filling. That failure is the design — the agent should walk the
user through the brainstorm round (see `hardware-design-planning`
skill) to fill them.

Full schema: `docs/JSON-CONTRACT.md`.
