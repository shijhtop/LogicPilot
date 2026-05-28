# Exemplar dialogue —— project scope (MLDSA-44 signing IP)

> EXEMPLAR (sample), not a template. Demonstrates the questioning style when
> the brief describes a multi-subsystem design —— here, a FIPS-204
> (Dilithium / MLDSA-44) signing accelerator. The Tier-0 ambiguity is in
> partitioning, the top-level bus, the memory map, and milestone strategy ——
> not internal data types. Internal data types belong to each subsystem's
> Tier-1 round (which recurses into the block-scope flow —— for per-block
> questioning style see `dialogue-streaming-fir.md`).

## User brief

> "I want an MLDSA-44 IP. AXI4-Lite to the host. Key in, message in,
> signature out. Must match the NIST FIPS-204 KAT."

## Agent analysis (not shown)

What's clear: MLDSA-44, AXIL host, KAT-match required. Gaps: this is *not* a
single block —— MLDSA-44 contains Keccak/SHAKE, NTT/INTT modulo q=8380417,
Montgomery, the ExpandA rejection sampler, SampleInBall, w1Encode, and three
top-level operations (KeyGen / Sign / Verify) that share most of these
building blocks. Memory map for key / message / signature? Do the polynomial
vectors (1024 bytes each × multiple vectors) live on-chip or in external
memory? Clock strategy —— single domain, or Keccak and NTT split? Phased
delivery (KeyGen first only, or all three at once)? Side-channel posture
(out of scope, or constant-time)? This is project scope.

## Round 0 —— scope confirmation

```
0. Project scope:
   A) Block —— implement MLDSA as one big block, single spec.md
   B) Subsystem —— group into 2–3 coupled blocks (e.g. "crypto core + CSR")
   C) Full project —— one subsystem each for Keccak, NTT, sampler, top-level
      FSM, CSR, key storage ★ —— matches the natural partition of the
      FIPS-204 algorithm, and lets each subsystem be verified independently
      against its own KAT intermediate values

Which one?
```

User: C (project scope).

## Round 1 —— subsystem partition

```
1. Hash subsystem:
   A) Single Keccak permutation core, SHAKE-128/256 as wrapper modes ★
      ExpandA, ExpandS, ExpandMask, H(message) each use one, sharing the
      same core
   B) Separate SHAKE-128 and SHAKE-256 cores (trade silicon for parallelism)
   C) Software provides SHAKE —— IP only does the math (reject: KAT requires
      a fully deterministic pipeline)

2. NTT subsystem:
   A) One NTT core, time-multiplexed across vectors ★ —— 5 NTTs per Sign,
      1024-point each, acceptable at 100 MHz
   B) Two NTT cores for A·s + s2 parallel (4× area for ~1.5× speed)
   C) Merged NTT + Montgomery + polynomial-multiply "ALU" —— harder to
      verify

3. Sampler subsystem:
   A) Merged ExpandA + ExpandS + ExpandMask + SampleInBall, sharing the
      Keccak output interface ★ —— all are consumers of rejection sampling
   B) One sampler per call site (more area, no benefit)

4. Top-level control:
   A) One FSM with three op modes (KeyGen/Sign/Verify) —— shared datapath ★
   B) Three independent FSMs (control duplication, more silicon)

5. Storage:
   A) Single key/seed RAM, separate signature/message RAM ★ —— lifetime and
      access patterns differ
   B) Unified scratchpad RAM, software-managed partitioning
   C) All in external memory (AXI master) —— out of scope for v1

Pick A/A/A/A/A?
```

User: A/A/A/A/A.

Subsystems pinned down: `keccak_core`, `ntt_core`, `sampler`, `top_ctrl`,
`key_storage`, `csr_block`. Six subsystems total. Each gets its own
`docs/subsystems/<name>/` triplet.

## Round 2 —— top-level bus, clock, reset

```
6. Host bus:
   A) AXI4-Lite slave, 32-bit, single channel ★ —— matches the brief
   B) APB3 slave (simpler, but streaming a 2.4 KB signature out is slower)

7. Clock scheme:
   A) All subsystems share a single 100 MHz clock domain ★ —— Keccak and
      NTT both close timing with margin; single domain simplifies CDC
   B) Keccak on a separate clock (faster, more rounds/sec) —— every Keccak
      → consumer signal needs a 2-FF CDC; not needed for v1
   C) Multiple clocks, async FIFO between subsystems (over-engineered)

8. Reset scheme:
   A) Single aresetn, async assert / sync deassert via standard
      sync-deassert cell ★ —— single domain → single reset suffices
   B) Per-subsystem reset (each subsystem soft-resettable via CSR)
      → defer to a later phase

Pick A/A/A?
```

User: A/A/A.

## Round 3 —— memory map and interrupt routing

```
9. Memory map (top-level address space seen by host):
   A) 64 KB region:
        0x0000 — CSR (control / status / IRQ)
        0x1000 — key storage (write seed, read public key)
        0x2000 — message buffer (host writes plaintext)
        0x4000 — signature buffer (IP writes, host reads)
      ★ —— clean partition; CSR stays strictly < 4 KB; key region is
          isolated so access control can be added later
   B) Flat scratchpad with offsets embedded in CSR fields (less flexibility,
      harder to ship a header file to software)

10. IRQ semantics:
    A) Single level-high IRQ, sticky DONE bit, mask + clear in CSR ★
       host clears DONE, IP drops IRQ
    B) Edge-triggered DONE pulse (host is responsible for not missing it ——
       fragile)
    C) Two IRQs (DONE + ERR) —— extra wires, no real benefit

11. Error handling:
    A) Single ERR sticky bit in CSR.STATUS, set on any abort condition
       (KAT-detected internal mismatch, sampler timeout, illegal CSR
       sequence), cleared by W1C ★
    B) Per-error code (harder to use, no feedback yet for v1)

Pick A/A/A?
```

User: A/A/A.

## Round 4 —— platform, milestone strategy

```
12. Platform target:
    A) Xilinx Artix-7 xc7a200t (FPGA prototype) ★ —— enough BRAM for the
       polynomial vectors, DSPs for Montgomery
    B) ASIC, TSMC 28 nm (out of scope for v1 —— no PDK in repo)

13. Side-channel posture:
    A) Functional correctness first; constant-time only where free (avoid
       early exits in hash compares) ★ —— v1 explicit non-goal
    B) Full constant-time + masking —— 3× the work, defer

14. Milestone strategy:
    A) P0 = interface stub-out; P1 = KeyGen end-to-end matching KAT;
       P2 = Sign end-to-end; P3 = Verify end-to-end ★ —— KeyGen is the
       smallest end-to-end loop and exercises Keccak + sampler + key store
       at the same time
    B) Build all three ops in parallel (higher risk, less feedback)

Pick A/A/A?
```

User: A/A/A.

## Output: `docs/arch.md` (skeleton —— sections that emerged)

- **Project goal** —— 1 paragraph: FIPS-204 MLDSA-44 signing IP, AXIL host,
  KAT-conformant, FPGA-first.
- **`## Subsystems`** (mandatory table):

| name         | role                         | clock   | power     | bus iface       |
|--------------|------------------------------|---------|-----------|-----------------|
| keccak_core  | Keccak-f[1600] + SHAKE wrap  | aclk    | always-on | internal valid/ready |
| ntt_core     | NTT/INTT mod q=8380417       | aclk    | always-on | internal valid/ready |
| sampler      | ExpandA/S/Mask + SampleInBall| aclk    | always-on | consumes keccak |
| top_ctrl     | KeyGen/Sign/Verify FSM       | aclk    | always-on | schedules all   |
| key_storage  | seed / public-key / secret-key RAM | aclk | always-on | AXIL-readable |
| csr_block    | host CSR + IRQ aggregator    | aclk    | always-on | AXIL slave      |

- **Top-level bus** —— AXI4-Lite slave, 32-bit, single channel
- **Clock scheme** —— single 100 MHz `aclk`
- **Reset scheme** —— single `aresetn`, async/low, sync-deassert
- **Memory map** —— Round 3 Q9 table
- **Interrupt routing** —— single IRQ, sticky DONE + ERR from `csr_block`
- **Power/security domains** —— none in v1 (target is functional correctness)
- **Platform target** —— Artix-7 xc7a200t
- **Partition rationale** —— 2 paragraphs: the FIPS-204 algorithm splits
  cleanly along these subsystems; every primitive has a KAT intermediate-value
  dump, so each subsystem can be verified independently.

## Tier-1: per-subsystem Q&A (recursive block flow)

Each of the six subsystems now enters its own block-scope round. For brevity,
this exemplar shows one in full (`ntt_core`), with the rest pointing at the
relevant per-block exemplars.

### `ntt_core` Tier-1, Round 1 —— data types and throughput

```
NTT-1. Coefficient width:
   A) 23-bit signed (matches q=8380417, ⌈log2(q)⌉=23) ★
   B) 32-bit (wasteful; helpful for debug)

NTT-2. Butterflies per cycle:
   A) 1 butterfly/cycle (8 cycles × 256 = ~2k cycles per 1024-NTT) ★ —— enough
   B) 4 parallel butterflies (4× DSP, useful when throughput matters)
   C) Pipelined radix-4 (fewer cycles, more area)

NTT-3. Twiddle storage:
   A) Pre-computed ROM, 1024 entries, generated by build script ★
   B) Compute on the fly (saves BRAM, costs cycles)

NTT-4. Modular reduction:
   A) Montgomery, fixed R=2^32 ★ —— textbook approach for MLDSA, two
      multiplies + one subtract
   B) Barrett (slightly cheaper for one-shot, worse for streaming)
```

The remaining Q&A for `ntt_core` follows the FIR streaming pattern
(precision, backpressure, reset behavior —— see `dialogue-streaming-fir.md`).

### Other subsystems (Tier-1 entry pointers)

| subsystem | follow which per-block exemplar |
|-----------|----------------------------------|
| keccak_core | dialogue-streaming-fir.md (pipelined compute) —— but with a custom Keccak round-constant table |
| sampler   | dialogue-crc-engine.md (rejection-sampling state machine, reference-model = numpy SHAKE → rejection sampling) |
| top_ctrl  | FSM round follows dialogue-async-fifo.md style (state-legality invariants), then append a custom round for per-mode (KeyGen/Sign/Verify) timing |
| key_storage | dialogue-peripheral-spi.md style, for the AXIL-accessible memory map (overlay the "CSR" pattern onto a RAM with access-control bits) |
| csr_block | use dialogue-peripheral-spi.md directly (this is exactly a CSR block with an IRQ) |

Each one ultimately produces its own `docs/subsystems/<name>/spec.md`,
`uarch.md`, `plan.md`.

## Integration planning round (after all Tier-1 sign-offs)

```
I-1. Cross-subsystem handshake style:
   A) One valid/ready pair per producer → consumer ★ —— uniform; conforms
      to AXIS convention
   B) Custom credit-based
   C) Memory-mapped —— every interaction goes through the key_storage
      scratchpad (slow)

I-2. Top-level CDC inventory:
   A) None (arch.md Round 2 Q7 decided single clock) ★ —— declared and
      confirmed
   B) (If multi-clock had been chosen) 2-FF per pair plus Gray on any
      counter

I-3. CSR ownership:
   A) csr_block owns the entire 0x0000–0x0FFF region; other subsystems
      expose status via an internal status network, muxed by csr_block ★
   B) Distributed CSR, each subsystem brings its own decoder

I-4. Top-level test scenarios (end-to-end):
   A) Three scenarios —— KeyGen-KAT, Sign-KAT, Verify-KAT ★ —— each spans
      all six subsystems
   B) One scenario per primitive (loses cross-subsystem coverage)
   C) Hundreds of random-message tests (defer to the verification skill)

Pick A/A/A/A?
```

User: A/A/A/A.

### Output: `docs/integration_plan.md` (skeleton)

- **Cross-subsystem interfaces** —— a table whose rows include
  `keccak_core → sampler`, `sampler → top_ctrl`, `top_ctrl → ntt_core`,
  `top_ctrl → key_storage`, `top_ctrl → csr_block`,
  `csr_block ↔ AXIL host`. All valid/ready; each row notes width and meaning.
- **Top-level CDC inventory** —— *none* (single clock, declared "none"
  explicitly so that the "none" is a decision rather than an oversight).
- **Aggregate CSR map** —— flatten the csr_block internal register file into
  the 0x0000 region of the memory map.
- **Aggregate interrupt** —— single host IRQ; DONE comes from `top_ctrl`,
  ERR from any subsystem, aggregated by `csr_block`.
- **Top-level test scenarios**:
  - `kat_keygen_match` —— feed FIPS-204 seed, expect KAT public key
  - `kat_sign_match` —— feed KAT message + private key, expect KAT signature
  - `kat_verify_match` —— feed KAT signature, expect ACCEPT

## Milestone planning round

The user's answer to Round 4 Q14 has already locked the strategy.
`milestones.md` writes it up as a roster.

### Output: `docs/milestones.md` (skeleton)

- **P0 —— interface stub-out**
  - real: `csr_block`, AXIL slave
  - stub: every other subsystem (returns canned data)
  - acceptance: top-level TB compiles, host can read the CSR.ID register,
    the IRQ line can toggle, plan-check passes
- **P1 —— KeyGen end-to-end**
  - real: `keccak_core`, `sampler`, `key_storage`, `top_ctrl` (KeyGen mode
    only), `csr_block`
  - stub: `ntt_core` (only used in Sign/Verify)
  - acceptance: `kat_keygen_match` scenario passes
- **P2 —— Sign end-to-end**
  - real: `ntt_core` filled in; `top_ctrl` gains Sign mode
  - acceptance: `kat_sign_match` scenario passes
- **P3 —— Verify end-to-end**
  - real: `top_ctrl` gains Verify mode (no new RTL elsewhere)
  - acceptance: `kat_verify_match` scenario passes

## How the File list distributes across subsystems

Each subsystem's `uarch.md` carries its own File list and allocation. As an
example, the end of `ntt_core/uarch.md` is:

| path | role | test | artifact |
|------|------|------|----------|
| rtl/ntt_core/ntt_top.sv     | top integration | property/invariant                   | upper bound on total NTT cycle count; output-valid asserted exactly once |
| rtl/ntt_core/butterfly.sv   | single butterfly | reference-model                      | tools/ntt_ref.py (numpy, FIPS 204 Algo 41) —— per butterfly |
| rtl/ntt_core/montgomery.sv  | mod reduce      | reference-model                       | tools/montgomery_ref.py |
| rtl/ntt_core/twiddle_rom.sv | twiddle ROM     | integration                           | covered by tb/ntt_smoke_tb.sv (`rom_matches_build_script`) |

The top-level integration TB lives separately and is named in
`integration_plan.md`'s scenarios —— it is not a subsystem-unit TB.

## Why this pattern

- **Round 0 is not optional** as soon as the brief even hints at "an IP that
  does X" and X has known sub-primitives. Treating it as project scope
  unlocks `arch.md` and the subsystem tree; treating it as block scope locks
  the agent into one giant spec that will fail review.
- **Round 1 (partition) is a Tier-0 decision** —— partition mistakes only
  surface when you try to write the integration TB and discover two
  "subsystems" share half their state. Offer options along natural algorithmic
  seams (here, the FIPS-204 named primitives).
- **Memory map and IRQ rules** (Round 3) drive the SW header file. Ask late
  and you have to redesign every subsystem's CSR offset.
- **Milestones (Round 4 Q14) are how you avoid the "build everything together,
  then nothing works" trap.** P0 = stub-out is unromantic, but it's the
  milestone that proves your interfaces work.
- **The KAT scenarios are `integration_plan.md`'s `top-level test scenarios`**
  —— they exist because Round 3 required them, not because a template did.
  The integration TB is built from these scenarios, and every subsystem's
  own uarch.md "integration" bucket points back to one of them.
