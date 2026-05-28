# Power reporting reference

## Confidence levels

- **Vectorless/default:** no representative activity. Good for early comparison
  between RTL alternatives, not for a power budget signoff.
- **Simulation annotated:** VCD/SAIF from a representative self-checking test.
  Good for engineering review if the test covers realistic traffic, idle states,
  burst behavior, and resets.
- **Post-route/signoff annotated:** placed/routed parasitics plus annotated
  activity and proper voltage/temperature/process corner. This is the number to
  use for thermal and supply sizing.

## What to preserve in reports

Always preserve:
- tool/stage and report path;
- activity source and DUT scope;
- clock frequencies and generated clocks;
- voltage/temperature/process corner;
- total/dynamic/static split;
- per-resource dynamic buckets;
- whether the design meets the power budget.

## Common interpretation traps

- A low vectorless estimate may hide high switching in real traffic.
- A VCD from a reset-only or smoke test underestimates dynamic power.
- A SAIF/VCD from a testbench with unrealistic always-ready downstream logic can
  overstate or understate toggle activity depending on the design.
- Clock and reset networks can dominate dynamic power in small FPGA designs.
- Optimizing for timing by replication or high fanout buffering can raise power;
  correlate timing closure changes with the power report.
