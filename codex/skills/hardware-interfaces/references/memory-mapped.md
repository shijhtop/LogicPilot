# Memory-mapped & register interfaces

All of these move address + data between a master (initiator) and slave (target).
They differ in complexity, pipelining, and ecosystem. Pick the simplest that
meets the bandwidth need.

## AXI4-Lite (registers / control)

A subset of AXI4 for single (non-burst) transfers — ideal for a register map.
**Five independent channels**, each with its own valid/ready handshake:
- Write address (**AW**), Write data (**W**), Write response (**B**).
- Read address (**AR**), Read data (**R**).

Key ordering rules:
- A write completes only after **both** the AW and W handshakes occur; the slave
  then returns a response on **B** (`OKAY`/`SLVERR`). The two write channels are
  independent — don't assume AW and W arrive together.
- Read: master sends AR, slave returns data + response on R.
- 32- or 64-bit data, byte strobes (`WSTRB`) on writes; no bursts, no IDs.

A typical slave: decode the address, on write capture `WDATA` under `WSTRB`
into the register, return `BRESP`; on read, mux the register to `RDATA`. Watch
the channel independence and the response ordering — that's where Lite slaves
go wrong.

## Full AXI4 (high-throughput memory)

Adds to the five channels: **bursts** (`AxLEN` beats, `AxSIZE` bytes/beat,
`AxBURST` INCR/WRAP/FIXED), **transaction IDs** (`AxID`) enabling multiple
outstanding and out-of-order completion, and QoS/cache/prot attributes. Use when
you need real memory bandwidth; it's heavier to implement and verify.

## APB (simple peripheral bus, AMBA)

The simplest AMBA bus: non-pipelined, single transfers, low power. A transfer is
a small state sequence — IDLE → SETUP (assert `PSEL`) → ACCESS (assert
`PENABLE`, hold until `PREADY`). Signals: `PADDR`, `PWRITE`, `PWDATA`, `PRDATA`,
`PSEL`, `PENABLE`, `PREADY` (wait states), `PSLVERR`. Great for low-bandwidth
control registers; often sits behind an AXI/AHB-to-APB bridge.

## AHB / AHB-Lite (pipelined, AMBA)

Higher performance than APB: pipelined address/data phases and bursts.
**AHB-Lite** restricts to a single master (common in FPGAs), simplifying
arbitration away. Signals include `HADDR`, `HTRANS` (IDLE/BUSY/NONSEQ/SEQ),
`HWRITE`, `HWDATA`, `HRDATA`, `HREADY` (slave wait/pipeline control), `HRESP`.

## Avalon-MM (Intel/Altera)

Intel's memory-mapped interface (Nios II ecosystem). Address + `read`/`write` +
`writedata`/`readdata`, with `waitrequest` (slave stalls the master) and
`readdatavalid` for pipelined/variable-latency reads; `byteenable` for partial
words. Conceptually close to AXI-Lite with different signal names.

## Wishbone (open / public domain, OpenCores)

A public-domain, license-free SoC interconnect. Classic cycle (B3): `CYC`
(cycle active), `STB` (strobe/valid), `WE`, `ADR`, `DAT_I`/`DAT_O`, `SEL`,
terminated by `ACK` (or `ERR`/`RTY`). B4 adds a **pipelined** mode (a `STALL`
signal acting like `ready`) so multiple requests can be outstanding. All signals
active-high; an IP core need not implement every optional signal. Common in open
designs and Lattice/OpenCores cores.

## Choosing & bridging

- Registers, minimal logic → APB or Wishbone-classic.
- Registers in a Xilinx/ARM flow → AXI4-Lite (plug-and-play with the IP
  integrator).
- Streaming → AXI4-Stream / Avalon-ST (see handshake-and-streaming.md).
- Bandwidth/bursts → full AXI4 or AHB.
- Mixed ecosystems → use a documented bridge (e.g. Avalon↔Wishbone,
  AXI↔APB); the mapping is mechanical but mind the response-ordering and
  wait-state semantics of each side.
