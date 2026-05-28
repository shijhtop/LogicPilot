---
name: hardware-power-analysis
description: >-
  Estimate, report, and reduce FPGA/ASIC power. Use whenever the user asks about power, energy, thermal, current draw, battery life, toggle activity, SAIF/VCD power annotation, clock gating, power budget, or report_power / report_power_analysis outputs.
---

# Hardware Power Analysis

Power numbers are useful only when the assumptions are visible. Separate early
vectorless estimates from activity-annotated analysis, and never mix synthesis,
post-route, and signoff numbers without naming the stage.

## Workflow

1. Confirm the design is functionally verified enough to produce representative
   activity.
2. Prefer simulation-derived activity:
   - FPGA/vendor: VCD or SAIF from the self-checking testbench.
   - ASIC: SAIF/VCD, SPEF/RC, liberty/operating corner, voltage and temperature.
3. Configure `flow.toml`:
   ```toml
   [activity]
   saif_file = "build/sim.saif"        # or vcd_file = "build/wave.vcd"
   instance = ""                       # optional DUT instance/scope

   [power]
   total_budget_w = 1.5
   temperature_c = 85
   voltage = "nominal"
   ```
4. Run the power stage when the active preset defines it:
   ```bash
   python3 <flow>/logicpilot.py power --config flow.toml
   ```
5. Read JSON:
   - `status` tells whether the tool ran.
   - `metrics` contains `total_power_w`, `dynamic_power_w`,
     `static_power_w`, and optional component buckets such as
     `clock_power_w`, `logic_power_w`, `signal_power_w`, `bram_power_w`,
     `dsp_power_w`, `io_power_w`, `junction_temp_c`, and `thermal_margin_c`.
   - `assumptions.activity_source` must be `saif` or `vcd` before treating the
     result as actionable. `vectorless/default` is an early estimate only.
   - `warnings` flags missing power parsing, default switching activity, and
     power-budget violations.
6. Report whether the number is early estimate, post-route estimate, or signoff.

## Report shape

Use this human-readable structure:

```markdown
# Power Report

## 1. Conclusion
- Status:
- Stage/tool:
- Confidence: SAIF/VCD annotated | vectorless estimate
- Budget result: pass/fail/unknown

## 2. Assumptions
- Activity source:
- Activity file / DUT scope:
- Clock frequency:
- Voltage / temperature / process corner:
- Design stage: synth | post-route | signoff

## 3. Power summary
| Metric | Value |
|---|---:|
| Total power | ... W |
| Dynamic power | ... W |
| Static/leakage power | ... W |
| Junction temperature | ... °C |

## 4. Dynamic power breakdown
| Bucket | Power |
|---|---:|
| Clock | ... W |
| Logic | ... W |
| Signals/interconnect | ... W |
| BRAM/SRAM | ... W |
| DSP | ... W |
| I/O | ... W |

## 5. Risks and actions
- Highest bucket:
- Clock/reset/high-fanout risks:
- Activity coverage gaps:
- RTL/constraint/implementation changes:
```

## Optimization playbook

- Reduce **clock power** with clock enables, lower fanout, generated enables
  instead of ad-hoc divided clocks, and narrower active regions. Use true clock
  gating only when the technology/library/FPGA primitive supports it safely.
- Reduce **logic/signal dynamic power** by cutting unnecessary toggles, adding
  valid/enable guards, pipelining long glitchy combinational cones, one-hot or
  Gray coding only where it lowers switching, and avoiding free-running counters.
- Reduce **memory power** with BRAM/SRAM enable pins, banking, fewer read ports,
  narrower accesses, and avoiding read-during-idle.
- Reduce **DSP power** by using clock enables, operand isolation, and pipelined
  DSP inference rather than LUT multipliers.
- Reduce **I/O power** with lower drive strength, fewer toggling pins, lower I/O
  voltage where legal, and protocol-level idle states.
- Static/leakage power is mostly device/process/temperature dependent; for RTL,
  focus on resource count and thermal conditions.

## Definition of done

A power report states total/dynamic/static power, activity source, stage,
frequency/corner assumptions, budget result, and at least one concrete reduction
path for the dominant power bucket.
