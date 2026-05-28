# HDL & verification standards (current editions)

Cite the right standard and edition — it signals rigor and resolves "is this
legal?" arguments. Current as of the language revisions below.

## Design languages

- **SystemVerilog — IEEE 1800-2023** (published Dec 2023). The current LRM.
  Since **IEEE 1800-2009** the base Verilog standard **IEEE 1364-2005** was
  merged in, so there is no separate Verilog standard to cite for new work —
  1800 *is* Verilog + SystemVerilog. Earlier milestones: 1800-2005 (first SV),
  1800-2012, 1800-2017. (Also adopted as IEC 62530.)
- **VHDL — IEEE 1076-2019** (revision of 1076-2008). Notably, this revision
  **incorporates PSL** into VHDL and folds in several previously-separate
  library-package standards. Use `numeric_std` (`signed`/`unsigned`), not the
  deprecated `std_logic_arith`/`std_logic_unsigned` Synopsys packages.

## Synthesizable subset (historical, still the conceptual reference)

- **IEEE 1364.1** (Verilog RTL synthesis) and **IEEE 1076.6** (VHDL RTL
  synthesis) defined the *synthesizable subset*. Both are inactive/withdrawn and
  were never fully tracked by tools, so in practice the synthesizable subset is
  defined by **what your synthesis tool accepts**, not by a live standard. Treat
  these as the conceptual baseline; let the `synth` stage be the arbiter.

## Verification & low-power

- **UVM — IEEE 1800.2-2020** (Universal Verification Methodology LRM). The
  Accellera UVM reference implementation tracks this.
- **PSL — IEEE 1850** (Property Specification Language); also incorporated into
  VHDL 1076-2019. SVA (SystemVerilog Assertions) is defined within IEEE 1800.
- **UPF — IEEE 1801-2024** (Unified Power Format) for power-intent /
  energy-aware design and verification.

## Practical notes

- "SystemVerilog" in a tool's docs rarely means *all* of 1800-2023 — synthesis
  accepts a subset, simulation/verification accepts more. State which you mean.
- Free copies of 1800-2023 and several others are available via the IEEE GET
  program (courtesy of Accellera); the VHDL 1076 machine-readable elements are
  in the IEEE 1076 open-source repository.
- When a construct's legality is disputed, name the clause/edition rather than
  asserting from habit.
