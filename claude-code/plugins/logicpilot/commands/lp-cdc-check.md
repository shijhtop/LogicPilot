---
description: Run CDC check — SpyGlass CDC if available, otherwise Verilator --cdc. Skipped automatically on single-clock designs.
---
Run the CDC check stage:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" cdc-check --config flow.toml
```

## When it runs

The stage detects clocks automatically before deciding whether to proceed:

1. Reads `[cdc].clocks` from `flow.toml` if declared (explicit, authoritative).
2. Otherwise scans RTL source files for `posedge`/`negedge` sensitivity lists.

- **≤1 clock found** → `status: skip` — single-clock design, no CDC to check.
- **≥2 clocks found** → proceeds to tool selection.

To declare clocks explicitly (recommended for reliability):

```toml
[cdc]
clocks = ["clk_sys", "clk_usb"]
```

## Tool priority

| Tool | Binary probed | Notes |
|---|---|---|
| SpyGlass CDC | `sg_shell` | Commercial. Set `[cdc].spyglass_script` for full library/SDC setup. |
| Verilator | `verilator` | Free. Uses `--cdc` mode. Catches common CDC warnings. |
| blocked | neither found | `status: blocked` with `install_hint`. |

SpyGlass is tried first. Verilator is the fallback. If neither is installed,
the stage reports `blocked` rather than silently passing.

## SpyGlass setup (optional but recommended)

Without `[cdc].spyglass_script`, a minimal inline TCL is used — suitable only
for small designs without library cells. For real projects:

```toml
[cdc]
clocks = ["clk_sys", "clk_ddr"]
spyglass_script = "scripts/cdc.tcl"  # your project TCL with libs + SDC
```

## Reading the result

```json
{
  "stage": "cdc-check",
  "status": "pass | fail | skip | blocked | timeout",
  "tool": "spyglass | verilator",
  "clocks": ["clk_sys", "clk_usb"],
  "violations_total": 3,
  "violations": [
    {"rule": "Ac_unsync01", "severity": "high", "message": "..."},
    {"rule": "CDCRstLogic", "file": "top.sv", "line": 42, "severity": "high", "message": "..."}
  ],
  "tail": "..."
}
```

- `status: skip` — single-clock design; CDC check not applicable.
- `status: blocked` — multi-clock design but no CDC tool installed.
- `status: fail` — violations found; each entry in `violations` is one finding.
- `violations[*].severity: "high"` — errors that block sign-off.
- `violations[*].severity: "medium"` — warnings worth reviewing.

Fix each high-severity violation in the RTL before declaring CDC clean.
Use `hardware-cdc` skill for synchronizer pattern guidance.
