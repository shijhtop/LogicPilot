# CDC tool waivers — file management

When commercial CDC tools (SpyGlass CDC, Questa CDC, JasperGold CDC) run
on a real project, they produce **hundreds to thousands** of violations.
Most are real, some are false positives, some are intentional. Waiving
them blindly destroys the value of the tool; tracking them is engineering
work in itself.

## What a waiver MUST carry

Every waived violation row must record:

| Field | Why |
|---|---|
| `rule_id` | The tool's violation ID (e.g. `Ac_unsync01`, `clock_glitch01`) |
| `scope` | Hierarchical path: `top.subsys.module.signal` |
| `owner` | A real person — not "team" or "TBD" |
| `expiry` | A date or release tag. **No "forever" waivers.** |
| `rationale` | One paragraph: *why* the tool is wrong OR *why* the risk is accepted |
| `evidence` | RTL file / line, or design-review meeting ID, or formal-proof reference |
| `re_review_trigger` | What event invalidates the waiver: "rewrite of sync_2ff", "next process node", "every release", etc. |

A waiver without owner + expiry + evidence is **not a waiver, it's a
silence button** — and the next run will re-add the same violation
because the tool has no idea why it was suppressed.

## Categories — keep them separate

Don't dump every waived rule into one file. Split by root cause so audits
are tractable:

- **`waivers/false-positives.tcl`** — tool genuinely wrong (e.g. unrolled
  loop the tool can't analyse). Re-review when tool version changes.
- **`waivers/known-issues.tcl`** — real CDC concern accepted for THIS
  release with a fix scheduled. Each entry's expiry = the planned fix
  release.
- **`waivers/architectural.tcl`** — by-design async behaviour the tool
  can't model (e.g. JTAG, async config bits set before clocks start).
  Re-review every major spec change.
- **`waivers/legacy.tcl`** — inherited IP, no current owner. Each entry
  needs an explicit accept-as-is signoff from the IP integrator.

## Re-review cadence

| Trigger | What gets re-reviewed |
|---|---|
| Every CI run | nothing — waivers are honored |
| Every release | every waiver in `known-issues.tcl` (must be fixed or re-justified) |
| Tool version change | every waiver in `false-positives.tcl` (tool may now catch / mis-catch differently) |
| RTL refactor of a module | every waiver scoped to that module |
| Process / library / target change | architectural waivers re-evaluated |

## Forbidden patterns

- ❌ **Wildcard waivers** like `waive -rule * -module foo` — only line up
  with explicit rule IDs.
- ❌ **Waiving by violation count** — "we had 234 of these, now we have
  235, must be a new bug" goes wrong when both real and accepted
  violations move together. Waive by stable identifier.
- ❌ **Waivers in RTL comments** — `// noqa: cdc` style. Tool can't see
  them; the waiver and the rule live in different files and drift apart.
- ❌ **"Will fix next sprint" with no expiry** — these accumulate
  indefinitely. Always set an expiry date.

## Integration with `cdc-inventory.json`

LogicPilot's `cdc-check` stage validates the architectural inventory
(payload × synchronizer × verdict). A `verdict: "waived"` row in the
inventory is the equivalent of an architectural waiver above:
`rationale` + `evidence` are mandatory. Tool-level waivers (rule-id
scoped, vendor-specific) live in vendor TCL / config files, not in the
inventory.

Both layers must agree: if `cdc-inventory.json` says a crossing is
`safe` with `synchronizer: 2ff`, then a CDC tool waiver saying "the
2FF is missing" is a contradiction — fix one of the two before
shipping.
