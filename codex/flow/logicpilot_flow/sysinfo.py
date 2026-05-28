"""Platform-aware system info — RAM and CPU (v0.9 §6.3).

Implemented in stdlib only — explicitly REJECTS psutil to preserve the
"zero compiled Python dependencies" promise. psutil ships a C extension
that breaks the wheel matrix on musl, Apple Silicon, ARM Linux,
freshly-released Python versions etc.

Three platforms covered:
- Linux:   read /proc/meminfo, key 'MemAvailable'
- macOS:   parse `vm_stat` (free + inactive pages × pagesize)
- Windows: ctypes call to GlobalMemoryStatusEx via kernel32

Unknown platforms get float('inf') for memory (= "don't throttle") so
the scheduler degrades to non-protective behavior rather than crashing.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys


def available_mem_gb() -> float:
    """Return currently available RAM in GiB. On unsupported platforms
    return +inf so the caller treats it as 'no constraint'."""
    plat = sys.platform
    if plat.startswith("linux"):
        return _linux_meminfo_gb()
    if plat == "darwin":
        return _macos_vm_stat_gb()
    if plat == "win32":
        return _windows_global_memory_gb()
    return float("inf")


def cpu_count() -> int:
    """Return logical CPU count, defaulting to 1 if undetectable."""
    return os.cpu_count() or 1


# --- Linux -----------------------------------------------------------------

_MEM_AVAILABLE_RE = re.compile(r"^MemAvailable:\s+(\d+)\s*kB", re.M)


def _linux_meminfo_gb() -> float:
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            text = f.read()
    except OSError:
        return float("inf")
    m = _MEM_AVAILABLE_RE.search(text)
    if not m:
        return float("inf")
    kb = int(m.group(1))
    return kb / 1024 / 1024  # KB → MB → GB


# --- macOS -----------------------------------------------------------------

_VM_STAT_PAGE_SIZE_RE = re.compile(r"page size of (\d+)")
_VM_STAT_FREE_RE = re.compile(r"Pages free:\s+(\d+)")
_VM_STAT_INACTIVE_RE = re.compile(r"Pages inactive:\s+(\d+)")
_VM_STAT_SPECULATIVE_RE = re.compile(r"Pages speculative:\s+(\d+)")


def _macos_vm_stat_gb() -> float:
    try:
        out = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=5,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return float("inf")
    page_size = 4096
    m = _VM_STAT_PAGE_SIZE_RE.search(out)
    if m:
        page_size = int(m.group(1))
    free = _VM_STAT_FREE_RE.search(out)
    inactive = _VM_STAT_INACTIVE_RE.search(out)
    speculative = _VM_STAT_SPECULATIVE_RE.search(out)
    pages = 0
    if free:
        pages += int(free.group(1))
    if inactive:
        pages += int(inactive.group(1))
    if speculative:
        pages += int(speculative.group(1))
    if pages == 0:
        return float("inf")
    return pages * page_size / 1024 / 1024 / 1024  # → GB


# --- Windows ---------------------------------------------------------------

def _windows_global_memory_gb() -> float:
    try:
        import ctypes
    except ImportError:  # pragma: no cover - ctypes ships with cpython
        return float("inf")

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        m = MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    except (AttributeError, OSError):  # not on Windows / API missing
        return float("inf")
    return m.ullAvailPhys / 1024 / 1024 / 1024
