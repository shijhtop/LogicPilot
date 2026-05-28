---
description: Run optional back-end stages defined by the project
argument-hint: "[stage: pnr | power | gls | lec]"
---
Run only the back-end stage the user requested. Validate the stage name before
executing; do not pass arbitrary text to the shell.

```bash
stage="$ARGUMENTS"
case "$stage" in
  pnr|power|gls|lec)
    python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" "$stage" --config flow.toml
    ;;
  "")
    python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" --list --config flow.toml
    ;;
  *)
    echo "invalid backend stage: $stage (only pnr|power|gls|lec are in default STAGE_ORDER)"
    ;;
esac
```

If `$ARGUMENTS` is empty, inspect `--list` and ask which back-end stage to run.

**Important — there is NO built-in code for back-end stages.** Only the
stage NAMES are pre-registered in `STAGE_ORDER`. The runner shell-execs
the `cmd` you put in `[stages.<name>]` in `flow.toml`. Without a
`flow.toml` entry, the stage returns `status: skipped` ("not defined in
config"). Names beyond `pnr|power|gls|lec` (e.g. `floorplan` / `place` /
`cts` / `route` / `signoff` / `gds`) are NOT shipped — declare them as
project-specific stages with their own `cmd` if you need them.

## After running, read

Back-end stages share the common runtime-stage JSON shape:

- `status` — `pass` / `fail` / `blocked` / `timeout`; back-end tools are heavy, so timeout is a real risk
- `metrics` — stage-dependent:
  - `pnr` / `place` / `route`: `wns_ns`, `tns_ns`, `lut`, `ff`, `bram`, `dsp`
  - `power`: `total_power_w`, `dynamic_w`, `leakage_w` (+ `assumptions`)
  - `gls` / `lec` / `signoff`: tool-specific pass/fail markers
- `warnings` — auto-elevated: timing miss (WNS<0), latch/multi-driver from any netlist write-out, timeout, stage check failures
- `tail` — first failing constraint / mismatch usually here
- `log` — full log path; back-end logs are large, consult selectively

Back-end stages are **optional and explicit** — never auto-run after synthesis. Full schema: `docs/JSON-CONTRACT.md`.
