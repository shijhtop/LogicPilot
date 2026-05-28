# RTL, behavioral, and transaction-level boundaries

## RTL model

An RTL model describes implementable registers, combinational logic, memories,
FSMs, and interfaces. It is expected to pass synthesis. Timing is expressed with
clocks, counters, enables, and pipelines, not `#delay`.

## Behavioral reference model

A behavioral model predicts correct results for simulation. It may use abstract
tasks/functions, dynamic data structures, DPI, delays, or untimed algorithms.
It belongs in `tb/` or model directories, not synthesizable RTL source globs.

## Transaction-level model

A transaction-level model represents operations as packets, commands, or method
calls. It hides signal-level protocol details behind higher-level transactions.
It is useful for architecture exploration and scoreboards, but it must be refined
into explicit clocks, storage, handshakes, and data paths before synthesis.

## Placement rule

When high-level SystemVerilog appears, classify the file first: implementation
hardware, verification infrastructure, or reference model. Then put the file
under the right project glob and run the right stage.
