# LogicPilot — Agent Instructions

This repository uses a generic, front-end-first hardware workflow. The default flow is:

```text
spec → micro-architecture → RTL/SV modeling → source audit → TB audit → lint → simulation / verification → synthesis → optional power/backend → report
```

Back-end and power stages are optional and should only be entered when the user asks for FPGA implementation/programming, ASIC physical implementation/sign-off, or power/thermal/current/budget analysis.

## Driver

Use the generic entrypoint when possible. Prefer `$LOGICPILOT_FLOW`; if unset in a marketplace install, use the packaged fallback `codex/flow/logicpilot.py`.

```bash
FLOW="${LOGICPILOT_FLOW:-}"
if [ -z "$FLOW" ]; then
  if [ -f ./codex/flow/logicpilot.py ]; then
    FLOW="./codex/flow/logicpilot.py"
  else
    FLOW="${CODEX_HOME:-$HOME/.codex}/logicpilot/flow/logicpilot.py"
  fi
fi
python3 "$FLOW" <stage> --config flow.toml
python3 "$FLOW" tb-audit --config flow.toml
python3 "$FLOW" report --config flow.toml
python3 "$FLOW" --tools --config flow.toml
```

`logicpilot.py` is the canonical entrypoint.

## Working agreements

- Start every unfamiliar workspace with `--tools` and `--list`.
- Do not assume a specific EDA suite. Use whatever the project config and workspace make available.
- Synthesis and everything before synthesis are considered the front-end flow.
- Run the built-in `audit` stage on unfamiliar/non-trivial RTL before lint; for SystemVerilog, review packages, `$unit`, types, enums, interfaces, and model boundaries.
- Run `tb-audit` before trusting a new or non-trivial testbench.
- Verify before synthesizing: audit, lint, and simulation must be understood before trusting synthesis reports.
- Read JSON `status`, `tool`, `metrics`, `warnings`, `assumptions` when present, and `tail`; do not claim success from exit code alone.
- Fix root causes in RTL, testbench, constraints, or project config; do not mask failures.
- Change one class of thing per iteration so metric movement is interpretable.

## Skills

Use generic front-end skills by default:

- `hardware-design-discipline`
- `hardware-design-planning`
- `hardware-rtl-design`
- `hardware-rtl-audit`
- `systemverilog-design-modeling`
- `hardware-synthesizable-coding`
- `hardware-reset-design`
- `hardware-fsm-design`
- `hardware-cdc`
- `hardware-constraints`
- `hardware-interfaces`
- `hardware-simulation`
- `hardware-verification`
- `systemverilog-verification-platform`
- `hardware-synthesis`
- `hardware-power-analysis`

Use the FPGA-specific skills when the design targets an FPGA:

- `fpga-architecture-optimization` — RTL-stage pipelining / fanout / resource inference
- `fpga-timing-closure` — post-synth / post-pnr WNS / TNS / utilization iteration

## Tools

- `markitdown` (`~/.venv/bin/markitdown`): Convert various file formats (PDF, DOCX, PPTX, XLSX, images, etc.) to Markdown.
