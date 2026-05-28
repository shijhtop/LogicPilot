---
name: systemverilog-verification-platform
description: >-
  SystemVerilog verification-platform specialist. Use when building or reviewing a SV testbench with interfaces, clocking blocks, virtual interfaces, classes, transactions, generators, drivers, monitors, scoreboards, mailboxes, constrained random, functional coverage, assertions, DPI, or UVM-like component structure.
---

# SystemVerilog Verification Platform

A good verification platform is not just stimulus. It drives legal and illegal
scenarios, observes the DUT, predicts expected behavior, checks automatically,
measures coverage, and reproduces failures exactly.

## Workflow

1. **Write the verification plan first.**
   Map each spec feature to stimulus, checker/assertion, and coverage point.
   Treat coverage holes as feedback into constraints or directed tests.

2. **Define the DUT boundary.**
   Use SV interfaces and modports when a protocol bundle repeats. Use clocking
   blocks for TB drive/sample timing. Use virtual interfaces so class-based
   components can connect to physical interfaces.

3. **Build component roles.**
   - Transaction: one abstract operation.
   - Generator/sequencer: chooses transactions.
   - Driver: converts transactions into pin/interface activity.
   - Monitor: observes pins and reconstructs transactions.
   - Reference model: predicts expected results.
   - Scoreboard: compares observed vs expected.
   - Coverage collector: samples meaningful scenarios, usually from monitors.

4. **Make it self-checking.**
   Every test must fail automatically through assertions, scoreboard mismatch,
   `$fatal`, UVM errors, or equivalent. Waveform-only tests are not regressions.

5. **Use constrained random responsibly.**
   Randomize configuration, data, legal/illegal protocol cases, timing,
   backpressure, and reset/error injection. Log the seed for every run. Check
   `randomize()` return values. Avoid accidental signed constraints unless they
   are intended.

6. **Use coverage as feedback, not decoration.**
   Define covergroups close to the abstraction being measured. Use bins,
   crosses, `ignore_bins`, and `illegal_bins` deliberately. Do not merge coverage
   from failing tests.

7. **Control concurrency explicitly.**
   Use `fork/join`, events, mailboxes, and semaphores for clear ownership and
   synchronization. Stop or join spawned threads. Avoid shared mutable state
   without a protocol.

8. **Add assertions where they are strongest.**
   Use **concurrent** assertions (`assert property @(posedge clk) disable iff
   (!rst_n) ...`) for temporal / protocol rules; use **immediate** assertions
   (`assert(cond) else $error;`) only for checking `$cast` /
   `randomize()` return / class invariants. Label every concurrent
   assertion with `ERROR_<what_failed>:` — waveform viewers show the label.
   Use scoreboards for end-to-end data correctness. **Bind** SVA files
   when RTL is untouchable: wrap assertions in a checker module with
   input-only ports, then `bind <target_module> chk_<name> u_chk (.*);`
   injects the checks into every instance (qualify with `:<inst>` to
   target one). Forbid X-testing inside `case` items (`2'bxx:` branches);
   use a `default:` arm that flags illegal state instead.

9. **Use DPI only for the right reason.**
   DPI is appropriate for C/C++ reference models, acceleration, or legacy
   libraries. Keep data conversions explicit and deterministic.

10. **Run tool stages.**
    Run `tb-audit`, then `sim`, then coverage/report stages when configured.

## Definition of done

The testbench is self-checking, deterministic under a logged seed, race-aware at
the DUT boundary, has a scoreboard or equivalent checker, includes assertions for
protocol rules, and maps every planned feature to at least one coverage point.
