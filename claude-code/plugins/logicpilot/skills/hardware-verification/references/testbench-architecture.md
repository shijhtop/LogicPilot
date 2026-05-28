# Testbench Architecture

A self-checking testbench has four jobs: drive stimulus, observe outputs, decide
pass/fail, and tell you how much you exercised. Even a small directed TB should
do the first three.

## Minimal self-checking directed TB

1. Generate/release reset, then apply known stimulus vectors.
2. Compute the expected result (inline, a lookup table, or a reference model).
3. Compare DUT output to expected; on mismatch print actual vs expected and the
   cycle, then fail (`$error`/`$fatal` in SV, `assert ... severity failure` in
   VHDL). End with an explicit PASS line and `$finish`/`std.env.finish`.
4. Dump a waveform for debugging when it fails.

The flow's `sim` stage keys off both the exit code and the PASS/FAIL line — a TB
that drives signals but checks nothing will "pass" while hiding bugs.

## Scaling up: the scoreboard pattern

For non-trivial blocks separate concerns into reusable components:

- **Driver** — turns abstract transactions into pin wiggles (respecting the
  protocol: handshakes, backpressure).
- **Monitor** — observes the interface and reconstructs transactions (never
  drives).
- **Reference model** — a behavioral (often higher-level language) model that
  predicts correct outputs.
- **Scoreboard** — compares monitored DUT output against the reference model's
  prediction; this is the end-to-end check.
- **Sequencer/stimulus** — directed vectors, or constrained-random sequences.

This is the structure UVM/UVVM formalize; you can build a lightweight version in
plain SV or in cocotb without the full methodology.

## What to cover (test plan order)

1. Reset behavior and power-up state.
2. Directed happy-path cases from the spec.
3. Edge cases: boundary values, overflow/underflow, full/empty, min/max latency.
4. Protocol stress: back-to-back transactions, stalls/backpressure, interleaving.
5. Error injection: illegal inputs, recovery.
6. Concurrency: clock-domain crossings, reset during operation.

Tie each spec feature to at least one directed test and one coverage point so
you can show the feature was both exercised and checked.

## Reference-model strategies

- **Algorithmic** — reimplement the function in SW (Python in cocotb, C model,
  or SV function). Best for datapaths.
- **Golden vectors** — precomputed input/expected pairs (from a trusted tool).
- **Inverse check** — feed output back through an inverse op and compare to
  input (e.g., encode→decode).
- **Property** — instead of predicting the exact value, assert invariants it
  must satisfy (see assertions); pairs well with constrained-random.

## Reset and clocking hygiene in the TB

Generate clocks with a single always/process; release reset on a clean edge;
parameterize the clock period from the project's target so timing-relevant tests
match intent. Avoid races by sampling DUT outputs on the inactive edge or via a
monitor that respects the protocol's valid timing.
