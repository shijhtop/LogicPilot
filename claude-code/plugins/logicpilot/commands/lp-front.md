---
description: "Run the default front-end flow: plan-check → audit → tb-audit → lint → sim → synth"
---
Run front-end stages in order. The first stage (`plan-check`) gates the chain
on `docs/spec.md`, `docs/uarch.md`, `docs/plan.md` — if those are missing or
the strict tables in spec.md are empty, stop and apply `hardware-design-planning`
to produce them before re-running.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" plan-check --config flow.toml
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" audit      --config flow.toml
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" tb-audit   --config flow.toml
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" lint       --config flow.toml
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" sim        --config flow.toml
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" synth      --config flow.toml
```

If the user is iterating on RTL and has already accepted the planning trade-off
for this session, you can skip the gate by starting from `audit`. The other
`/lp-*` stage commands (`/lp-sim`, `/lp-synth`, …) do not gate on plan-check by
design, so per-stage iteration stays fast.

Use `hardware-rtl-audit`, `systemverilog-verification-platform`,
`hardware-simulation`, and `hardware-synthesis` as needed.

## After running, read (every stage in the chain)

Each invocation prints a single JSON object. Read it per-stage and surface
the worst result rather than just the last:

- `status` — `pass` / `fail` / `blocked` / `timeout`. **`blocked` is an
  environment issue, `fail` is a design/config/test issue** — never report
  them interchangeably.
- `warnings` — driver-elevated flags (timing miss, latch, no PASS/FAIL marker,
  unseeded random, check failures); treat `pass` + `warnings` as a soft fail
  pending explicit waiver.
- `metrics` — stage-specific (audit: `summary`, `findings`; lint/synth:
  WNS/TNS/utilization; sim: errors/warnings counts; power: `total_power_w`
  + `assumptions`).
- `tail` — first failing line is usually here.

Halt the chain on `fail` / `blocked` / `timeout` and report which stage and
why before proceeding. Full schema: `docs/JSON-CONTRACT.md`.
