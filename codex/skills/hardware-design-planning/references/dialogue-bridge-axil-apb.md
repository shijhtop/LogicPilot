# Exemplar dialogue —— Protocol bridge (AXI4-Lite → APB)

> **Block scope** —— a single IP. Outputs `docs/{spec,uarch,plan}.md`. If
> this is a project scope flow (multiple subsystems, arch.md + subsystem
> tree), see `dialogue-soc-mldsa.md`.
>
> EXEMPLAR (an example), not a template. It shows the questioning style
> for a protocol-translation block, where the genuinely ambiguous parts
> are the transaction mapping rules — not computation or CSR design.

## User brief

> "AXIL slave to APB master bridge, single clock."

## Agent analysis (not shown to the user)

Already clear: the host side is an AXIL slave, the peripheral side is an
APB master, single clock. To clarify: APB version (APB2/APB3/APB4)? How
is PSLVERR handled? PREADY wait strategy? AXIL response code when APB
errors out? Maximum number of outstanding transactions? How are byte
strobes forwarded? Address width? Concurrent or serial read/write? How
does reset propagate?

## Round 1 —— Protocol version and core semantics

```
1. APB variant:
   A) APB4 —— has PSTRB and PSLVERR  ★ (modern default)
   B) APB3 —— has PREADY but no PSTRB
   C) APB2 —— fixed latency, no PREADY/PSLVERR

2. AXIL data width:
   A) 32-bit  ★ (natively matches APB)
   B) 64-bit (requires APB widening logic —— out of scope?)

3. Concurrency:
   A) Serialized: only one outstanding transaction allowed at a time
      (AR or AW, not both simultaneously)  ★
      Simplest, no reorder hazard
   B) AR + AW concurrent, each with an independent APB sub-controller
   C) Pipelined AXIL with a reorder buffer (overkill for APB)

4. Reset:
   A) Single reset (aresetn), propagated to PRESETn  ★
   B) Independent reset domains for AXIL and APB

Pick A/A/A/A?
```

User: A/A/A/A.

## Round 2 —— Error and timing strategy

```
5. APB PSLVERR → AXIL response:
   A) PSLVERR=1 → BRESP/RRESP=SLVERR  ★ (transparent mapping)
   B) PSLVERR=1 → BRESP/RRESP=OKAY, logged internally (host cannot tell)
   C) PSLVERR=1 → stall and assert irq

6. APB PREADY stall budget:
   A) Unbounded wait (trust the APB slave)  ★
   B) Time out after N aclk cycles, return SLVERR
      → If A, the AXIL host may be blocked indefinitely; SW should not
        access bad addresses
      → If B, N must be pinned down (default 256?)

7. Byte-strobe WSTRB handling:
   A) Forward to APB PSTRB (APB4 only)  ★
   B) Reject any partial-word write, BRESP=SLVERR
   C) Convert partials to full-word via read-modify-write

8. Address window:
   A) Pass the entire AXIL address space through to APB  ★
   B) Decode N regions to N PSEL lines (multi-slave APB)
   C) Address translation at a fixed offset

Pick A/A/A/A?
```

User: A/A/A/A.

## Round 3 —— Outstanding transactions and ordering

```
9. AXIL write-data + write-address ordering:
   A) AW and W may arrive in any order; the bridge waits until both are
      present before launching APB  ★
     (matches the AXIL spec)
   B) Require AW to precede W (simpler but technically non-compliant)

10. When a new AXIL request arrives while the previous APB transaction
    is still in flight:
    A) Stall the AXIL valid/ready until APB completes  ★ (Round 1 already
       picked serialization)
    B) Buffer one extra request (1-stage skid)

11. APB clock relative to AXIL clock:
    A) Same clock, same edge (single clock domain —— Round 1 already
       fixed single clock)  ★
    B) Same clock, opposite edge (legacy, not recommended)

Pick A/A/A?
```

User: A/A/A.

## What ultimately lands in spec.md

The sections that may emerge in the end (driven by the questions, not
forced by a template):

- Function
- Interfaces (s_axil_*, m_apb_*, clk, rstn —— 4 groups)
- Clocks (1 line —— per Q11, both sides share the same clock)
- Resets (1 line, with a note that aresetn propagates to PRESETn)
- **Transaction mapping table** (this section appears because the design
  needs it —— rows: AXIL_AR→APB_read, AXIL_AW+W→APB_write, error mapping
  per PSLVERR)
- **Response code mapping** (because Q5 picked transparent mapping)
- Performance targets (Fmax, AXIL→APB latency = APB_wait + 2 cycles)
- Parameters (should be very few —— ADDR_WIDTH, optional WAIT_TIMEOUT)
- Failure modes (PSLVERR mapping, partial-word policy, ordering hazards)
- Assumptions (the APB slave will eventually assert PREADY; same clock
  domain)

No CSR (this is a bridge). No fixed-point precision (no computation).
There is one transaction mapping table that neither the SPI nor the FIR
exemplar has.

## Allocation in the File list of uarch.md

| path | role | test | artifact |
|------|------|------|----------|
| rtl/bridge_top.sv         | top integration   | integration                          | covered by tb/bridge_smoke_tb.sv:AR/AW/W round-trip |
| rtl/axil_slave.sv         | AXIL handshake    | property/invariant                   | handshake legality; AR not allowed while AW is outstanding (Q9) |
| rtl/apb_master.sv         | APB master FSM    | property/invariant                   | PSEL must precede PENABLE, single setup, no overlap allowed |
| rtl/xact_translator.sv    | AXIL→APB mapping  | reference-model + property/invariant | python: AXIL transaction → APB sequence; beat rules |
| rtl/pslverr_mapper.sv     | error code mux    | reference-model                      | python: PSLVERR → BRESP/RRESP mapping table |

`xact_translator` is the heart of the bridge and carries two kinds of
obligation: the AXIL-in → APB-out sequence is deterministic (a python
translator can mechanically map any input transaction), and the beat
rules (when PSEL goes high, when bvalid is allowed to fire) are timing
invariants. Reference-model-only handling would miss back-to-back
ordering bugs, while property-only handling would miss content errors.

`pslverr_mapper` is pure combinational, but the mapping table **is** the
spec —— it is worth covering on its own with a bit-exact check rather
than relying solely on "it looks right in integration."

## Why this pattern

- Round 1 first pins down **which** APB version, because the presence of
  PSTRB and PSLVERR determines half of the questions that follow.
- The PSLVERR mapping in Round 2 is the trap specific to bridge designs:
  silently swallowing errors is the #1 bug at delivery time for bridge
  designs, and it must be a conscious decision.
- The ordering questions in Round 3 catch the "unit tests pass but it
  hangs once you connect a concurrent host" class of bug. If a bridge
  gets this wrong, sim will pass, but it will fail at SoC integration.
