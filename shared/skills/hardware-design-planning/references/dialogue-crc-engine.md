# Exemplar dialogue — pure-compute block (CRC engine)

> **Block scope** — single IP. Outputs `docs/{spec,uarch,plan}.md`. For the
> project scope flow (multiple subsystems, arch.md + subsystem tree), see
> `dialogue-soc-mldsa.md`.
>
> EXEMPLAR, not a template. It shows the questioning style for a block with
> no host bus, no streaming protocol, no CDC — just data in, data out, with
> configurable math. The key ambiguities are polynomial choice, byte order,
> and what happens between messages.

## User brief

> "CRC-32 engine, 1 byte / cycle, single clock."

## Agent analysis (not shown)

What's clear: CRC-32, 1 byte/cycle, single clock. Gaps: which CRC-32?
(Ethernet 0x04C11DB7, Castagnoli 0x1EDC6F41, or something else). Init
value (0xFFFFFFFF, 0, or parameterized)? Reflected input / reflected output
(the four standard combinations each correspond to a completely different CRC)?
Final XOR? How does the engine know a message boundary — explicit start/end
strobe, or "read the result after processing N bytes"? Does internal state
reset between messages? Result byte order? Throughput when bytes arrive at
less than one per cycle?

## Round 1 — CRC polynomial decisions (every byte matters)

```
1. Polynomial:
   A) 0x04C11DB7 — Ethernet / PNG / ZIP CRC-32 ★ (what people usually mean by "CRC-32")
   B) 0x1EDC6F41 — Castagnoli CRC-32C (iSCSI, SCTP, BTRFS)
   C) Parameterized — let the user pick at synthesis time
      → A is what people commonly refer to when they say "CRC-32"

2. Init value:
   A) 0xFFFFFFFF — matches Ethernet/PNG/ZIP ★
   B) 0x00000000
   C) Parameterized

3. Per-byte input bit reflection:
   A) Yes (LSB-first reflection) — matches Ethernet/PNG/ZIP ★
   B) No (MSB-first)

4. Output reflection:
   A) Yes — matches Ethernet/PNG/ZIP ★
   B) No

5. Output final XOR:
   A) 0xFFFFFFFF — matches Ethernet/PNG/ZIP ★
   B) 0x00000000
   C) Parameterized

Pick A/A/A/A/A, or specify a non-standard variant?
```

User: A/A/A/A/A (this gives a standard "CRC-32 / IEEE 802.3" engine, the
kind people stuff into Ethernet frames).

## Round 2 — message boundaries and reset

```
6. Message boundary signal:
   A) Explicit start_i pulse before the first byte; result valid 1 cycle after the last byte ★
      (most flexible, no implicit state)
   B) Process N bytes, where N is a CSR (introduces a CSR plane, and the CSR plane is out of scope here)
   C) Continuous CRC, sample any time (no boundary — the accumulator never resets unless aresetn)

7. State reset between messages:
   A) start_i pulse reloads init_value, then begins the byte stream ★
   B) Auto-reset on idle bytes (data_valid=0 for N cycles)
   C) Manual reset via a separate clear_i input

8. Output handshake:
   A) result_o valid + result_valid_o pulses for 1 cycle after the last byte ★
   B) result_o permanently visible (latest CRC, independent of message state)
   C) FIFO of completed results

Pick A/A/A?
```

User: A/A/A.

## Round 3 — throughput and edge cases

```
9. Throughput:
   A) 1 byte / aclk cycle when byte_valid_i=1 ★ (matches the brief)
   B) Higher: parallel CRC units processing N bytes/cycle (LUT-heavy)
   C) Lower: serial 1-bit/cycle (cheap area, 8x slower)

10. Cycles with byte_valid_i=0 (no data):
    A) Internal state stalls, output_valid_o stays low, ready for the next byte ★
    B) Implicitly process a 0x00 byte (changes the math result, almost certainly wrong)

11. Empty message (read result after start_i pulse with no bytes):
    A) result_o = init_value XOR final_xor = 0x00000000 (well-defined) ★
    B) result_valid_o never asserts (host hangs)
    C) Forbidden — assert in the TB

12. Result byte order:
    A) Native (32-bit word, byte 0 = LSB) ★ — matches the host's integer view
    B) Network byte order (byte 0 = MSB), convenient for direct concatenation into an Ethernet frame

Pick A/A/A/A?
```

User: A/A/A/A.

## What gets written into spec.md

Sections that emerged (noticeably smaller — because this is a small block):

- Function
- Interfaces (data_in port group, including valid, start_i, result_o,
  result_valid_o — 5 row groups)
- Clocks (1 row)
- Resets (1 row)
- **CRC math specification** (this section exists because of Round 1 —
  polynomial 0x04C11DB7, init 0xFFFFFFFF, refin=YES, refout=YES, xorout=0xFFFFFFFF —
  with an agreed-upon test vector, the standard reference value
  "CRC of ASCII '123456789' = 0xCBF43926")
- Performance targets (Fmax target, throughput = 1 byte/cycle)
- Parameters (few — possibly none at all if the IEEE 802.3 variant is fully fixed)
- Failure modes (empty-message behavior defined, byte_valid=0 stall behavior defined)
- Assumptions (host pulses start_i exactly once per message; read the result before the next start_i)

No CSR. No CDC. No fixed-point. No streaming backpressure. The CRC math section is the spec.

## Allocation in uarch.md's File list

| path | role | test | artifact |
|------|------|------|----------|
| rtl/crc_top.sv      | top integration   | reference-model + property/invariant | python golden: full-message CRC matches the vector "123456789" → 0xCBF43926; result_valid_o pulses for exactly 1 cycle after last_byte_i |
| rtl/crc_step.sv     | single-byte LFSR  | reference-model                      | python golden: per-byte polynomial step |
| rtl/crc_ctrl_fsm.sv | message boundary  | property/invariant                   | start → processing → result; no result without a preceding start; empty message produces a well-defined result |
| rtl/result_reg.sv   | output latch      | integration                          | covered by tb/crc_smoke_tb.sv (named "result_visible_one_cycle_after_end") |

`crc_top` carries two obligations: message CRC must match the public vector
(reference-model), and result strobe timing must match the convention from
Round 2 (property/invariant). The reference-model alone would miss the
"value correct but appearing on the wrong cycle" timing bug.

`crc_step` is a reference-model because per-byte stepping is a deterministic
single-cycle function. The verification skill decides how many vectors to
use and whether to do an exhaustive sweep — that's HOW, not WHAT.

`crc_ctrl_fsm` is the only part of the CRC that is purely about timing rules —
it's the translation of Round 2's message-boundary semantics into invariants.

## Why this pattern

- Round 1 is unusual: a batch of 5 questions, all about polynomial parameters.
  They're tightly coupled — there happen to be four "famous" CRC-32 variants
  (Ethernet, Castagnoli, BZIP2, MPEG-2), each corresponding to a specific
  A/B/A/B/A combination. Asking them together lets the user answer "Ethernet"
  in one shot; asking sequentially would be verbose and error-prone.
- The public reference test vector ("123456789" → 0xCBF43926 corresponds to
  Ethernet CRC-32) must appear in spec.md as a TB acceptance criterion.
  Without it, plausible-looking but wrong answers can also pass functional tests.
- Round 2's empty-message question captures the CRC engine's "textbook
  divide-by-zero analogue". Most homegrown CRC blocks hang on empty input.
- Reflection and final-XOR (Round 1 Q3/Q4/Q5) are the most common silent
  bugs: the math runs fine, but the result is just wrong by a predictable
  transformation. The user must choose explicitly.
