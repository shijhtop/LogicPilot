---
description: Detect available local EDA tools and stage readiness
---
Run workspace discovery:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" --tools --config flow.toml
```

Report which stages are runnable, which are blocked, and which tool probes were found.
In untrusted workspaces this uses safe-preset mode, so project-local stage
commands are not considered until the project is locally trusted. Do not recommend changing tools unless the user asks; treat the workspace configuration as the source of truth.

## After running, read

`--tools` returns one object per declared stage. Per entry:

- `stage` — stage name
- `tool` — first runnable candidate, or `null` if none found
- `status` — `runnable` / `blocked` (env / file / preset issue) / `disabled`
- `candidates[*]` — `{tool, probes_passed, probes_failed}`; explains why each candidate was accepted or rejected
- `missing` — list of probes that failed for the chosen candidate (when `blocked`)
- `safe_preset_mode` — top-level boolean; true ⇒ project commands ignored, only shipped presets are considered

Report blocked stages as **environment**, not as design defects. Full schema: `docs/JSON-CONTRACT.md`.
