"""Tests for the power stage (VCS SAIF → Vivado report_power)."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.power import run_power, _vcs_saif_cmd, _vivado_tcl


def _cfg(tmp_path: Path, saif_file: str = "", top: str = "top") -> dict:
    return {
        "_root": tmp_path,
        "project": {"top": top, "src": [], "tb": []},
        "toolchain": {"preset": "vivado"},
        "activity": {"saif_file": saif_file} if saif_file else {},
        "power": {},
    }


def _make_dcp(tmp_path: Path, top: str = "top") -> Path:
    build = tmp_path / "build"
    build.mkdir(exist_ok=True)
    dcp = build / f"{top}_impl.dcp"
    dcp.write_text("placeholder")
    return dcp


# ---------------------------------------------------------------------------
# Blocked cases
# ---------------------------------------------------------------------------

def test_blocked_no_vivado(tmp_path: Path) -> None:
    with patch("shutil.which", return_value=None):
        out = run_power(_cfg(tmp_path))
    assert out["status"] == "blocked"
    assert "vivado" in out["missing"]
    assert "install_hint" in out


def test_blocked_no_dcp(tmp_path: Path) -> None:
    with patch("shutil.which", side_effect=lambda b: "/usr/bin/vivado" if b == "vivado" else None):
        out = run_power(_cfg(tmp_path))
    assert out["status"] == "blocked"
    assert "missing_paths" in out
    assert "impl.dcp" in out["missing_paths"][0]


# ---------------------------------------------------------------------------
# Dry-run (print_cmd)
# ---------------------------------------------------------------------------

def test_print_cmd_with_vcs(tmp_path: Path) -> None:
    _make_dcp(tmp_path)

    def _which(b: str) -> str | None:
        return "/usr/bin/" + b if b in ("vivado", "vcs") else None

    with patch("shutil.which", side_effect=_which):
        out = run_power(_cfg(tmp_path), print_cmd=True)
    assert out["status"] == "dry-run"
    assert out["tool"] == "vcs+vivado"
    assert "vcs_cmd" in out
    assert "+saif=on" in out["vcs_cmd"]


def test_print_cmd_no_vcs_vectorless(tmp_path: Path) -> None:
    _make_dcp(tmp_path)

    def _which(b: str) -> str | None:
        return "/usr/bin/vivado" if b == "vivado" else None

    with patch("shutil.which", side_effect=_which):
        out = run_power(_cfg(tmp_path), print_cmd=True)
    assert out["status"] == "dry-run"
    assert out["tool"] == "vivado"
    assert "vectorless" in out["activity"]


def test_print_cmd_user_saif_skips_vcs(tmp_path: Path) -> None:
    _make_dcp(tmp_path)
    saif = tmp_path / "sim.saif"
    saif.write_text("saif_data")

    with patch("shutil.which", return_value="/usr/bin/vivado"):
        out = run_power(_cfg(tmp_path, saif_file=str(saif)), print_cmd=True)
    # User provided saif_file — goes straight to Vivado dry-run (no vcs_cmd)
    assert out["status"] == "dry-run"
    assert "vcs_cmd" not in out
    assert "saif" in out["activity"]


# ---------------------------------------------------------------------------
# TCL content
# ---------------------------------------------------------------------------

def test_vivado_tcl_with_saif(tmp_path: Path) -> None:
    from logicpilot_flow.variables import build_vars
    cfg = _cfg(tmp_path)
    variables = build_vars(cfg)
    saif = tmp_path / "build" / "power.saif"
    saif.parent.mkdir(exist_ok=True)
    saif.write_text("x")
    tcl = _vivado_tcl(variables, saif)
    assert "read_saif" in tcl
    assert "POWER_ACTIVITY: SAIF" in tcl
    assert "vectorless" not in tcl


def test_vivado_tcl_vectorless(tmp_path: Path) -> None:
    from logicpilot_flow.variables import build_vars
    cfg = _cfg(tmp_path)
    variables = build_vars(cfg)
    tcl = _vivado_tcl(variables, None)
    assert "vectorless" in tcl
    assert "read_saif" not in tcl


# ---------------------------------------------------------------------------
# VCS SAIF command
# ---------------------------------------------------------------------------

def test_vcs_saif_cmd_contains_saif_flags(tmp_path: Path) -> None:
    from logicpilot_flow.variables import build_vars
    cfg = _cfg(tmp_path)
    variables = build_vars(cfg)
    cmd = _vcs_saif_cmd(variables)
    assert "+saif=on" in cmd
    assert "+saif_file=" in cmd
    assert "+saif_scope=" in cmd
    assert "simv_power" in cmd
