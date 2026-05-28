# Hardware Inference Patterns

Canonical code shapes and the hardware each infers. Examples in Verilog/SV;
VHDL equivalents in `vhdl.md`.

## Flip-flop (the basic state element)

```verilog
always_ff @(posedge clk)        // posedge clk, no reset in list -> sync-only
    q <= d;
```

### Synchronous reset
```verilog
always_ff @(posedge clk)
    if (!rst_n) q <= '0;        // reset is just another synchronous input
    else        q <= d;
```

### Asynchronous reset (reset on sensitivity list)
```verilog
always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) q <= '0;
    else        q <= d;
```
Async reset must be released synchronously (a **reset synchronizer**: async
assert, sync deassert) to avoid recovery/removal timing failures — this is the
recommended way to use async reset (reset-design reference, "Synchronous Resets?
Asynchronous Resets? I'm so confused!"). Two further rules from that paper:
- If the reset is **generated from internal logic** (not a clean external pin),
  prefer a **synchronous** reset — it filters combinational glitches between
  clock edges that an async reset would pass straight through.
- **Avoid a flip-flop that needs both async set and async reset**; the
  simultaneous-deassert case is a known sim/synth-mismatch trap.

Pick one reset style per design and be consistent. ASIC practice: make every
flop resettable. FPGA fabrics often prefer synchronous reset, or no reset on
deep shift/pipeline chains, letting FFs power up to a defined init value.

## Latch (usually a BUG — know how it appears)

```verilog
always_comb
    if (en) y = a;              // no else -> y must HOLD when !en -> LATCH
```
Fix: assign on all paths.
```verilog
always_comb begin
    y = '0;                     // default first
    if (en) y = a;              // now fully specified -> mux/AND, no latch
end
```

## Mux / priority mux

```verilog
always_comb
    unique case (sel)           // 'unique' asserts mutually-exclusive, full
        2'b00: y = a;
        2'b01: y = b;
        2'b10: y = c;
        default: y = d;         // always include default
    endcase
```
An `if/else if` chain infers a **priority** mux (slower for many terms); a
`case` infers a balanced mux. Prefer `case` for wide selects.

## Two-always-block FSM (recommended)

```verilog
typedef enum logic [1:0] {IDLE, RUN, DONE} state_t;
state_t state, next;

always_ff @(posedge clk)        // 1) state register
    if (!rst_n) state <= IDLE;
    else        state <= next;

always_comb begin               // 2) next-state + outputs (Moore here)
    next = state;               // default: hold
    case (state)
        IDLE: if (go)   next = RUN;
        RUN:  if (done) next = DONE;
        DONE:           next = IDLE;
    endcase
end
```
Guidelines (RTL methodology source, "State Machine Coding Styles for Synthesis" / "The
Fundamentals of Efficient Synthesizable FSM Design"): keep each FSM in its own
module; register outputs if you need glitch-free / better timing (adds one cycle
latency). Prefer this **two-always-block** split; **avoid the one-always-block
style** (everything including outputs in the clocked block) — it's verbose and
error-prone. Encoding: FPGAs often favor **one-hot** (FFs are plentiful, smaller
next-state logic, usually faster); binary/Gray can be smaller on ASIC or for
wide state counts. Let the tool choose unless you have a measured reason — and
if you hand-code a one-hot decode, that is the *one* place `parallel_case` is
legitimate (see verilog-sv.md case hygiene).

## Memory — RAM/ROM, BRAM vs distributed

```verilog
logic [7:0] mem [0:255];                 // 256x8

// Synchronous-read single-port RAM -> infers BRAM on most FPGAs
always_ff @(posedge clk) begin
    if (we) mem[addr] <= wdata;
    rdata <= mem[addr];                  // registered read = BRAM-friendly
end
```
- Registered (synchronous) read → block RAM. Asynchronous (combinational) read
  → distributed/LUT RAM. Choose based on which resource is scarce.
- ROM: initialize with `initial` + `$readmemh`, or a `case`. FPGA ROM init is
  supported; ASIC is not.
- Multiple write ports or wide async-read banks can blow up into LUTs — check
  the synth utilization.

## Shift register / pipeline

```verilog
always_ff @(posedge clk)
    {q3, q2, q1} <= {q2, q1, d};         // 3-stage pipeline
```
Long shift registers can map to SRL primitives (Xilinx) — efficient. Pipelining
the critical path is the highest-leverage timing fix.

## Counter

```verilog
always_ff @(posedge clk)
    if (!rst_n)    cnt <= '0;
    else if (en)   cnt <= cnt + 1'b1;    // size the literal
```

## Arithmetic → DSP

`a * b`, multiply-accumulate, and wide adders map to DSP blocks (DSP48 / SB_MAC
/ etc.) when shaped right (registered inputs/outputs help inference). A divider
or variable shifter built naively becomes a large LUT cloud — pipeline it or use
a vendor IP / iterative algorithm. Watch synth `dsp`/`luts` to confirm the map.
```

## Clock-domain crossing (structure, not a single primitive)

- 1-bit control: 2-flop synchronizer.
- Multi-bit value: gray code (counters), async FIFO, or req/ack handshake with a
  data hold. Never let a raw multi-bit bus cross unsynchronized.
- Constrain CDC paths as false/max-delay so timing tools don't chase them.
