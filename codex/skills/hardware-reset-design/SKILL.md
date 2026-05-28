---
name: hardware-reset-design
description: >-
  Design and review reset architectures for FPGA/ASIC RTL: sync vs async reset, async-assert/sync-deassert synchronizers, reset-domain crossing (RDC), reset trees, sequencing, and reset timing. Use when the user mentions reset, rst_n, POR, reset synchronizer, or recovery/removal, especially in multi-clock/multi-reset designs.
---

# Reset Architecture & RDC Review

A reset is not a comment in RTL; it is a real control network with timing,
glitch, fanout, and clock-domain implications. The goal is to make reset
assertion deterministic and reset release safe in every clock domain.

This skill distills the reset guidance in the reset-design references and
the FPGA advanced-design focus on asynchronous-reset synchronous-release,
reset cascade, and reset timing analysis.

## Why reset every state element matters

Under-reset state hides in RTL simulation (zero-delay X is often optimistically
resolved by `if (cond)` evaluating to 0), then explodes in gate-level sim
(GLS) or silicon (FFs come up to whatever the library / process gives). The
cheapest fix is to reset every architecturally-visible register at design
time, not to debug X-propagation later.

## Pick the reset style deliberately

Use the project convention when it exists. If no convention is given:

- **FPGA default**: reset only architecturally visible / control state; rely on
  vendor-supported initialization only for registers or memories where the
  target family and synthesis flow document it. For external or POR resets,
  prefer **asynchronous assert, synchronous deassert** per clock domain. The
  synchronizer's first-FF D-input is **tied to `1'b1`**, the raw async reset
  drives both FFs' async clear pin, and the FF chain is clocked by the
  destination clock — you synchronize the *release* of `1` into the domain,
  not the reset signal itself.
- **ASIC default**: every flip-flop should be resetable unless it is a
  deliberate shift-register / pipeline FF with a documented known-state
  wind-up time. Do not rely on `don't care` reduction giving you a usable
  power-up state. Prefer synchronous resets unless there is a system-level
  reason for asynchronous assertion.
- **Internally generated reset**: prefer a **synchronous reset** or register
  the reset source first, unless the system requires immediate hardware-safe
  assertion (e.g. fault-driven shutdown). Combinationally generated async
  resets can glitch and reset only part of a domain.

## Async assert / sync deassert pattern

Use an independent reset synchronizer in every destination clock domain:

```systemverilog
module reset_sync (
  input  logic clk,
  input  logic arst_n,      // asynchronous assertion, active low
  output logic srst_n       // synchronous deassertion in clk domain
);
  logic rff1;

  always_ff @(posedge clk or negedge arst_n) begin
    if (!arst_n) {srst_n, rff1} <= 2'b00;
    else         {srst_n, rff1} <= {rff1, 1'b1};
  end
endmodule
```

`rff1`'s D-input is implicitly `1'b1`; the second FF (`srst_n`) sees `rff1`
transition `0 → 1` cleanly after release because both ends are guaranteed
stable for at least one destination-clock period.

Rules:

1. Assert reset asynchronously when the system requires immediate assertion.
2. Deassert reset only through the synchronizer for the destination clock
   domain.
3. Each destination clock domain must own its own 2-FF synchronizer instance;
   share the **raw** `arst_n` input only — never reuse the synchronized output
   across unrelated clocks.
4. Constrain the async assertion path with a false path on the synchronizer's
   `CLR` pins, but keep recovery/removal checks enabled from the synchronizer
   Q to every destination FF so STA still times the release.

## Reset-domain crossing (RDC)

A reset crossing exists when logic in one reset domain observes state in another
reset domain, even if both share the same clock. Treat RDC like CDC:

- If two blocks release reset at different times, any handshake between them
  must tolerate one side being held in reset.
- Reset deassertion can create a pulse-like event. Synchronize it or gate it
  through a safe ready/valid initialization sequence.
- Avoid reset cascades that combinationally feed reset from one domain into
  another. Register sequencing signals in the destination domain.
- For multi-clock reset release, list each reset source and each synchronized
  per-domain reset in the design plan.

## What to reset

Reset what software, external pins, or downstream logic can observe. Typical
reset targets across both targets:

- FSM state, counters with protocol meaning, valid bits, credit counts, status
  flags, interface outputs, and pointers.
- **Output enables of tri-state / I/O drivers**: power-on `oe` must come from
  an async-resetable FF so the pad cannot fight an external driver before
  the local clock is alive.
- Do not reset pure pipeline data when the associated `valid` bit is reset and
  masks it (FPGA target).
- Memories: initialize only if the target flow supports it, or provide an
  explicit scrub/fill sequence.

### Coding rule: don't mix reset and non-reset FFs in one always block

A single `always_ff` block must have either all-resetable or all-non-resetable
flops. Mixing them degrades the reset signal into a load-enable on the
non-reset side. Split into two blocks per reset style.

## Edge cases

- **Glitch filtering**: if raw `rst_n` can glitch (board noise, hot-plug),
  insert a small delay + de-glitch AND/OR network ahead of the synchronizer
  and pair with a Schmitt-trigger input pad. Mark the delay cells
  `dont_touch` so synthesis cannot collapse them.
- **Sequenced reset removal**: when release ordering matters across domains
  A → B → C, chain the synchronizers — domain N's first-FF D-input is driven
  by domain (N-1)'s synchronized `rst_n` instead of `1'b1`. Independent
  handshake interfaces use the parallel (unordered) form.
- **Dual async set + reset FFs**: avoid. If unavoidable, the cell is inferred
  correctly by synthesis but RTL sim races; isolate with a `translate_off`
  self-correcting block.
- **Scan / DFT handling**: the two synchronizer FFs (`rff1`, `srst_n`)
  need explicit DFT treatment — either excluded from the scan chain or
  constrained so the raw async reset is masked during capture. Vendor /
  flow dependent; coordinate with the DFT engineer rather than blindly
  setting `set_dont_scan`.
- **FPGA GSR**: GSR alone does not guarantee synchronous release per domain;
  you still need a per-domain reset synchronizer downstream of GSR.
- **Testbench reset rule**: drive reset transitions on the **inactive** clock
  edge with nonblocking assignments (or at time-0 NBA). Never release reset
  coincident with the active edge — this races both Verilog and real-hardware
  recovery.

## Review checklist

- [ ] Every clock domain has its own reset synchronizer or explicitly
      synchronous reset.
- [ ] Async resets are asserted asynchronously and deasserted synchronously.
- [ ] No combinational logic drives an async reset pin.
- [ ] Reset release order is documented when blocks depend on each other.
- [ ] Reset fanout is reasonable; high-fanout resets are buffered/replicated by
      tool or architecture.
- [ ] CDC/RDC crossings during reset release are handled by handshake, FIFO, or
      per-domain sequencing.
- [ ] Constraints identify false/asynchronous reset assertion paths and preserve
      timing checks required for release.
- [ ] Testbench checks reset during idle and, when allowed, reset during active
      traffic.

## Definition of done

The reset style is stated, every reset source and destination domain is listed,
async release is synchronized per clock domain, RDC hazards are either fixed or
waived with rationale, and simulation/constraints cover the reset behavior.
