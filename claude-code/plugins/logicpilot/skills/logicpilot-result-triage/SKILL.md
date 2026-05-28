---
name: logicpilot-result-triage
description: Use when interpreting LogicPilot JSON output from lp-run, lp-front, lp-doctor, or any logicpilot.py stage result, especially when deciding whether the next action is an environment fix, RTL/test fix, waiver, or report summary.
---

# LogicPilot Result Triage

LogicPilot results are structured contracts. Read the JSON first; do not infer
success from exit code or friendly prose.

## Triage Order

1. **Classify status.**
   - `fail`: design/config/test failed. Read `tail`, `warnings`, and `checks`.
   - `blocked`: environment or input missing. Report missing tools/files and
     `install_hint`; do not call it an RTL bug.
   - `timeout`: budget/runtime issue. Report `timeout_s`, `tail`, and likely
     stage cost.
   - `pass`: still inspect `warnings`, `metrics`, and stage-specific fields.
   - unknown status: treat as `fail`.

2. **Use `overall` for pipelines, then drill into `results[]`.** Summarize
   the first actionable non-pass stage before listing secondary warnings.

3. **Quote command trust.** If `command_source` is present, include it when
   recommending execution:
   - `shipped_preset`: packaged LogicPilot command.
   - `project_config`: project-local command; inspect or dry-run before
     running on an untrusted checkout.

4. **Handle pass-with-warnings as unresolved.** Timing misses, latch inference,
   multi-driver patterns, missing PASS/FAIL markers, vectorless power, and
   failed `checks` are action items unless explicitly waived.

5. **Report metrics with context.** For timing, include WNS/Fmax when present.
   For power, always include `assumptions.activity_source`; vectorless numbers
   are estimates, not sign-off.

## Output Shape

Use this order:

1. Verdict: `pass`, `fail`, `blocked`, `timeout`, or `pass with warnings`.
2. Cause: one sentence tied to the stage and JSON field.
3. Next action: exact environment, RTL, testbench, constraint, or waiver step.
4. Evidence: stage name, tool, `command_source`, key warning/metric, and log path
   if present.

Keep the report short. If many stages failed, group by status and lead with the
earliest pipeline blocker.

## Common Mistakes

- Treating `blocked` as a design failure.
- Treating `pass` as clean while `warnings` are present.
- Reporting power without activity assumptions.
- Ignoring `command_source` before advising an agent to execute project-local
  shell commands.
- Pasting long log tails instead of extracting the first actionable line.
