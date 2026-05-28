---
description: Run post-implementation power analysis (VCS SAIF → Vivado report_power)
argument-hint: "[optional: activity note]"
---

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" power --config flow.toml
```

Use `hardware-power-analysis`. Focus/activity note: $ARGUMENTS

## Requirements

- **Vivado** on PATH (required — runs `report_power`)
- **Post-implementation checkpoint** `build/{top}_impl.dcp` (run `pnr` first)

## Activity annotation priority

| Source | How |
|---|---|
| `[activity].saif_file` in flow.toml | User-provided SAIF, used as-is |
| `vcs` on PATH | SAIF generated automatically from simulation |
| Neither | Vectorless estimate only |

VCD is not used. Vectorless is acceptable for early exploration but not for sign-off.

## After running, read

- `status` — `blocked` = Vivado not found or checkpoint missing
- `activity` — `saif:path` (annotated) or `vectorless (...)` (unannotated)
- `metrics.total_power_w` / `metrics.dynamic_power_w` / `metrics.static_power_w`
- `assumptions` — **always state this when reporting power**; a vectorless estimate without disclosure is misleading
- `warnings` — budget overrun when `[power].total_budget_w` is configured

Full schema: `docs/JSON-CONTRACT.md`.
