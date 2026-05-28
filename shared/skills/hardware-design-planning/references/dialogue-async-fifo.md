# Exemplar dialogue — multi-clock CDC (async FIFO)

> **Block scope** — a single IP. Output `docs/{spec,uarch,plan}.md`. For the
> project-scope flow (multiple subsystems, arch.md + subsystem tree) see
> `dialogue-soc-mldsa.md`.
>
> EXEMPLAR, not a template. Shows the questioning style for an inherently
> multi-clock design — CDC and reset-domain questions dominate, and getting
> any one of them wrong produces a silicon-level bug that still passes
> simulation.

## User brief

> "Async FIFO, between a 100 MHz domain and a 50 MHz domain, 32-bit data, depth 16."

## Agent analysis (not shown)

Clear parts: two asynchronous clocks, 32-bit, depth 16. Gaps: depth must be a
power of two to fit a Gray-coded pointer — is 16 confirmed? almost-full /
almost-empty thresholds? per-domain reset strategy (independent resets or a
shared async reset)? coordination between write-side and read-side reset?
FIFO behavior when both sides are reset together? Are "empty" / "full" in
the local domain correct (they should be conservative — never overflow, but
may stall when actually empty)? First-word fall-through or registered
output? Push-on-full / pop-on-empty behavior?

## Round 1 — key CDC decisions

```
1. Depth:
   A) 16 (power of two, Gray pointer works directly)  ★
   B) 15 (not a power of two, requires non-binary Gray — complexity goes up)
   C) Parameterized, but a power of two must be enforced

2. Pointer style:
   A) Gray-coded binary pointer, 2-FF synchronizer across the domain ★ (textbook approach)
   B) Token-passing handshake (rarely used in FIFOs, but workable)

3. Conservatism of full / empty flags:
   A) Each flag lives in its own domain, computed from the local pointer plus the
      synchronized far-side pointer ★
      (write-side full is conservative: may still say full right after the reader has just popped;
       read-side empty is conservative: may still say empty right after the writer has just pushed)
   B) Cross-domain combinational comparison
      → metastable, do not do this

4. Output registering:
   A) First-word fall-through (FWFT) — valid whenever non-empty ★
      (matches AXI-Stream and simple consumers)
   B) Show-ahead, with explicit read enable (legacy interface)

Pick A/A/A/A?
```

User: A/A/A/A.

## Round 2 — reset strategy (the second-largest source of CDC bugs)

```
5. Reset strategy:
   A) Two independent async resets, one per domain (wr_rst_n, rd_rst_n) ★
      Sync deassert within each domain; each side independently safe
   B) Single async reset, resetting both sides simultaneously
   C) Single async reset routed through per-domain synchronizers to each domain

6. FIFO behavior on partial reset (resetting only one side):
   A) Not supported — both resets must be asserted together (asserted in the TB) ★
      A partial reset breaks pointer synchronization; the simplest approach is to forbid it
   B) Read-side reset only: discard unread data, write side keeps its pointer
   C) Write-side reset only: undefined

7. Push on full:
   A) Silently dropped (and if a status pin is exposed, set STATUS.WR_OVF) ★
      The writer is responsible — the flag is telemetry, not flow control
   B) Block via the wr_valid handshake (do not allow wr_en when wr_full)
   C) Overwrite the oldest data (FIFO becomes a ring buffer)

8. Pop on empty:
   A) Return undefined data, set STATUS.RD_UDF ★
      The reader is responsible — never read while empty
   B) Block via the rd_valid handshake
   C) Return the previously popped value (latched)

Pick A/A/A/A?
```

User: A/A/A/A.

## Round 3 — auxiliary flags + edge cases

```
9. Almost-full / almost-empty:
   A) Configurable thresholds (AFULL_THRESH, AEMPTY_THRESH parameters) ★
      A common flow-control requirement in SoCs
   B) None (only FULL and EMPTY)
   C) Fixed at depth/2

10. Count / occupancy outputs:
    A) Each side reports occupancy in its own domain (conservative, with lag) ★
    B) A single shared count (would require CDC on a multi-bit count → forbidden)
    C) An approximate count is only valid when both sides are idle

11. Enforcement of power-of-two depth:
    A) Compile-time `$error` when DEPTH is not a power of two ★
    B) Silently round up to the next power of two
    C) Allow non-power-of-two, taking a slower path

12. Memory inference:
    A) Distributed RAM / register array (cheap at depth 16) ★
    B) BRAM (overkill at depth 16, consumes a BRAM another block might need)

Pick A/A/A/A?
```

User: A/A/A/A.

## What gets written into spec.md

Sections that emerge (note how heavy the CDC content is — it is required by
this kind of design itself, not by a template):

- Function
- Interfaces (wr_* and rd_* port groups + 2 clocks + 2 resets)
- Clocks (2 rows — wr_clk@100, rd_clk@50, related = async)
- Resets (2 rows — wr_rst_n, rd_rst_n; both async/low, sync-deassert within
  each domain)
- **CDC inventory** (a mandatory section here — one row per cross-domain
  signal: wr_ptr_gray → through 2-FF into the read domain; rd_ptr_gray →
  through 2-FF into the write domain; FIFO data is per-domain and does not
  cross)
- **Flag computation rules** (write-side full conservative: uses the local
  wr_ptr plus the synchronized rd_ptr; read-side empty conservative: uses
  the local rd_ptr plus the synchronized wr_ptr)
- Performance targets (per-side Fmax, throughput bounded by the slower side,
  worst-case latency = synchronizer depth + 1 cycle)
- Parameters (WIDTH=32, DEPTH=16, AFULL_THRESH, AEMPTY_THRESH)
- Failure modes (push-on-full, pop-on-empty, the simultaneous-reset
  requirement)
- Assumptions (resets are always asserted together; DEPTH enforced to be a
  power of two)

No CSRs (no host bus). No fixed-point. CDC inventory is its own section
because the entire purpose of this design is crossing.

## Allocation in uarch.md's file list

| path | role | test | artifact |
|------|------|------|----------|
| rtl/async_fifo_top.sv | top integration   | property/invariant                   | cross-domain ordering, no-loss, depth-16 invariants |
| rtl/wptr_gray.sv      | write pointer     | reference-model + property/invariant | python golden: binary↔gray conversion; invariant: exactly one bit changes between adjacent pointer values |
| rtl/rptr_gray.sv      | read pointer      | reference-model + property/invariant | python golden: binary↔gray conversion; invariant: exactly one bit changes between adjacent pointer values |
| rtl/sync_2ff.sv       | 2-FF synchronizer | property/invariant                   | structural invariant: the source net must be the output of a source-domain flop with no combinational logic in between; synchronizer chain depth >= 2; checked by the hardware-cdc structural audit (a separate flow stage), not by SVA |
| rtl/fifo_mem.sv       | dual-port RAM     | integration                          | covered by tb/async_fifo_smoke_tb.sv (named "fill_drain_all_entries") |
| rtl/flag_logic.sv     | full / empty compute | reference-model + property/invariant | python golden: compute the flag from the (local_ptr, synced_ptr) pair; invariant: the flag is conservative in the safe direction |

`flag_logic` is deliberately dual-bucketed: the flag value is deterministic
(reference-model), and it must be conservative in the correct direction
(invariant — the empty side may say "empty" when not empty, but not the
reverse; the full side may say "full" when not full, but not the reverse).
Reference-model alone misses the directional asymmetry that makes the async
FIFO genuinely safe.

`wptr_gray` and `rptr_gray` both need both: the binary↔gray mapping is
deterministic (golden check function arithmetic), and the rule that
"adjacent output pointer values differ by exactly one increment" is the
foundation of 2-FF synchronizer safety. Even if surrounding logic skips or
duplicates an increment on certain edges, a correctly encoded Gray function
will still pass the golden — the values emitted by that kind of
pointer-step bug each look like a legal Gray code on their own, but break
the synchronizer chain. The golden catches encoding errors; the invariant
catches timing errors.

`sync_2ff` is `property/invariant`, not `integration`, because the 2-FF
synchronizer has its own failure mode (metastability) and the structural
rules that prevent it must be checked. That check is done by the
hardware-cdc structural audit (a flow stage), not by SVA — but the
obligation is real, and the bucket reflects that. A top-level smoke test
alone cannot detect problems like "combinational logic accidentally
inserted between the source flop and the first synchronizer stage".

Note: the hardware-cdc structural audit applies to every cross-domain
signal, not just the sync_2ff module. It is a separate flow stage that runs
in parallel with what the allocation table specifies.

## Why this pattern

- Round 1 puts CDC first because Gray pointer + 2-FF + per-domain flag
  computation is the textbook-grade safe construction. Any departure must
  be an explicit, justified choice — not a default.
- Round 2 puts reset strategy first because async-FIFO reset bugs are the
  most common silicon-level defect for this block type. Forbidding partial
  reset (option A) eliminates a whole class of debugging pain.
- Round 3's "DEPTH not a power of two → compile error" is the kind of rule
  the agent might forget without a prompt. Forcing the choice keeps the
  Gray pointer safe.

The CDC inventory section in spec.md is **not** equivalent to the cdc-rdc
audit step — the spec captures decisions, the audit verifies that the RTL
implements those decisions. Both must be done.
