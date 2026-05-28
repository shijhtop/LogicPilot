# CDC / RDC reference: synchronizer patterns

Pick the synchronizer by *what* is crossing, not by habit. The wrong one is a
silent bug.

## Single control/status bit → two-flop synchronizer

Two back-to-back flops in the destination domain. The first may go metastable;
it is given one full destination cycle to settle before the second samples it.

```verilog
reg [1:0] sync;
always @(posedge dclk or negedge drst_n)
  if (!drst_n) sync <= 2'b0;
  else         sync <= {sync[0], async_in};
wire dst_in = sync[1];
```

Rules: source must be **wide enough to span at least one full
destination clock period plus setup/hold** — commonly stated as
≥1.5 destination periods as a design rule, ≥2 destination periods as
the safe floor when source / dest periods are similar. No combinational
logic on `async_in`. Add a third stage for very high-frequency
destinations or to lower MTBF further. Exact margin is PVT / library
dependent; defer to project CDC sign-off when budget is tight.

## A short event/pulse → pulse (toggle) synchronizer

A 1-cycle pulse in a fast domain can be missed by a slower domain. Convert the
pulse to a **toggle** in the source, 2-FF synchronize the toggle, then edge-
detect in the destination to regenerate the pulse. Source pulses must be spaced
far enough apart for the destination to see each toggle.

## Multi-bit data → async FIFO or handshake (NEVER parallel 2-FF)

- **Async FIFO**: dual-port RAM with **Gray-coded** read/write pointers; only the
  pointers cross domains. Gray code has **code distance 1** — exactly one bit
  changes per increment — so a 2-FF sync of the pointer can only ever be "one
  count behind," never a garbage intermediate value. Use for streaming /
  rate-decoupling. Two subtleties that bite real designs:
  - **Register the Gray pointer before resynchronizing.** The Gray pointer
    must be the **registered output** of the binary→Gray combinational logic,
    not the raw combinational output. Sampling the unregistered combinational
    value lets combinational settling appear at the synchronizer input and
    re-introduces the multi-bit-transition problem Gray was meant to eliminate.
  - **Reset sequencing.** The two ports sit in different clock (and possibly
    reset) domains; if one side leaves reset before the other, stale data can be
    read. Reset both pointer logic consistently (e.g. async-assert/sync-deassert
    per domain) so the FIFO comes up empty on both sides.
- **Req/ack handshake**: source drives data + `req`, holds both stable; `req` is
  synchronized to the destination; destination latches data and returns `ack`;
  `ack` is synchronized back. Slower (round-trip latency) but cheap for
  occasional transfers. The bus is only sampled while it is guaranteed stable.

## Slow-changing bus → Gray-coded counter

If the multi-bit value is a counter (e.g. a FIFO level), Gray-encode it so only
one bit changes per step; then a per-bit 2-FF sync is safe.

## MUX recirculation with synchronized enable

Hold a captured value with a feedback MUX in the destination; only the 1-bit
load-enable crosses (synchronized). Good for a register written rarely from
another domain.

## Multi-bit consolidation / MCP formulation

When two control bits must arrive in the **same destination cycle** (e.g.
`load` + `enable`), small source skew can split them across two destination
cycles and miss the transaction.

- **Fix A — consolidate**: collapse to one synchronized control bit in the
  source; let the destination regenerate the second signal locally.
- **Fix B — MCP (multi-cycle path)**: drive the multi-bit data
  **unsynchronized but held stable** in the source, and synchronize a single
  load-enable through 2–3 FFs. The destination only latches data after the
  enable pulse propagates, so the multi-bit value is guaranteed stable by
  then. Constrain the data path with `set_max_delay` (≤ source period) so
  STA bounds the skew the destination tolerates.

## Reset-domain crossing (RDC)

- Prefer **asynchronous assert, synchronous deassert** ("reset synchronizer"):
  the reset asserts immediately but releases on a clock edge, so all flops in a
  domain leave reset on the same cycle.
- A signal that crosses from a register in reset domain A to one in domain B is
  an RDC: if A can reset while B is active, the B register sees a mid-flight
  change. Treat like a CDC — gate or synchronize, or prove the resets are
  always coincident.

## When to escalate to formal

Structural review proves the *presence* of a synchronizer; it does not prove
data is *stable long enough* or that protocol assumptions hold. For high-risk
crossings, formal CDC with **metastability injection** (randomly delaying the
synchronized signal by a cycle in the formal model) checks the destination is
robust to real metastable behavior — stronger than structural checks or sim.
