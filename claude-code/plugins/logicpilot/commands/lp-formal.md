---
description: Run formal verification (BMC / prove / cover / live) on declared SystemVerilog assertions
argument-hint: "[optional: property name to scope to]"
---

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" --experimental-formal formal --config flow.toml
```

Use `hardware-verification` and `systemverilog-verification-platform`. Focus property: $ARGUMENTS

## Backend selection (advisory)

Formal stage is **vendor-agnostic** — dispatches to whichever backend is installed:

| Backend | Probe binary | Status | Notes |
|---|---|---|---|
| SBY (SymbiYosys) | `sby` | **fully implemented** | Open source. Free. Ships with OSS CAD Suite. Recommended default. |
| Cadence JasperGold | `jaspergold` | dispatch + envelope, parser stub | Commercial. License required. Contribute a parser via GitHub issue with anonymized log. |
| Synopsys VC Formal | `vcf` | dispatch + envelope, parser stub | Commercial. Same. |
| Siemens Questa Formal | `qverify` | dispatch + envelope, parser stub | Commercial. Same. |

First installed backend wins (probe order: sby → jaspergold → vcf → qverify). Pin a specific one with `[formal].backend = "sby"` in `flow.toml`.

## Configuration (`flow.toml`)

```toml
[formal]
mode      = "prove"           # bmc | prove | cover | live
depth     = 20                # cycles to unroll
engines   = ["smtbmc z3"]     # backend-specific; first that solves wins
top       = "my_module"       # defaults to [project].top
properties = []               # empty = run all asserts; list scopes
timeout_s = 600
```

## After running, read

- `status` — `pass` / `fail` / `blocked` / `timeout`. `blocked` = no backend installed OR `--experimental-formal` not set
- `tool` — which backend actually ran (`sby` / `jaspergold` / `vcf` / `qverify`)
- `mode`, `depth`, `engine_used` — what verification was attempted
- `properties` — `{name: "PASS|FAIL|UNKNOWN"}` per assertion (or `{<all>: PASS}` if SBY didn't break out per-property)
- `counterexamples` — for each FAIL, `{property, trace, depth_hit}` with VCD/FST path
- `summary` — `{pass, fail, unknown}` counts
- `warnings` — `[EXPERIMENTAL:formal] preview behaviour active` (expected; not a defect)

`status: pass` with 0 FAILs and 0 UNKNOWNs is a real proof. `UNKNOWN` means the solver timed out or the property isn't k-inductive — **NOT** safe to ship.

Full schema: `docs/JSON-CONTRACT.md`.
