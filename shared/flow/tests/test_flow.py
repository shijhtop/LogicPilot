"""Unit tests for logicpilot.py — run with: pytest -q (or python -m pytest).

These don't need real EDA tools; PATH probing is monkeypatched. They lock in the
behavior that matters: HDL detection, simulator priority/fallback/blocking, the
metric-regex fix, and placeholder expansion.
"""
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow import compat as ff  # noqa: E402


def write_cfg(tmp_path: Path, body: str, files=None) -> Path:
    (tmp_path / "rtl").mkdir(exist_ok=True)
    for name, content in (files or {}).items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    cfg = tmp_path / "flow.toml"
    cfg.write_text(textwrap.dedent(body))
    return cfg


PRESET = textwrap.dedent("""
    [[stages.sim.candidates]]
    name = "verilator"
    hdl  = ["verilog"]
    probe = "verilator"
    cmd = "verilator {src} {tb}"

    [[stages.sim.candidates]]
    name = "iverilog"
    hdl  = ["verilog"]
    probe = "iverilog"
    cmd = "iverilog {src} {tb}"

    [[stages.sim.candidates]]
    name = "ghdl"
    hdl  = ["vhdl"]
    probe = "ghdl"
    cmd = "ghdl {src} {tb}"
""")


def cfg_with_preset(tmp_path: Path, body: str, files=None) -> dict:
    (tmp_path / "presets").mkdir(exist_ok=True)
    (tmp_path / "presets" / "p.toml").write_text(PRESET)
    cfg_path = write_cfg(tmp_path, body, files)
    return ff.load_config(cfg_path)


# ---------------- HDL detection ----------------

def test_hdl_autodetect_verilog(tmp_path):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.v": "module t(); endmodule"})
    assert ff.resolve_hdl(cfg) == "verilog"


def test_hdl_autodetect_vhdl(tmp_path):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.vhd"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.vhd": "entity t is end;"})
    assert ff.resolve_hdl(cfg) == "vhdl"


def test_hdl_autodetect_mixed(tmp_path):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v","rtl/*.vhd"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.v": "module t(); endmodule", "rtl/u.vhd": "entity u is end;"})
    assert ff.resolve_hdl(cfg) == "mixed"


def test_hdl_explicit_override(tmp_path):
    # .v files present but declared vhdl -> declaration wins
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        hdl="vhdl"
        src=["rtl/*.v"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.v": "module t(); endmodule"})
    assert ff.resolve_hdl(cfg) == "vhdl"


# ---------------- simulator priority / fallback / blocked ----------------

def test_sim_picks_first_available(tmp_path, monkeypatch):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.v": "module t(); endmodule"})
    monkeypatch.setattr(ff.shutil, "which", lambda p: "/usr/bin/" + p)  # all present
    r = ff.resolve_stage("sim", cfg)
    assert r["tool"] == "verilator"  # priority #1


def test_sim_falls_back_when_first_missing(tmp_path, monkeypatch):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.v": "module t(); endmodule"})
    # verilator absent -> should fall back to iverilog
    monkeypatch.setattr(ff.shutil, "which", lambda p: None if p == "verilator" else "/usr/bin/" + p)
    r = ff.resolve_stage("sim", cfg)
    assert r["tool"] == "iverilog"


def test_sim_vhdl_selects_ghdl(tmp_path, monkeypatch):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        hdl="vhdl"
        src=["rtl/*.vhd"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.vhd": "entity t is end;"})
    monkeypatch.setattr(ff.shutil, "which", lambda p: "/usr/bin/" + p)
    r = ff.resolve_stage("sim", cfg)
    assert r["tool"] == "ghdl"  # only vhdl candidate


def test_sim_blocked_when_no_tool_installed(tmp_path, monkeypatch):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.v": "module t(); endmodule"})
    monkeypatch.setattr(ff.shutil, "which", lambda p: None)  # nothing installed
    r = ff.resolve_stage("sim", cfg)
    assert "blocked" in r and "verilator" in r["blocked"]


def test_run_stage_reports_project_config_command_source(tmp_path, monkeypatch):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        build_dir="build"
        [toolchain]
        preset="p"
    """, files={"rtl/t.v": "module t(); endmodule"})
    monkeypatch.setattr(ff.shutil, "which", lambda p: "/usr/bin/" + p)

    out = ff.run_stage("sim", cfg, print_cmd=True)

    assert out["command_source"] == "project_config"


def test_blocked_stage_reports_command_source(tmp_path, monkeypatch):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.v": "module t(); endmodule"})
    monkeypatch.setattr(ff.shutil, "which", lambda p: None)

    out = ff.run_stage("sim", cfg)

    assert out["status"] == "blocked"
    assert out["command_source"] == "project_config"


def test_shipped_preset_reports_shipped_command_source(tmp_path, monkeypatch):
    cfg = write_cfg(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [toolchain]
        preset="yosys-nextpnr"
    """, files={"rtl/t.v": "module t(); endmodule"})
    loaded = ff.load_config(cfg)
    monkeypatch.setattr(ff.shutil, "which", lambda p: "/usr/bin/" + p)

    out = ff.run_stage("sim", loaded, print_cmd=True)

    assert out["command_source"] == "shipped_preset"


def test_sim_blocked_for_mixed_without_dual_tool(tmp_path, monkeypatch):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v","rtl/*.vhd"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.v": "module t(); endmodule", "rtl/u.vhd": "entity u is end;"})
    monkeypatch.setattr(ff.shutil, "which", lambda p: "/usr/bin/" + p)
    r = ff.resolve_stage("sim", cfg)
    assert "blocked" in r  # no candidate supports both verilog AND vhdl


# ---------------- metric parsing (the regex fix) ----------------

def test_parse_metrics_yosys_stat():
    log = textwrap.dedent("""
        Generating RTLIL representation for module `\\SB_LUT4'.
        Number of cells:                 23
          SB_CARRY                        6
          SB_DFFER                        8
          SB_LUT4                         9
    """)
    m = ff.parse_metrics(log, {})
    assert m.get("luts") == 9   # NOT 23 or a stray number from the decl line
    assert m.get("ffs") == 8


def test_parse_metrics_no_cross_line_bleed():
    # label on one line, number many lines later -> must NOT match
    log = "SB_LUT4'\nsome text\nmore\nSB_RAM40_4K appears later 40"
    m = ff.parse_metrics(log, {})
    assert "luts" not in m  # the old [^\\d]* bug would have grabbed 40


def test_parse_metrics_wns_negative_flag():
    log = "Worst Negative Slack (WNS): -1.234 ns"
    m = ff.parse_metrics(log, {})
    assert m.get("wns_ns") == -1.234


def test_parse_power_metrics_and_unit_normalization():
    """Power patterns opt in when stage_name is recognized as power-related.
    The bare-word power label regexes (Static / Signal / Clock / Logic /
    BRAM / DSP) are otherwise off because they create false positives in
    synth/pnr logs."""
    log = """
      | Total On-Chip Power (W) | 1.234 |
      Total Dynamic Power: 900 mW
      Device Static: 334 mW
      Junction Temperature (C): 54.7
    """
    m = ff.parse_metrics(log, {}, stage_name="power")
    assert m.get("total_power_w") == 1.234
    assert m.get("dynamic_power_w") == pytest.approx(0.9)
    assert m.get("static_power_w") == pytest.approx(0.334)
    assert m.get("junction_temp_c") == 54.7


def test_power_patterns_skipped_for_non_power_stages():
    """Same log, but stage='synth' → no power metrics emitted."""
    log = """
      yosys: Static lookup table mapping done
      Signal foo elaborated
      Logic optimization pass complete
    """
    m_synth = ff.parse_metrics(log, {}, stage_name="synth")
    assert "static_power_w" not in m_synth
    assert "signal_power_w" not in m_synth
    assert "logic_power_w" not in m_synth


def test_power_patterns_opt_in_via_metrics_power_stages():
    """Project-defined power-style stages can opt in."""
    log = "Total Dynamic Power: 100 mW"
    cfg = {"metrics": {"power_stages": ["my_custom_power"]}}
    m = ff.parse_metrics(log, cfg, stage_name="my_custom_power")
    assert m.get("dynamic_power_w") == pytest.approx(0.1)


# ---------------- placeholder expansion ----------------

def test_render_expands_known_and_keeps_unknown():
    out = ff.render("run {top} tb {tb_top} unknown {nope}", {"top": "cpu", "tb_top": "cpu_tb"})
    assert "cpu" in out and "cpu_tb" in out and "{nope}" in out


@pytest.mark.parametrize("tcl", [
    "x = {4{1'b0}};",            # SystemVerilog replication (nested braces)
    "set_prop {mode:fast}",      # colon inside braces (TCL named arg)
    "puts {x!y}",                # bang inside braces
    "puts {}",                   # empty braces
    "foreach {a {b} c} {body}",  # nested TCL braces
])
def test_render_survives_literal_braces(tcl):
    # str.format_map would raise ValueError on all of these; the regex renderer
    # must leave them untouched (this is what makes vendor TCL presets work).
    assert ff.render(tcl, {"top": "cpu"}) == tcl


def test_render_substitutes_amid_tcl_braces():
    out = ff.render("read_verilog [list {src}]; foreach c {a b} {puts $c}; top {top}",
                    {"src": "a.v", "top": "cpu"})
    assert out == "read_verilog [list a.v]; foreach c {a b} {puts $c}; top cpu"


def test_tb_top_defaults_to_top_tb(tmp_path):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="cpu"
        src=["rtl/*.v"]
        [toolchain]
        preset="p"
    """, files={"rtl/cpu.v": "module cpu(); endmodule"})
    assert ff.build_vars(cfg)["tb_top"] == "cpu_tb"


def test_tb_top_override(tmp_path):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="cpu"
        tb_top="my_testbench"
        src=["rtl/*.v"]
        [toolchain]
        preset="p"
    """, files={"rtl/cpu.v": "module cpu(); endmodule"})
    assert ff.build_vars(cfg)["tb_top"] == "my_testbench"


# ---------------- pipeline order & auto-exposed vars (ASIC enablement) -------

def test_preset_declares_pipeline_order(tmp_path):
    (tmp_path / "presets").mkdir(exist_ok=True)
    (tmp_path / "presets" / "asic.toml").write_text(textwrap.dedent("""
        [pipeline]
        order = ["lint", "synth", "floorplan", "place", "cts", "route", "gds"]
        [stages.synth]
        cmd = "echo synth"
        [stages.floorplan]
        cmd = "echo fp"
        [stages.gds]
        cmd = "echo gds"
    """))
    (tmp_path / "rtl").mkdir(exist_ok=True)
    (tmp_path / "rtl" / "t.v").write_text("module t(); endmodule")
    cfg_path = tmp_path / "flow.toml"
    cfg_path.write_text('[project]\ntop="t"\nsrc=["rtl/*.v"]\n[toolchain]\npreset="asic"\n')
    cfg = ff.load_config(cfg_path)
    assert cfg["_pipeline"] == ["lint", "synth", "floorplan", "place", "cts", "route", "gds"]
    out = ff.run_all(cfg, print_cmd=True)
    # Declared stages that exist keep their relative order; the built-in
    # front-end gates and closing report are injected around them.
    assert out["pipeline"] == ["audit", "tb-audit", "synth", "floorplan", "gds", "report"]
    # The declared (existing) stages still appear in their declared order.
    declared_present = [s for s in out["pipeline"] if s in ("synth", "floorplan", "gds")]
    assert declared_present == ["synth", "floorplan", "gds"]


def test_auto_expose_project_toolchain_scalars(tmp_path):
    cfg = cfg_with_preset(tmp_path, """
        [project]
        top="aes"
        src=["rtl/*.v"]
        die_area = "0 0 100 100"
        [toolchain]
        preset="p"
        platform="sky130hd"
        config_mk="designs/aes/config.mk"
    """, files={"rtl/aes.v": "module aes(); endmodule"})
    v = ff.build_vars(cfg)
    assert v["platform"] == "sky130hd"          # plain scalar exposed
    assert v["die_area"] == "0 0 100 100"
    assert v["config_mk"].endswith("/designs/aes/config.mk")  # path-like -> resolved
    assert v["config_mk"].startswith("/")


@pytest.mark.parametrize("log", [
    "Warning: inferred latch for signal 'q'",
    "  $_DLATCH_P_   2",
    "%Warning-LATCH: example.v:12: Latch inferred for signal 'state'",
])
def test_quality_warning_inferred_latch(log):
    w = ff.quality_warnings(log)
    assert any("latch" in x.lower() for x in w)


def test_quality_warning_multi_driver():
    w = ff.quality_warnings("Error: net 'd' has multiple drivers")
    assert any("multiple drivers" in x.lower() for x in w)


def test_quality_warning_clean_log_is_silent():
    # a normal, clean synth log must not trip the red-flag scan
    log = "SB_LUT4   9\nSB_DFFER  8\nMax frequency for clock: 120.5 MHz"
    assert ff.quality_warnings(log) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ---------------- Round 4 hardening: probes, scope, checks, timeout ----------

def test_fixed_stage_missing_probes_is_blocked(tmp_path, monkeypatch):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [stages.pnr]
        probes=["definitely_missing_nextpnr"]
        cmd="echo pnr"
    """, files={"rtl/t.v": "module t(); endmodule"})
    cfg = ff.load_config(cfg_path)
    monkeypatch.setattr(ff.shutil, "which", lambda p: None)
    r = ff.resolve_stage("pnr", cfg)
    assert "blocked" in r
    assert "definitely_missing_nextpnr" in r["blocked"]


def test_candidate_requires_all_probes_and_falls_back(tmp_path, monkeypatch):
    (tmp_path / "presets").mkdir(exist_ok=True)
    (tmp_path / "presets" / "p.toml").write_text(textwrap.dedent("""
        [[stages.sim.candidates]]
        name="iverilog"
        hdl=["verilog"]
        probes=["iverilog", "vvp"]
        cmd="iverilog {src} && vvp a.out"

        [[stages.sim.candidates]]
        name="verilator"
        hdl=["verilog"]
        probes=["verilator"]
        cmd="verilator {src}"
    """))
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.v": "module t(); endmodule"})
    cfg = ff.load_config(cfg_path)
    monkeypatch.setattr(ff.shutil, "which", lambda p: None if p == "vvp" else "/bin/" + p)
    r = ff.resolve_stage("sim", cfg)
    assert r["tool"] == "verilator"


def test_synth_scope_uses_rtl_not_testbench_language(tmp_path, monkeypatch):
    (tmp_path / "presets").mkdir(exist_ok=True)
    (tmp_path / "presets" / "p.toml").write_text(textwrap.dedent("""
        [[stages.synth.candidates]]
        name="yosys+ghdl"
        hdl=["vhdl"]
        probes=["yosys", "ghdl"]
        cmd="echo synth-vhdl"

        [[stages.sim.candidates]]
        name="ghdl"
        hdl=["vhdl"]
        probes=["ghdl"]
        cmd="echo sim-vhdl"
    """))
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="t"
        hdl="auto"
        src=["rtl/*.vhd"]
        tb=["tb/*.sv"]
        [toolchain]
        preset="p"
    """, files={"rtl/t.vhd": "entity t is end;", "tb/t_tb.sv": "module t_tb; endmodule"})
    cfg = ff.load_config(cfg_path)
    monkeypatch.setattr(ff.shutil, "which", lambda p: "/bin/" + p)
    synth = ff.resolve_stage("synth", cfg)
    sim = ff.resolve_stage("sim", cfg)
    assert synth["hdl"] == "vhdl"
    assert synth["tool"] == "yosys+ghdl"
    assert "blocked" in sim and sim["hdl"] == "mixed"


def test_stage_checks_can_fail_on_fail_regex_even_with_exit_zero(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [stages.sim]
        cmd="printf 'FAIL: scoreboard mismatch\\n'"
        [stages.sim.checks]
        fail_regex="FAIL"
    """, files={"rtl/t.v": "module t(); endmodule"})
    cfg = ff.load_config(cfg_path)
    r = ff.run_stage("sim", cfg)
    assert r["returncode"] == 0
    assert r["status"] == "fail"
    assert r["checks"]["fail_seen"] is True


def test_stage_checks_can_require_pass_marker(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [stages.sim]
        cmd="printf 'simulation ended\\n'"
        [stages.sim.checks]
        pass_regex="PASS"
        require_pass=true
    """, files={"rtl/t.v": "module t(); endmodule"})
    cfg = ff.load_config(cfg_path)
    r = ff.run_stage("sim", cfg)
    assert r["status"] == "fail"
    assert "required pass_regex not seen" in r["checks"]["reasons"]


def test_stage_timeout_returns_timeout_status(tmp_path):
    cfg_path = write_cfg(tmp_path, f"""
        [project]
        top="t"
        src=["rtl/*.v"]
        [stages.sim]
        timeout_s=0.2
        cmd="{sys.executable} -c 'import time; time.sleep(2)'"
    """, files={"rtl/t.v": "module t(); endmodule"})
    cfg = ff.load_config(cfg_path)
    r = ff.run_stage("sim", cfg)
    assert r["status"] == "timeout"
    assert any("timed out" in w for w in r.get("warnings", []))


def test_path_probe_blocks_missing_required_file(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        [stages.signoff]
        path_probes=["missing/config.mk"]
        cmd="echo signoff"
    """, files={"rtl/t.v": "module t(); endmodule"})
    cfg = ff.load_config(cfg_path)
    r = ff.resolve_stage("signoff", cfg)
    assert "blocked" in r
    assert "missing/config.mk" in r["blocked"]


# ---------------- built-in source audit -------------------------------------

def test_source_audit_flags_cummings_traps(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="bad"
        src=["rtl/*.sv"]
    """, files={"rtl/bad.sv": """
        module bad(input logic clk, input logic [1:0] sel, output logic y);
          // synopsys full_case parallel_case
          always_ff @(posedge clk) begin
            y = sel[0];
          end
          always_comb begin
            unique case (sel)
              2'b00: y = 1'b0;
            endcase
          end
          initial y = 1'b0;
          assign #1 y = sel[1];
        endmodule
    """})
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("audit", cfg)
    rules = {f["rule"] for f in out["findings"]}
    assert out["status"] == "pass"
    assert "full_parallel_case" in rules
    assert "blocking_in_clocked_block" in rules
    assert "case_without_default" in rules
    assert "delay_control_in_rtl" in rules
    assert out["summary"]["high"] >= 2


def test_source_audit_vhdl_rules(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="bad"
        src=["rtl/*.vhd"]
    """, files={"rtl/bad.vhd": """
        library ieee;
        use ieee.std_logic_arith.all;
        entity bad is end;
        architecture rtl of bad is
        begin
          process(all)
          begin
            y <= a after 1 ns;
            case s is
              when "00" => y <= '0';
            end case;
          end process;
        end;
    """})
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("audit", cfg)
    rules = {f["rule"] for f in out["findings"]}
    assert "vhdl_after_in_rtl" in rules
    assert "deprecated_vhdl_arithmetic_package" in rules
    assert "case_without_default" in rules


def test_source_audit_dry_run_lists_files(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="ok"
        src=["rtl/*.v"]
    """, files={"rtl/ok.v": "module ok; endmodule"})
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("audit", cfg, print_cmd=True)
    assert out["status"] == "dry-run"
    assert out["tool"] == "built-in-source-audit"
    assert out["files"] == ["rtl/ok.v"]
    # v1.0+ contract: engine disclosure is on every audit envelope.
    assert out["audit_engine"] == "regex"


def test_source_audit_engine_field_default_regex(tmp_path):
    """No --experimental-ast → audit_engine == 'regex' on real runs too."""
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="ok"
        src=["rtl/*.v"]
    """, files={"rtl/ok.v": "module ok; endmodule"})
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("audit", cfg)
    assert out["audit_engine"] == "regex"


def test_source_audit_engine_field_when_flag_no_verible(tmp_path, monkeypatch):
    """Flag set, Verible not installed → silent degrade, engine stays regex."""
    from logicpilot_flow import verible_client
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: None)
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="ok"
        src=["rtl/*.v"]
    """, files={"rtl/ok.v": "module ok; endmodule"})
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("audit", cfg, experimental={"ast"})
    assert out["audit_engine"] == "regex"



# ---------------- power reporting ------------------------------------------------

def test_build_vars_exposes_activity_and_power_sections(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
        clock_mhz=100
        [activity]
        saif_file="build/sim.saif"
        instance="dut"
        [power]
        total_budget_w=1.5
        temperature_c=85
    """, files={"rtl/t.v": "module t(); endmodule"})
    cfg = ff.load_config(cfg_path)
    v = ff.build_vars(cfg)
    assert v["saif_file"].endswith("/build/sim.saif")
    assert v["activity_file"].endswith("/build/sim.saif")
    assert v["activity_instance"] == "dut"
    assert v["total_budget_w"] == "1.5"
    assert v["temperature_c"] == "85"


def test_power_warnings_flags_vectorless_and_budget():
    metrics = {"total_power_w": 2.0}
    cfg = {"power": {"total_budget_w": 1.5}}
    warnings = ff.power_warnings("POWER_ACTIVITY: vectorless/default switching activity", metrics, cfg)
    assert any("vectorless" in w for w in warnings)
    assert any("exceeds budget" in w for w in warnings)


# ---------------- SystemVerilog verification-oriented audits ----------------

def test_source_audit_flags_sv_testbench_constructs_in_rtl(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="bad"
        src=["rtl/*.sv"]
    """, files={"rtl/bad.sv": """
        module bad(input logic clk);
          class Packet; rand bit [3:0] id; endclass
          covergroup cg; coverpoint id; endgroup
          import "DPI-C" function int c_model(int x);
        endmodule
    """})
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("audit", cfg)
    rules = {f["rule"] for f in out["findings"]}
    assert "sv_tb_construct_in_rtl" in rules
    assert "sv_randomization_in_rtl" in rules
    assert "dpi_in_rtl" in rules


def test_testbench_audit_flags_waveform_only_random_tb(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="dut"
        src=["rtl/*.sv"]
        tb=["tb/*.sv"]
    """, files={
        "rtl/dut.sv": "module dut(input logic clk); endmodule",
        "tb/dut_tb.sv": """
            module dut_tb;
              logic clk, a;
              initial begin
                a = $random;
                #0 a = 1'b0;
                $dumpvars;
              end
            endmodule
        """
    })
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("tb-audit", cfg)
    rules = {f["rule"] for f in out["findings"]}
    assert out["stage"] == "tb-audit"
    assert "tb_no_visible_self_check" in rules
    assert "tb_legacy_random" in rules
    assert "tb_zero_delay_race_fix" in rules


def test_testbench_audit_accepts_selfchecking_seeded_tb(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="dut"
        src=["rtl/*.sv"]
        tb=["tb/*.sv"]
    """, files={
        "rtl/dut.sv": "module dut(input logic clk); endmodule",
        "tb/dut_tb.sv": """
            module dut_tb;
              int seed = 32'h1234;
              initial begin
                $display("seed=%0d", seed);
                assert (1) else $fatal("mismatch");
                $display("TEST_PASS");
                $finish;
              end
            endmodule
        """
    })
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("tb-audit", cfg)
    rules = {f["rule"] for f in out["findings"]}
    assert "tb_no_visible_self_check" not in rules
    assert "tb_no_pass_marker" not in rules
    assert "tb_no_finish_or_objection" not in rules


def test_parse_coverage_metrics_and_goal_warning():
    log = """
      Functional Coverage: 82.5%
      Code Coverage: 91.0%
      Assertion Coverage: 100%
    """
    m = ff.parse_metrics(log, {})
    assert m["functional_coverage_pct"] == 82.5
    assert m["code_coverage_pct"] == 91.0
    warnings = ff.verification_warnings(log, m, {"verification": {"coverage_goal_pct": 90}})
    assert any("functional_coverage_pct" in w for w in warnings)


def test_builtin_report_summarizes_existing_logs(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="dut"
        src=["rtl/*.sv"]
        build_dir="build"
    """, files={"rtl/dut.sv": "module dut; endmodule"})
    log_dir = tmp_path / "build" / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "sim.log").write_text("Functional Coverage: 95%\nTEST_PASS\n")
    (log_dir / "synth.log").write_text("SB_LUT4   7\nWorst Negative Slack (WNS): 0.1 ns\n")
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("report", cfg)
    assert out["stage"] == "report"
    stages = {r["stage"] for r in out["reports"]}
    assert {"sim", "synth"} <= stages
    metrics = {r["stage"]: r["metrics"] for r in out["reports"]}
    assert metrics["sim"]["functional_coverage_pct"] == 95.0
    assert metrics["synth"]["luts"] == 7


def test_source_audit_flags_sv_declaration_and_type_modeling_risks(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="bad"
        src=["rtl/*.sv"]
    """, files={"rtl/bad.sv": """
        import types_pkg::*;
        typedef enum {IDLE, BUSY} state_e;

        module bad(input logic clk);
          bit flag;
          state_e state_q;
          initial begin
            $cast(state_q, 0);
          end
          always_comb begin
            #1 flag = 1'b1;
          end
        endmodule
    """})
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("audit", cfg)
    rules = {f["rule"] for f in out["findings"]}
    assert "unit_scope_package_import" in rules
    assert "unit_scope_declaration" in rules
    assert "enum_without_explicit_base" in rules
    assert "two_state_rtl_signal" in rules
    assert "dynamic_cast_in_rtl" in rules
    assert "timing_control_in_always_comb" in rules


def test_source_audit_flags_interface_modeling_risks(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="user"
        src=["rtl/*.sv"]
    """, files={"rtl/user.sv": """
        timeunit 1ns; timeprecision 1ps;
        interface bus_if(input logic clk);
          logic valid;
          task drive(input logic v);
            valid = v;
          endtask
          clocking cb @(posedge clk);
            output valid;
          endclocking
        endinterface

        module user(bus_if b);
        endmodule
    """})
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("audit", cfg)
    rules = {f["rule"] for f in out["findings"]}
    assert "interface_without_modport" in rules
    assert "interface_method_not_automatic" in rules
    assert "clocking_block_in_rtl_interface" in rules


def test_testbench_audit_flags_timeunit_and_interface_role_gaps(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="dut"
        src=["rtl/*.sv"]
        tb=["tb/*.sv"]
    """, files={
        "rtl/dut.sv": "module dut(input logic clk); endmodule",
        "tb/dut_tb.sv": """
            interface dut_if(input logic clk);
              logic req;
              clocking cb @(posedge clk);
                output req;
              endclocking
            endinterface

            module dut_tb;
              logic clk;
              dut_if vif(clk);
              initial begin
                assert (1) else $fatal("mismatch");
                $display("TEST_PASS");
                $finish;
              end
            endmodule
        """
    })
    cfg = ff.load_config(cfg_path)
    out = ff.run_stage("tb-audit", cfg)
    rules = {f["rule"] for f in out["findings"]}
    assert "tb_time_unit_unspecified" in rules
    assert "tb_interface_without_modport" in rules
    assert "tb_interface_without_clocking_block" not in rules


# --- security: untrusted flow.toml placeholder values in safe-preset mode ----

def _safe_cfg(tmp_path, top, *, safe):
    """Build a config on a real shipped preset (so safe-preset mode can locate
    it next to logicpilot.py) with the given top, returning the loaded cfg."""
    body = f"""
        [toolchain]
        preset = "yosys-nextpnr"
        [project]
        top = {top!r}
        src = ["rtl/*.v"]
    """
    cfg_path = write_cfg(tmp_path, body, files={"rtl/a.v": "module a; endmodule\n"})
    return ff.load_config(cfg_path, safe_preset_only=safe)


def test_safe_mode_rejects_shell_metachar_in_placeholder(tmp_path):
    # A quote+';' lets a value break out of yosys -p '...': must be refused.
    cfg = _safe_cfg(tmp_path, "x'; touch PWNED; echo 'y", safe=True)
    with pytest.raises(SystemExit):
        ff.build_vars(cfg)


def test_safe_mode_rejects_command_substitution_in_placeholder(tmp_path):
    cfg = _safe_cfg(tmp_path, "$(touch PWNED)", safe=True)
    with pytest.raises(SystemExit):
        ff.build_vars(cfg)


def test_safe_mode_rejects_metachar_in_source_path(tmp_path):
    # {src} is interpolated inside the yosys -p '...' single quotes in shipped
    # presets, so a metacharacter in a (literal, non-matching) src entry must be
    # rejected even though it is shlex-quoted as a standalone word.
    body = """
        [toolchain]
        preset = "yosys-nextpnr"
        [project]
        top = "a"
        src = ["a; touch PWNED #.v"]
    """
    cfg_path = write_cfg(tmp_path, body)
    cfg = ff.load_config(cfg_path, safe_preset_only=True)
    with pytest.raises(SystemExit):
        ff.build_vars(cfg)


def test_non_safe_mode_allows_arbitrary_placeholder(tmp_path):
    # Running your OWN project (no safe mode) is unrestricted by design.
    cfg = _safe_cfg(tmp_path, "x'; echo hi", safe=False)
    v = ff.build_vars(cfg)
    assert v["top"] == "x'; echo hi"


def test_safe_mode_allows_normal_identifiers(tmp_path):
    cfg = _safe_cfg(tmp_path, "fifo_ctrl", safe=True)
    v = ff.build_vars(cfg)
    assert v["top"] == "fifo_ctrl"


def test_tcl_word_escapes_both_braces():
    out = ff._tcl_word("a{b}c")
    assert out == "{a\\{b\\}c}"


# --- run_all includes the built-in audit/tb-audit/report stages --------------

def test_all_includes_builtin_stages_by_default(tmp_path):
    cfg = cfg_with_preset(tmp_path, """
        [toolchain]
        preset = "p"
        [project]
        top = "m"
        src = ["rtl/m.v"]
    """, files={"rtl/m.v": "module m; endmodule\n"})
    order = ff.run_all(cfg, print_cmd=True)["pipeline"]
    # v0.6+: plan-check goes first (at the head of STAGE_ORDER), then
    # audit + tb-audit. Report stays last. The exact head triplet is part
    # of the v0.6 deprecation cycle contract.
    assert order[0] == "plan-check"
    assert order[1] == "audit"
    assert order[2] == "tb-audit"
    assert order[-1] == "report"
    assert "sim" in order


def test_all_skip_builtin_opts_out(tmp_path):
    cfg = cfg_with_preset(tmp_path, """
        [toolchain]
        preset = "p"
        [project]
        top = "m"
        src = ["rtl/m.v"]
        [pipeline]
        skip_builtin = true
    """, files={"rtl/m.v": "module m; endmodule\n"})
    order = ff.run_all(cfg, print_cmd=True)["pipeline"]
    assert "audit" not in order and "tb-audit" not in order and "report" not in order


# --- --jobs N plumbing (Stage DAG scheduler, post-v1.0) ----------------------

def test_run_all_jobs_1_keeps_sequential_envelope(tmp_path):
    """jobs=1 → no 'scheduler' field appears (back-compat with v1.0)."""
    cfg = cfg_with_preset(tmp_path, """
        [toolchain]
        preset = "p"
        [project]
        top = "m"
        src = ["rtl/m.v"]
    """, files={"rtl/m.v": "module m; endmodule\n"})
    out = ff.run_all(cfg, print_cmd=True, jobs=1)
    assert "scheduler" not in out
    assert "pipeline" in out and "results" in out


def test_run_all_jobs_2_emits_scheduler_envelope(tmp_path):
    """jobs>1 → top-level 'scheduler' object with jobs + peak_running."""
    cfg = cfg_with_preset(tmp_path, """
        [toolchain]
        preset = "p"
        [project]
        top = "m"
        src = ["rtl/m.v"]
    """, files={"rtl/m.v": "module m; endmodule\n"})
    out = ff.run_all(cfg, print_cmd=True, jobs=2)
    assert "scheduler" in out
    assert out["scheduler"]["jobs"] == 2
    assert "peak_running" in out["scheduler"]


def test_run_all_jobs_cycle_detection_falls_back_sequential(tmp_path):
    """A depends_on cycle MUST surface a warning + fall back, not crash."""
    cfg = cfg_with_preset(tmp_path, """
        [toolchain]
        preset = "p"
        [project]
        top = "m"
        src = ["rtl/m.v"]
        [stages.sim]
        depends_on = ["lint"]
        [stages.lint]
        candidates = []
        depends_on = ["sim"]
    """, files={"rtl/m.v": "module m; endmodule\n"})
    out = ff.run_all(cfg, print_cmd=True, jobs=4)
    # Cycle is detected; scheduler degrades to sequential and reports it.
    assert any("cycle" in w for w in out.get("warnings", []))


def test_all_declared_pipeline_gets_builtins_injected(tmp_path):
    cfg = cfg_with_preset(tmp_path, """
        [toolchain]
        preset = "p"
        [project]
        top = "m"
        src = ["rtl/m.v"]
        [pipeline]
        order = ["sim"]
    """, files={"rtl/m.v": "module m; endmodule\n"})
    order = ff.run_all(cfg, print_cmd=True)["pipeline"]
    assert order[0] == "audit" and order[1] == "tb-audit"
    assert order[-1] == "report"
    assert "sim" in order


# --- machine-local trust gate (manual /lp-* commands) ------------------------

def test_project_is_trusted_via_env(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGICPILOT_TRUST_FILE", raising=False)
    monkeypatch.setenv("LOGICPILOT_TRUST_PROJECT", "1")
    assert ff._project_is_trusted(tmp_path) is True
    monkeypatch.delenv("LOGICPILOT_TRUST_PROJECT", raising=False)
    monkeypatch.setenv("LOGICPILOT_TRUST_FILE", str(tmp_path / "nope"))
    assert ff._project_is_trusted(tmp_path) is False


def test_project_is_trusted_via_file(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGICPILOT_TRUST_PROJECT", raising=False)
    tf = tmp_path / "trusted"
    proj = tmp_path / "proj"
    proj.mkdir()
    tf.write_text(f"# comment\n{proj}\n")
    monkeypatch.setenv("LOGICPILOT_TRUST_FILE", str(tf))
    assert ff._project_is_trusted(proj) is True
    assert ff._project_is_trusted(tmp_path / "other") is False


def test_gate_untrusted_runs_safe_and_notes(tmp_path, monkeypatch, capsys):
    # An untrusted project run with --gate-untrusted falls back to safe mode and
    # surfaces a note telling the user how to trust it.
    monkeypatch.delenv("LOGICPILOT_TRUST_PROJECT", raising=False)
    monkeypatch.setenv("LOGICPILOT_TRUST_FILE", str(tmp_path / "empty-trust"))
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "a.v").write_text("module a; endmodule\n")
    (tmp_path / "flow.toml").write_text(
        '[toolchain]\npreset="yosys-nextpnr"\n[project]\ntop="a"\nsrc=["rtl/*.v"]\n'
    )
    rc = ff.main(["synth", "--config", str(tmp_path / "flow.toml"),
                  "--gate-untrusted", "--print-cmd"])
    out = capsys.readouterr().out
    assert "safe_mode_note" in out
    assert rc in (0, 1)  # blocked (no yosys) or dry-run; either is fine here


def test_gate_untrusted_trusted_runs_full(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LOGICPILOT_TRUST_FILE", raising=False)
    monkeypatch.setenv("LOGICPILOT_TRUST_PROJECT", "1")
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "a.v").write_text("module a; endmodule\n")
    (tmp_path / "flow.toml").write_text(
        '[toolchain]\npreset="yosys-nextpnr"\n[project]\ntop="a"\nsrc=["rtl/*.v"]\n'
    )
    ff.main(["synth", "--config", str(tmp_path / "flow.toml"),
             "--gate-untrusted", "--print-cmd"])
    out = capsys.readouterr().out
    assert "safe_mode_note" not in out


# --- safe-preset path boundary ------------------------------------------------

def test_safe_preset_rejects_src_outside_project_root(tmp_path):
    outside = tmp_path.parent / "outside_safe_src.v"
    outside.write_text("module outside_safe_src; endmodule\n")
    cfg_path = write_cfg(tmp_path, f"""
        [project]
        top = "m"
        src = ["../{outside.name}"]
    """)
    cfg = ff.load_config(cfg_path, safe_preset_only=True)
    with pytest.raises(SystemExit) as exc:
        ff.build_vars(cfg)
    assert "outside project root" in str(exc.value)


def test_safe_preset_rejects_build_dir_outside_project_root(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top = "m"
        src = ["rtl/m.v"]
        build_dir = "../outside_build"
    """, files={"rtl/m.v": "module m; endmodule\n"})
    cfg = ff.load_config(cfg_path, safe_preset_only=True)
    with pytest.raises(SystemExit) as exc:
        ff.build_vars(cfg)
    assert "project.build_dir" in str(exc.value)


def test_safe_preset_rejects_constraints_outside_project_root(tmp_path):
    outside = tmp_path.parent / "outside_constraints.xdc"
    outside.write_text("create_clock -period 10 [get_ports clk]\n")
    cfg_path = write_cfg(tmp_path, f"""
        [project]
        top = "m"
        src = ["rtl/m.v"]
        constraints = "../{outside.name}"
    """, files={"rtl/m.v": "module m; endmodule\n"})
    cfg = ff.load_config(cfg_path, safe_preset_only=True)
    with pytest.raises(SystemExit) as exc:
        ff.build_vars(cfg)
    assert "project.constraints" in str(exc.value)


# --- regression: latch false-positive on real yosys/ice40 output ---------
# A clean design synthesized for ice40 still makes yosys print DLATCH noise:
# the PROC_DLATCH *pass name* and the ice40 latches_map.v library modules
# ($_DLATCH_N_/$_DLATCH_P_). None of these mean the design has a latch. The
# earlier scanner matched them and warned on every ice40 run; this fixture is
# the exact noise from `yosys synth_ice40` on a latch-free register.
_ICE40_CLEAN_LATCH_NOISE = textwrap.dedent("""\
    2.3.8. Executing PROC_DLATCH pass (convert process syncs to latches).
    Generating RTLIL representation for module `\\$_DLATCH_N_'.
    Generating RTLIL representation for module `\\$_DLATCH_P_'.
    Using template \\$_DLATCH_P_ for cells of type $_DLATCH_P_.
    === clean ===
       SB_LUT4   9
       SB_DFFER  8
""")

# A real inferred latch instead prints an explicit per-signal message.
_ICE40_REAL_LATCH = (
    "Latch inferred for signal `\\latchy.\\q' from process "
    "`\\latchy.$proc$latch.v:2$1': $auto$proc_dlatch.cc:427:proc_dlatch$439"
)


def test_clean_ice40_synth_does_not_false_flag_latch():
    # The decisive regression: clean ice40 synthesis output must stay silent
    # even though it contains $_DLATCH_P_/PROC_DLATCH library/pass noise.
    assert ff.quality_warnings(_ICE40_CLEAN_LATCH_NOISE) == []


def test_real_inferred_latch_is_still_flagged():
    w = ff.quality_warnings(_ICE40_REAL_LATCH)
    assert any("latch" in x.lower() for x in w)


def test_real_inferred_latch_flagged_even_amid_library_noise():
    # Real inference message buried in the same library noise must still warn.
    combined = _ICE40_CLEAN_LATCH_NOISE + "\n" + _ICE40_REAL_LATCH + "\n"
    w = ff.quality_warnings(combined)
    assert any("latch" in x.lower() for x in w)


# --- regression: power_assumptions NameError after module split ----------
def test_power_assumptions_runs_without_explicit_variables(tmp_path):
    # Reproduces the v0.2 split regression where power_assumptions referenced
    # build_vars without importing it -> NameError on every power run.
    cfg_path = write_cfg(tmp_path, """
        [project]
        top = "m"
        src = ["rtl/m.v"]
        clock_mhz = 50
    """, files={"rtl/m.v": "module m; endmodule\n"})
    cfg = ff.load_config(cfg_path)
    out = ff.power_assumptions("vectorless default switching", cfg)
    assert out["activity_source"] == "vectorless-default"
    assert out["confidence"] == "early_estimate"


def test_power_assumptions_accepts_precomputed_variables(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top = "m"
        src = ["rtl/m.v"]
    """, files={"rtl/m.v": "module m; endmodule\n"})
    cfg = ff.load_config(cfg_path)
    variables = ff.build_vars(cfg)
    out = ff.power_assumptions("no activity annotated", cfg, variables)
    assert out["activity_source"] == "vectorless-default"


def test_power_assumptions_saif_annotated(tmp_path):
    """Explicit [activity].saif_file → activity_source='saif-annotated'."""
    cfg_path = write_cfg(tmp_path, """
        [project]
        top = "m"
        src = ["rtl/m.v"]
        [activity]
        saif_file = "build/activity.saif"
    """, files={"rtl/m.v": "module m; endmodule\n"})
    cfg = ff.load_config(cfg_path)
    out = ff.power_assumptions("", cfg)
    assert out["activity_source"] == "saif-annotated"
    assert out["confidence"] == "high"


def test_power_assumptions_vcd_annotated(tmp_path):
    """VCD without SAIF → activity_source='vcd-annotated', confidence='high'."""
    cfg_path = write_cfg(tmp_path, """
        [project]
        top = "m"
        src = ["rtl/m.v"]
        [activity]
        vcd_file = "build/sim.vcd"
    """, files={"rtl/m.v": "module m; endmodule\n"})
    cfg = ff.load_config(cfg_path)
    out = ff.power_assumptions("", cfg)
    assert out["activity_source"] == "vcd-annotated"
    assert out["confidence"] == "high"


def test_power_assumptions_manual_override(tmp_path):
    """No activity file but [activity].toggle_rate → manual-override."""
    cfg_path = write_cfg(tmp_path, """
        [project]
        top = "m"
        src = ["rtl/m.v"]
        [activity]
        toggle_rate = 0.2
    """, files={"rtl/m.v": "module m; endmodule\n"})
    cfg = ff.load_config(cfg_path)
    out = ff.power_assumptions("", cfg)
    assert out["activity_source"] == "manual-override"
    assert out["confidence"] == "early_estimate"


def test_power_activity_sources_enum_is_closed():
    """Drift detector: enum values are part of the JSON contract."""
    from logicpilot_flow.diagnostics import POWER_ACTIVITY_SOURCES
    assert set(POWER_ACTIVITY_SOURCES) == {
        "saif-annotated", "vcd-annotated", "vectorless-default",
        "manual-override", "unknown",
    }


# ---------------- safe-mode hardening ---------------------------------------

def test_safe_mode_rejects_parent_glob_before_expansion(tmp_path):
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="t"
        src=["../*.v"]
    """)
    cfg = ff.load_config(cfg_path, safe_preset_only=True)
    with pytest.raises(SystemExit):
        ff.build_vars(cfg)


def test_safe_mode_glob_limit_env(tmp_path, monkeypatch):
    files = {f"rtl/t{i}.v": "module t; endmodule" for i in range(5)}
    cfg_path = write_cfg(tmp_path, """
        [project]
        top="t"
        src=["rtl/*.v"]
    """, files=files)
    monkeypatch.setenv("LOGICPILOT_MAX_GLOB_MATCHES", "2")
    cfg = ff.load_config(cfg_path, safe_preset_only=True)
    src_words = ff.build_vars(cfg)["src"].split()
    assert len(src_words) == 2
