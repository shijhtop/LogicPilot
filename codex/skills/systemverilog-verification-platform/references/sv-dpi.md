# DPI usage notes

Use DPI when a C/C++ model or library is the right reference model or acceleration
path. Avoid it for simple functions that can be written clearly in SV.

## Rules

- Keep imports/exports in testbench or model code, not synthesizable RTL.
- Use simple value types when possible.
- **DPI C arguments are inherently 2-state** (no X / Z representation).
  When an SV-side 4-state signal feeds a DPI import, X / Z must be
  explicitly trapped before the call — silent X→0/1 conversion on the C
  side produces false-positive reference-model matches that mask real
  bugs. Add an `assert(!$isunknown(sig))` immediate check on every
  4-state signal feeding a DPI import.
- Keep ownership and lifetime of C-side objects clear when using handles.
- Make DPI calls deterministic for regression replay.
- Log versions of external models used in sign-off regressions.
