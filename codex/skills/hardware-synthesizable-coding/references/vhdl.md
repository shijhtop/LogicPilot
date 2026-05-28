# VHDL — Synthesizable Subset

Standard: **IEEE 1076-2019** (revision of 1076-2008; it incorporates PSL). Use
the `numeric_std` package (`signed`/`unsigned`) for arithmetic — not the
deprecated `std_logic_arith`/`_unsigned`. See `references/standards.md`.

## Clocked vs combinational processes

```vhdl
-- Sequential (flip-flops)
process(clk)
begin
  if rising_edge(clk) then
    if rst = '1' then q <= (others => '0');   -- synchronous reset
    else              q <= d;
    end if;
  end if;
end process;

-- Async reset variant: reset on the sensitivity list
process(clk, rst)
begin
  if rst = '1' then    q <= (others => '0');
  elsif rising_edge(clk) then q <= d;
  end if;
end process;

-- Combinational
process(all)            -- VHDL-2008; else list every read signal
begin
  y <= '0';             -- default avoids a latch
  if en = '1' then y <= a; end if;
end process;
```

## signal vs variable

- `signal` models a hardware net; assignment (`<=`) takes effect after the
  process suspends (delta cycle) — this is the hardware-accurate behavior.
- `variable` (`:=`) updates immediately within the process; use only when you
  understand it infers either combinational logic or, if carried across a clock
  edge, a register. Prefer signals for clarity; one process drives a given
  signal.

## Types

- Use `ieee.numeric_std` with `unsigned`/`signed` for arithmetic. **Do not** use
  the non-standard `std_logic_arith`/`std_logic_unsigned`.
- `std_logic`/`std_logic_vector` for ports (resolved, 9-value); convert to
  `unsigned`/`signed`/`integer` for math, convert back for ports.
- Records and arrays synthesize (they're structured bit collections). Constrain
  ranges; unconstrained needs care.
- Enumerated types are ideal for FSM state.

## Completeness & latches

Every combinational process must assign all outputs on all paths (default
assignment), and every `case` needs `when others`. A missing branch infers a
latch — same trap as Verilog.

## Compile order matters

VHDL is analyzed in dependency order: **packages and entities must be analyzed
before the units that use them.** Globbing sorts alphabetically, which can break
this. List `src` files in the correct order in `flow.toml` (packages first, then
lower-level entities, then top), rather than relying on a wildcard.

## --std selection

Pick a standard and pass it consistently to analyze/elaborate (`--std=08` for
VHDL-2008 in GHDL; the flow's `ghdl` candidate uses `--std=08`). VHDL-2008 adds
`process(all)`, simpler generics, and unconstrained-element conveniences. Make
sure your synthesis path (e.g. ghdl-yosys-plugin or vendor tool) supports the
chosen standard.

## Testbench-only constructs

`wait for`, `after`, `assert ... report ... severity`, file I/O, `std.env.finish`
— for simulation, not synthesis. Keep them in `tb/` files.

## Synthesis path note

Open-source VHDL synthesis goes through GHDL → Yosys (`yosys -m ghdl`), which
requires the ghdl-yosys-plugin installed. Vendor tools (Vivado/Quartus) synthesize
VHDL natively. The flow selects the right `synth` candidate from the detected
language; if the plugin isn't installed the stage reports it clearly.
