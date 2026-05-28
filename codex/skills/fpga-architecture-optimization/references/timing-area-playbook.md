# FPGA timing and area playbook

## Critical-path reduction patterns

### Pipeline a datapath

Before:

```systemverilog
assign y = (((a + b) * c) + d) ^ e;
```

After: split at operator boundaries and delay valid/control by the same number
of stages.

### Balance an adder tree

Prefer a tree over a linear accumulator when all terms are available in the same
cycle. A balanced tree reduces logic depth; pipeline levels when Fmax requires.

### Remove priority chains

A long `if/else if` implements priority. Use a `case` or one-hot mux when
priority is not required.

## Resource inference patterns

- BRAM: synchronous read, registered address/control, no reset of the array.
- LUTRAM: small RAMs or asynchronous-read tables when BRAM is too coarse.
- SRL: shift register with no reset on every stage.
- DSP: explicit `*` with suitable widths and pipeline registers near the
  multiplier/add/sub stages.

## Area trade-offs

- Pipelining increases FF count and latency but reduces LUT depth.
- Resource sharing reduces DSP/LUT area but lowers throughput or adds scheduling
  latency.
- One-hot FSMs increase FFs but can reduce LUT decode and raise Fmax.
- Binary FSMs reduce FFs but can deepen decode logic.
