"""Install hints for common EDA tools (v0.7a §4a.3).

When a stage is blocked because a required external tool is missing,
the driver attaches install_hint to the JSON so the agent can suggest
a concrete install command instead of just "missing tool X".

Schema per tool (all keys optional, omit if no good answer):
    apt:     Debian/Ubuntu apt install command
    brew:    macOS Homebrew formula install
    pacman:  Arch Linux pacman install
    source:  upstream URL with install instructions
    note:    extra one-liner (e.g., 'requires X.Y or newer')
    vendor:  vendor sign-up / download portal URL

INSTALL_HINTS is intentionally a curated allow-list — tools without an
entry simply produce no install_hint (additive evolution: omit > guess).
Adding a hint here only requires the maintainer to verify the install
command actually works; no schema or driver changes are needed.
"""
from __future__ import annotations


# fmt: off
INSTALL_HINTS: dict[str, dict[str, str]] = {
    "yosys": {
        "apt":    "sudo apt install yosys",
        "brew":   "brew install yosys",
        "pacman": "sudo pacman -S yosys",
        "source": "https://yosyshq.net/yosys/download.html",
    },
    "sg_shell": {
        "vendor": "https://www.synopsys.com/implementation-and-signoff/signoff/spyglass.html",
        "note":   "SpyGlass CDC; commercial, license required. Set [cdc].spyglass_script in flow.toml for project-specific TCL.",
    },
    "vcs": {
        "vendor": "https://www.synopsys.com/verification/simulation/vcs.html",
        "note":   "Synopsys VCS; commercial, license required. Used by the power driver to generate SAIF for annotated power analysis.",
    },
    "verilator": {
        "apt":    "sudo apt install verilator",
        "brew":   "brew install verilator",
        "pacman": "sudo pacman -S verilator",
        "source": "https://verilator.org/guide/latest/install.html",
        "note":   "5.0+ recommended for SystemVerilog 'always_ff' and full UVM-lite",
    },
    "verible-verilog-lint": {
        "brew":   "brew install verible",
        "source": "https://github.com/chipsalliance/verible/releases",
        "note":   "single-binary releases for Linux x86_64 / aarch64 / macOS",
    },
    "verible-verilog-syntax": {
        "brew":   "brew install verible",
        "source": "https://github.com/chipsalliance/verible/releases",
    },
    "iverilog": {
        "apt":    "sudo apt install iverilog",
        "brew":   "brew install icarus-verilog",
        "pacman": "sudo pacman -S iverilog",
        "source": "http://iverilog.icarus.com/",
    },
    "vvp": {
        "apt":    "sudo apt install iverilog",
        "brew":   "brew install icarus-verilog",
        "note":   "vvp ships with iverilog",
    },
    "ghdl": {
        "apt":    "sudo apt install ghdl",
        "brew":   "brew install ghdl",
        "pacman": "sudo pacman -S ghdl",
        "source": "https://ghdl.github.io/ghdl/getting.html",
    },
    "nvc": {
        "source": "https://www.nickg.me.uk/nvc/",
    },
    "nextpnr-ice40": {
        "apt":    "sudo apt install nextpnr-ice40",
        "brew":   "brew install nextpnr",
        "source": "https://github.com/YosysHQ/nextpnr/releases",
    },
    "nextpnr-ecp5": {
        "apt":    "sudo apt install nextpnr-ecp5",
        "brew":   "brew install nextpnr",
        "source": "https://github.com/YosysHQ/nextpnr/releases",
    },
    "icepack": {
        "apt":    "sudo apt install fpga-icestorm",
        "brew":   "brew install icestorm",
        "source": "https://github.com/YosysHQ/icestorm",
    },
    "openFPGALoader": {
        "apt":    "sudo apt install openfpgaloader",
        "brew":   "brew install openfpgaloader",
        "source": "https://trabucayre.github.io/openFPGALoader/",
    },
    "sby": {
        "source": "https://github.com/YosysHQ/sby",
        "note":   "ships with the OSS CAD Suite; needs yosys + z3/boolector",
    },
    "jaspergold": {
        "vendor": "https://www.cadence.com/en_US/home/tools/system-design-and-verification/formal-and-static-verification/jasper-gold-verification-platform.html",
        "note":   "commercial; license required. LogicPilot dispatches to it but ships no parser yet — file an issue with an anonymized session log to contribute one.",
    },
    "vcf": {
        "vendor": "https://www.synopsys.com/verification/static-and-formal-verification/vc-formal.html",
        "note":   "Synopsys VC Formal; commercial. LogicPilot dispatches but ships no parser yet.",
    },
    "qverify": {
        "vendor": "https://eda.sw.siemens.com/en-US/ic/questa/formal-verification/",
        "note":   "Siemens Questa Formal; commercial. LogicPilot dispatches but ships no parser yet.",
    },
    "vivado": {
        "vendor": "https://www.xilinx.com/support/download.html",
        "note":   "free WebPACK edition supports 7-series and small Ultrascale",
    },
    "quartus_sh": {
        "vendor": "https://www.intel.com/content/www/us/en/software-kit/quartus-prime-lite.html",
        "note":   "free Lite Edition for Cyclone IV/V/10",
    },
    "openroad": {
        "source": "https://github.com/The-OpenROAD-Project/OpenROAD/blob/master/docs/user/Build.md",
        "note":   "or use OpenLane Docker image for the full ASIC flow",
    },
    "klayout": {
        "apt":    "sudo apt install klayout",
        "brew":   "brew install --cask klayout",
        "source": "https://www.klayout.de/build.html",
    },
    "magic": {
        "source": "http://opencircuitdesign.com/magic/",
    },
    "netgen": {
        "source": "http://opencircuitdesign.com/netgen/",
    },
}
# fmt: on


def hints_for(missing: list[str]) -> dict[str, dict[str, str]]:
    """Return a {tool: hint_dict} subset of INSTALL_HINTS for the missing
    tools. Tools without a registered hint are silently omitted — the
    caller should treat an empty return as "no hints available" and
    skip the install_hint field entirely (additive evolution).
    """
    return {tool: INSTALL_HINTS[tool] for tool in missing if tool in INSTALL_HINTS}
