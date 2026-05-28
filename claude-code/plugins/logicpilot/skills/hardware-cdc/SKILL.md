---
name: hardware-cdc
description: >-
  Structural review of clock-domain and reset-domain crossings (CDC/RDC) in RTL. Use for any multi-clock or async-reset design, or when the user mentions metastability, synchronizers, async FIFO, Gray code, or handshakes; these bugs pass sim and STA and must be caught structurally.
---

# Clock- and Reset-Domain Crossing Review

CDC/RDC bugs do **not** show up in plain RTL simulation (zero-delay hides
metastability) or STA (single-domain only). They have to be caught by
*structural* review of the RTL. If a CDC tool (SpyGlass, JasperGold CDC, Questa
CDC, ALINT) or formal flow is available, use it in addition — not instead.

## When this skill is mandatory (MUST gate)

This skill MUST be invoked, and its Definition of done MUST be met, on any
design that has:

- ≥2 unrelated/asynchronous clocks, OR
- ≥2 asynchronous reset sources, OR
- any signal written in one clock/reset domain and read in another.

Single-clock single-reset designs are exempt — say so and skip.

**There is no "obviously safe" multi-bit crossing.** Either do the structural
review below or waive the crossing in writing with a reason. Multi-clock
designs that pass sim and STA but never get a CDC review are the #1 source
of post-silicon respin in this stack — these bugs do not show up in
zero-delay simulation and STA only covers single-domain paths.

## Clock-partitioned design rule

**Leaf modules should see one functional clock.** The top level is the
only place that hosts multiple clocks; every cross-domain net passes
through a dedicated synchronizer sub-module. Synchronizer primitives
(2FF / handshake / async-FIFO read-and-write ports) are the documented
exception — they see both clocks by construction and are accounted for
as one crossing each.

This makes STA tractable (each leaf is single-clock, false-paths apply
only on synchronizer inputs) and the CDC inventory mechanical (every
synchronizer instance = one crossing). If a normal module needs two
clocks for any reason other than being a synchronizer, split it.

## Workflow

1. **Enumerate domains.** List every clock and async reset; group registers by
   the `(clk, rst)` pair from their `always @(posedge clk or negedge rst_n)`.
2. **Find crossings.** Every signal written in one domain and read in another.
3. **Classify each crossing** (single bit / pulse / bus / handshake / reset
   release) and confirm it uses the matching synchronizer. See
   `references/cdc-rdc-reference.md` and `references/async-fifo-patterns.md`.
4. **Check the hazards below** on every crossing.
5. **Report** each crossing as safe / unsafe / needs-waiver, with the fix. An
   unsafe crossing is a design defect, not a style nit.

## Hazards to check on every crossing

- No synchronizer at all on a cross-domain net feeding combinational logic.
- Multi-bit bus through **parallel** 2-FF chains — bits settle on different
  cycles. Use async FIFO, Gray-coded counter, or req/ack with held data.
- Reconvergence / fan-out before the synchronizer — synchronize once, then fan
  out.
- Combinational logic (including gating) between the crossing and the first
  flop — glitches get captured. Sync first, gate after.
- **RDC:** register reset by A feeding register reset by B. Assert async,
  **deassert synchronously** per domain.
- **Fast → slow:** the source pulse must span at least one full
  destination clock period plus setup/hold (commonly ≥1.5 destination
  periods as a design rule; ≥2 is the safe floor). A 1-source-cycle
  pulse can land entirely between two destination edges and be missed;
  a pulse just slightly wider than one destination period can still
  violate setup on one edge and hold on the next. Open-loop fix: hold
  the source long enough. Closed-loop fix: req/ack handshake
  (automatically meets the timing requirement).
- **Derived/gated clocks:** prefer a clock enable over a gated/divided/ripple
  clock. If unavoidable, treat each parent↔derived path as a crossing and
  constrain it (`create_generated_clock`, `set_clock_groups` /
  `set_false_path` — see `hardware-constraints`).
- **Declare async relationships to STA** (`set_clock_groups -asynchronous`) so
  false violations don't appear and the tool doesn't try to "close" an async
  path.

## STA exception choice — MCP vs `set_max_delay` vs `set_clock_groups`

CDC crossings need an STA exception, but **which one** depends on the
crossing class. Picking the wrong one either over-constrains (false
timing failures) or under-constrains (real bugs slip).

| Crossing class | Correct exception | Wrong choice / why |
|---|---|---|
| Async clock domains, no relationship | `set_clock_groups -asynchronous {clkA} {clkB}` | `set_false_path` between every endpoint pair — works but verbose, easy to miss paths |
| Reset-synchronizer first FF (async assert) | `set_false_path -to [get_pins <sync>/rff1/CLR]` | Generic `clock_groups` — wrong, would also false-path the recovery/removal check on release |
| CDC bus data path (driver → sync register input) | `set_max_delay <one-source-period> -from <src_reg> -to <sync_first_ff>` | `set_multicycle_path N` — wrong, MCP means "settle in N source cycles", but CDC data isn't synchronous to the source clock at the destination |
| Handshake (req / ack pair) | `set_clock_groups -asynchronous` on the domain pair (req + ack both covered) | Per-signal `false_path` — fragile, breaks when synchronizer module is renamed |
| Clock-enable path (sampled every N cycles) | `set_multicycle_path -setup N -hold N-1` | `set_false_path` — wrong, this is a real synchronous path that just runs slowly |

**MCP (`set_multicycle_path`) is for synchronous paths that legitimately
take more than one source cycle to settle** (clock-enable, slow data on
a fast clock). It is **not** a CDC primitive — the data must still be
synchronous to the launching clock at the capture flop. CDC bus data is
async by construction; use `set_max_delay` to bound metastability
window, not MCP.

The `-hold N-1` adjustment is mandatory for MCP — a setup-only
multicycle exception that omits the hold side is a common sign-off bug.

For tool-level CDC waivers (SpyGlass / Questa CDC / JasperGold CDC
violation suppression files), see `references/cdc-tool-waiver.md`.

## Multi-bit data: async FIFO rules

- Binary read/write pointers local to each domain.
- **Gray-coded** pointers synchronized across domains (binary toggles many bits
  at once → illegal intermediate value).
- Full/empty from local pointer + synced opposite pointer.
- Memory written only in write domain, read only in read domain.
- FIFO flags used only in their own domain.

## Definition of done (MUST gate)

You MUST satisfy all of the following before declaring a multi-clock or
multi-reset design done:

- [ ] **Crossing inventory exists** — every cross-domain signal is listed
      (source domain, destination domain, kind: single-bit / pulse / bus /
      handshake / reset release).
- [ ] **Each crossing has a verdict** — synchronized with the matching
      pattern, OR explicitly waived with a written reason. "Probably fine"
      is not a verdict.
- [ ] **No multi-bit bus uses parallel 2-FF chains** — multi-bit uses async
      FIFO with Gray-coded pointers, Gray-coded counter, or req/ack with
      held data.
- [ ] **Reset deassertion is synchronized per domain** (assert async,
      deassert sync).
- [ ] **Async clock relationships are declared to STA** with
      `set_clock_groups -asynchronous` (see `hardware-constraints`).

Output the crossing inventory and the status of each as part of the review.
A design that has not been through this checklist MUST NOT be declared
done — including by exit-code-0 from sim or synth.
