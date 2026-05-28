"""Tests for sysinfo (v0.9 §6.3.1) — stdlib-only RAM/CPU detection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.sysinfo import (  # noqa: E402
    available_mem_gb,
    cpu_count,
)


def test_cpu_count_is_at_least_one() -> None:
    n = cpu_count()
    assert isinstance(n, int)
    assert n >= 1


def test_available_mem_gb_is_positive_finite_on_supported_platforms() -> None:
    """On the 3 supported platforms (linux/macos/win32) we should see a
    real number. CI runs Ubuntu + macOS + Windows so this is the only
    cross-platform smoke we need."""
    g = available_mem_gb()
    assert isinstance(g, float)
    if sys.platform.startswith(("linux", "darwin", "win")):
        # Could be inf if the platform-specific path failed (e.g. sandbox
        # blocked /proc), but on a real CI runner it must be finite.
        assert g > 0


def test_available_mem_gb_no_psutil_imported() -> None:
    """v0.9 zero-deps assertion: this module must not pull in psutil."""
    import logicpilot_flow.sysinfo  # noqa: F401
    assert "psutil" not in sys.modules
