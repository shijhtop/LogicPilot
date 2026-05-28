# Built-in audit rule rationale

| Rule | Why it matters |
|------|----------------|
| Delay control in RTL | Simulation timing does not synthesize into hardware timing. |
| full_case / parallel_case | Can hide incomplete decode and create simulation/synthesis mismatch. |
| casex | Treats X/Z as don't-cares and can mask real bugs. |
| missing case default | Common accidental latch / illegal-state behavior. |
| defparam | Fragile cross-hierarchy parameter override; use instance parameters. |
| initial in RTL | FPGA-specific at best; ASIC-incompatible unless mapped intentionally. |
| blocking in clocked block | Can create race/scheduling mismatch. |
| nonblocking in comb block | Can hide combinational ordering mistakes. |
| VHDL after/wait for | Testbench timing, not synthesizable RTL timing. |
| SV class/randomize/covergroup/mailbox/semaphore/DPI in RTL | Verification/modeling constructs are not synthesizable implementation RTL. |
| `$unit` declarations/imports | Shared declarations outside packages create compile-order hazards. |
| missing `default_nettype none` | Implicit nets hide typos and declaration-order bugs. |
| missing SV timebase policy | Simulation time can depend on compile context. |
| enum without explicit RTL base | Default enum base can hide X behavior and mismatch intended hardware width. |
| 2-state RTL signals | `bit`/2-state types can mask X/Z/reset issues in implementation RTL. |
| `$cast` in RTL | Dynamic casts are simulation checks; use static casts/explicit decode in RTL. |
| dynamic SV objects in RTL | Dynamic containers/strings/events belong in TB/reference models. |
| interface without modport | Interface roles/directions are ambiguous for reusable RTL. |
| clocking block in RTL interface | Clocking blocks are TB drive/sample constructs. |
| interface task/function not automatic | Static storage in imported methods can surprise synthesis and reuse. |
| wildcard `.*` port connection | Depends on exact names and can silently connect unintended ports. |
| explicit always_latch | Legal when intentional, but often accidental or target-unfriendly. |
| TB no visible self-check | Simulation without automated checking is not a regression. |
| TB random without seed logging | Random failures must be replayable. |
| TB coverage without checkers | Coverage does not prove correctness without pass/fail checks. |

The audit intentionally does not try to prove CDC safety; CDC requires structural
domain enumeration and pattern review.
