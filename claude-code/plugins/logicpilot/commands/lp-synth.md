---
description: Run synthesis and interpret reports
---

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" synth --config flow.toml
```

Use `hardware-synthesis`. Trace failures back to RTL/config/constraints.

## Synthesizer recommendation (advisory, not enforced)

Pick by project target. If the preferred tool isn't installed, fall back — but **always state which tool ran** so "passed under yosys" doesn't sound like "passed under Vivado" on an FPGA project.

| Target | Recommended | Fallback |
|---|---|---|
| FPGA (Xilinx/AMD) | `vivado` | `yosys` (exploratory only) |
| FPGA (Intel/Altera) | `quartus_sh` | `yosys` (exploratory only) |
| ASIC | `dc_shell` (Design Compiler) | `yosys` (exploratory only) |
| Anything when neither is installed | `yosys` | — |

Numbers from `yosys` on an FPGA project are exploratory, NOT authoritative — say so explicitly when reporting them.

## After running, read

- `status` — `blocked` = synth tool missing; `fail` = synth ran and complained
- `metrics.wns_ns` / `metrics.tns_ns` / `metrics.fmax_mhz` — timing; **negative WNS auto-promotes to a `warnings` entry** even on returncode 0
- `metrics.lut` / `metrics.ff` / `metrics.bram` / `metrics.dsp` — utilization
- `warnings` — auto-elevated: latch inference, multi-driver, timing miss, stage checks failed
- `tail` — first failing constraint or synth error usually here

For power/thermal questions, run `/lp-power` — do not infer power from utilization. Full schema: `docs/JSON-CONTRACT.md`.
