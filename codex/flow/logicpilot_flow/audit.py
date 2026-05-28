"""LogicPilot hardware flow internals."""
from __future__ import annotations


import re
from pathlib import Path

from .config import _expand_globs

AUDIT_SOURCE_EXTS = {".v", ".vh", ".sv", ".svh", ".vhd", ".vhdl"}

TB_SOURCE_EXTS = {".v", ".vh", ".sv", ".svh", ".vhd", ".vhdl", ".py"}

def _audit_add(findings: list[dict], severity: str, rule: str,
               path: Path, root: Path, line: int, message: str) -> None:
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)
    findings.append({
        "severity": severity,
        "rule": rule,
        "file": rel,
        "line": line,
        "message": message,
    })

def _strip_comments_for_audit(text: str) -> str:
    """Remove comments for heuristic scans while preserving line count.

    Pragmas such as full_case/parallel_case are intentionally scanned on the raw
    text elsewhere because they usually appear in comments.
    """
    # Replace block comments with the same number of newlines, then remove line comments.
    def block_repl(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")
    text = re.sub(r"/\*.*?\*/", block_repl, text, flags=re.S)
    return re.sub(r"//.*", "", text)

def _iter_audit_source_files(cfg: dict) -> list[Path]:
    root: Path = cfg["_root"]
    proj = cfg.get("project", {})
    patterns = proj.get("src_ordered", proj.get("src", []))
    files = []
    for f in _expand_globs(patterns, root):
        p = Path(f)
        if not p.is_absolute():
            p = root / p
        if p.exists() and p.suffix.lower() in AUDIT_SOURCE_EXTS:
            files.append(p.resolve())
    # Preserve order but deduplicate.
    seen, out = set(), []
    for p in files:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out

def _scan_case_defaults(path: Path, root: Path, lines: list[str], findings: list[dict], *, vhdl: bool = False) -> None:
    if vhdl:
        start_pat = re.compile(r"\bcase\b.*\bis\b", re.I)
        end_pat = re.compile(r"\bend\s+case\b", re.I)
        default_pat = re.compile(r"\bwhen\s+others\b", re.I)
    else:
        start_pat = re.compile(r"\b(?:unique\s+|priority\s+)?case[zx]?\s*\(", re.I)
        end_pat = re.compile(r"\bendcase\b", re.I)
        default_pat = re.compile(r"\bdefault\b", re.I)

    i = 0
    while i < len(lines):
        if start_pat.search(lines[i]):
            start = i
            block = [lines[i]]
            i += 1
            while i < len(lines):
                block.append(lines[i])
                if end_pat.search(lines[i]):
                    break
                i += 1
            if not any(default_pat.search(x) for x in block):
                _audit_add(
                    findings, "medium", "case_without_default", path, root, start + 1,
                    "case statement has no visible default/others branch; review latch/illegal-state behavior"
                )
        i += 1

def _scan_always_assignment_style(path: Path, root: Path, lines: list[str], findings: list[dict]) -> None:
    """Heuristic, not a parser: find obvious assignment-style mismatches."""
    start_pat = re.compile(r"\balways(?:_ff|_comb|_latch)?\b|^\s*always\s*@", re.I)
    edge_pat = re.compile(r"\balways_ff\b|@\s*\([^)]*(?:posedge|negedge)", re.I)
    comb_pat = re.compile(r"\balways_comb\b|@\s*\(\s*\*\s*\)|@\s*\*", re.I)
    blocking_assign = re.compile(r"^\s*(?!assign\b|parameter\b|localparam\b)([A-Za-z_][\w$.\[\]:]*)\s*=(?!=)")
    nonblocking_assign = re.compile(r"<=")

    i = 0
    while i < len(lines):
        line = lines[i]
        if not start_pat.search(line):
            i += 1
            continue

        block_kind = "edge" if edge_pat.search(line) else "comb" if comb_pat.search(line) else "other"
        begin_end_depth = 0
        block_lines: list[tuple[int, str]] = []
        # Scan until the next obvious procedural block if begin/end structure is absent.
        j = i
        while j < len(lines):
            cur = lines[j]
            if j > i and begin_end_depth <= 0 and start_pat.search(cur):
                break
            block_lines.append((j + 1, cur))
            begin_end_depth += len(re.findall(r"\bbegin\b", cur))
            begin_end_depth -= len(re.findall(r"\bend\b", cur))
            if j > i and begin_end_depth <= 0 and re.search(r"\bend\b", cur):
                break
            j += 1

        if block_kind == "edge":
            for lineno, cur in block_lines[1:]:
                if blocking_assign.search(cur):
                    _audit_add(
                        findings, "high", "blocking_in_clocked_block", path, root, lineno,
                        "blocking assignment in an edge-triggered block; use nonblocking <= for sequential RTL"
                    )
                    break
        elif block_kind == "comb":
            for lineno, cur in block_lines[1:]:
                if nonblocking_assign.search(cur):
                    _audit_add(
                        findings, "medium", "nonblocking_in_comb_block", path, root, lineno,
                        "nonblocking assignment in combinational block; use blocking = for combinational RTL"
                    )
                    break
        else:
            # Plain always @(a or b) comb blocks are easy to get wrong.
            if re.search(r"@\s*\(", line) and not re.search(r"posedge|negedge|\*|all", line, re.I):
                _audit_add(
                    findings, "medium", "manual_sensitivity_list", path, root, i + 1,
                    "manual combinational sensitivity list; prefer always_comb/always @* to avoid sim/synth mismatch"
                )
        i = max(j, i + 1)

def _scan_top_level_sv_declarations(path: Path, root: Path, lines: list[str], findings: list[dict]) -> None:
    """Flag declarations that live in $unit instead of a package/module/interface.

    This is a style and compile-order risk check, not a parser. It keeps the
    rule narrow: shared declarations should be in packages; source-order import
    tricks should be intentional.
    """
    depth = 0
    decl_pat = re.compile(
        r"^\s*(?:typedef|parameter|localparam|task|function|"
        r"(?:var\s+)?(?:logic|bit|wire|reg|byte|shortint|int|longint|integer|time)\b|"
        r"(?:typedef\s+)?(?:enum|struct|union)\b)",
        re.I,
    )
    start_pat = re.compile(r"^\s*(module|interface|package|program|primitive)\b", re.I)
    end_pat = re.compile(r"^\s*end(module|interface|package|program|primitive)\b", re.I)

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue

        if end_pat.search(line):
            depth = max(0, depth - 1)

        if depth == 0:
            if re.search(r"^\s*import\s+\w+(?:::\w+|::\*)\s*;", line, re.I):
                sev = "medium" if "::" in line and "*" in line else "low"
                _audit_add(
                    findings, sev, "unit_scope_package_import", path, root, idx,
                    "package import at $unit scope creates file-order dependence; prefer package-qualified names or controlled src_ordered"
                )
            elif decl_pat.search(line):
                _audit_add(
                    findings, "medium", "unit_scope_declaration", path, root, idx,
                    "declaration at $unit scope is fragile across compile units; put shared typedefs/parameters/functions/tasks in a package"
                )

        if start_pat.search(line) and not end_pat.search(line):
            depth += 1

def _scan_sv_type_and_modeling_style(path: Path, root: Path, raw: str, lines: list[str], findings: list[dict]) -> None:
    """SystemVerilog design-modeling heuristics from the stricter RTL style guide."""
    suffix = path.suffix.lower()
    is_sv = suffix in {".sv", ".svh"}
    is_verilog_family = suffix in {".v", ".vh", ".sv", ".svh"}
    raw_no_comments = "\n".join(lines)

    if is_verilog_family and re.search(r"\bmodule\b", raw_no_comments) and not re.search(r"`\s*default_nettype\s+none\b", raw, re.I):
        _audit_add(
            findings, "low", "implicit_nettype_not_disabled", path, root, 1,
            "`default_nettype none` not visible; implicit nets can hide typos and source-order declaration bugs"
        )

    if is_sv and re.search(r"\b(module|interface|program|package)\b", raw_no_comments) and not re.search(r"\btimeunit\b|`\s*timescale\b", raw, re.I):
        _audit_add(
            findings, "low", "sv_time_unit_unspecified", path, root, 1,
            "no visible timeunit/timeprecision or `timescale; simulation time semantics may depend on compile context"
        )

    whole = raw_no_comments

    # Interface-level checks. Interfaces in RTL source should declare roles
    # clearly and avoid testbench-only clocking blocks unless the file is routed
    # through the TB flow instead of the RTL source glob.
    for m in re.finditer(r"\binterface\s+([A-Za-z_][\w$]*)\b(?P<body>.*?)(?:\bendinterface\b|$)", whole, re.I | re.S):
        body = m.group("body")
        line_no = whole[:m.start()].count("\n") + 1
        if not re.search(r"\bmodport\b", body, re.I):
            _audit_add(
                findings, "medium", "interface_without_modport", path, root, line_no,
                "interface in RTL source has no visible modport; define per-role directions before connecting modules"
            )
        if re.search(r"\bclocking\b", body, re.I):
            _audit_add(
                findings, "high", "clocking_block_in_rtl_interface", path, root, line_no,
                "clocking block appears in RTL source interface; clocking blocks belong in testbench interfaces"
            )
        for tm in re.finditer(r"^\s*(task|function)\b(?![^;\n]*\bautomatic\b)", body, re.I | re.M):
            tm_line = line_no + body[:tm.start()].count("\n")
            _audit_add(
                findings, "medium", "interface_method_not_automatic", path, root, tm_line,
                "interface task/function used by RTL should be automatic to avoid shared static storage surprises"
            )

    for idx, line in enumerate(lines, 1):
        low = line.lower()

        # Default enum base is int: 32-bit, 2-state. That can mask X/reset
        # behavior and disconnect RTL sim from intended hardware encoding.
        m = re.search(r"\b(?:typedef\s+)?enum\s*([^{;]*)\{", line, re.I)
        if m:
            base = m.group(1)
            if not re.search(r"\b(logic|reg|wire)\b|\[[^]]+\]", base, re.I):
                _audit_add(
                    findings, "medium", "enum_without_explicit_base", path, root, idx,
                    "enum has no explicit packed 4-state base/width; prefer typedef enum logic [N-1:0] for RTL/FSM state"
                )
            elif re.search(r"\b(bit|byte|shortint|int|longint)\b", base, re.I) and not re.search(r"\blogic\b|\breg\b|\bwire\b", base, re.I):
                _audit_add(
                    findings, "low", "two_state_enum_base", path, root, idx,
                    "2-state enum base can mask X/reset behavior; use only when that simulation behavior is intentional"
                )

        if re.search(r"^\s*(?:input|output|inout|var|static|automatic)?\s*(?:bit|byte|shortint|longint)\b", line, re.I):
            _audit_add(
                findings, "low", "two_state_rtl_signal", path, root, idx,
                "2-state RTL signal type can hide X/Z behavior; prefer logic for hardware nets/registers unless intentionally modeling 2-state"
            )

        if re.search(r"\$cast\s*\(", line, re.I):
            _audit_add(
                findings, "medium", "dynamic_cast_in_rtl", path, root, idx,
                "$cast is a dynamic simulation check; use static casts or explicit decode in synthesizable RTL"
            )

        if re.search(r"\b(string|chandle|event|mailbox|semaphore)\b|\[[ \t]*\$[ \t]*\]|\bnew\s*\[", line, re.I):
            _audit_add(
                findings, "high", "dynamic_sv_object_in_rtl", path, root, idx,
                "dynamic SystemVerilog object/container appears in RTL source; keep dynamic data structures in TB/reference models"
            )

        if re.search(r"\bunion\b", line, re.I) and not re.search(r"\bpacked\b", line, re.I):
            _audit_add(
                findings, "medium", "nonpacked_union_in_rtl", path, root, idx,
                "non-packed union in RTL has limited synthesis portability; use packed union or explicit mux/storage"
            )

        if re.search(r"^\s*(task|function)\b(?![^;\n]*\bautomatic\b)", line, re.I):
            _audit_add(
                findings, "low", "task_function_not_automatic", path, root, idx,
                "task/function defaults to static storage; declare automatic when used as reusable combinational helper logic"
            )

        if re.search(r"\.\s*\*", line):
            _audit_add(
                findings, "low", "implicit_wildcard_port_connection", path, root, idx,
                "wildcard .* port connection depends on exact names; prefer explicit named connections for reusable RTL"
            )

        if re.search(r"\balways_comb\b", line, re.I):
            # Narrow block scan: catch obvious illegal timing controls inside
            # the next few lines without trying to parse SV grammar.
            start = idx - 1
            snippet = "\n".join(lines[start:start + 12])
            if re.search(r"(^|[^'])#\s*\d|@\s*\(|\bwait\b", snippet, re.I):
                _audit_add(
                    findings, "high", "timing_control_in_always_comb", path, root, idx,
                    "always_comb must not contain timing/event controls; keep it purely combinational"
                )

def run_source_audit(
    cfg: dict,
    *,
    print_cmd: bool = False,
    experimental: set[str] | None = None,
) -> dict:
    """Built-in tool-independent RTL source audit.

    This is deliberately heuristic. It highlights sim/synth traps
    and FPGA RTL risks before the agent runs lint/sim/synth.

    ``experimental`` carries opt-in feature names from
    ``--experimental-*`` flags. v1.0+ audit recognises ``"ast"`` only
    as a disclosure hint: the engine field flips to ``"verible-ast"``
    when both the flag is set AND the binary is on PATH, but the
    finding set is unchanged. Real AST-driven rules land in a later
    release; this round freezes the contract so downstream agents can
    start reading ``audit_engine`` immediately.
    """
    experimental = experimental or set()
    root: Path = cfg["_root"]
    files = _iter_audit_source_files(cfg)

    # Engine disclosure per JSON-CONTRACT.md. "regex" is the v1.0
    # baseline; "verible-ast" means the flag was requested AND the
    # binary is actually available — flag-requested-but-unavailable
    # silently degrades to regex (the warning from features.py already
    # tells the user the flag did nothing).
    engine = "regex"
    ast_rules_active = False
    if "ast" in experimental:
        try:
            from .verible_client import ast_available
            if ast_available():
                engine = "verible-ast"
                ast_rules_active = True
        except ImportError:
            pass

    if print_cmd:
        return {
            "stage": "audit", "status": "dry-run", "tool": "built-in-source-audit",
            "audit_engine": engine,
            "files": [str(p.relative_to(root)) for p in files],
        }

    findings: list[dict] = []
    missing = []
    for path in files:
        try:
            raw = path.read_text(errors="ignore")
        except OSError as exc:
            missing.append(f"{path}: {exc}")
            continue

        stripped = _strip_comments_for_audit(raw)
        raw_lines = raw.splitlines()
        lines = stripped.splitlines()
        suffix = path.suffix.lower()
        is_vhdl = suffix in {".vhd", ".vhdl"}

        if is_vhdl:
            # v0.7b §4b.4: VHDL audit expanded from 4 to ≥ 15 rules. The
            # additions are regex-feasible only; rules that require
            # cross-line state (signal driver count, sensitivity list vs
            # read set) wait for the AST migration in post-capstone work.
            for idx, line in enumerate(lines, 1):
                low = line.lower()
                # R1 (v0.5.x): after delay
                if re.search(r"\bafter\b", low):
                    _audit_add(findings, "high", "vhdl_after_in_rtl", path, root, idx,
                               "VHDL 'after' delay in RTL source; use counters/pipelines for hardware timing")
                # R2 (v0.5.x): wait for
                if re.search(r"\bwait\s+for\b", low):
                    _audit_add(findings, "high", "vhdl_wait_for_in_rtl", path, root, idx,
                               "VHDL 'wait for' is a testbench timing construct, not synthesizable RTL timing")
                # R3 (v0.5.x): deprecated arithmetic package
                if re.search(r"\bstd_logic_(arith|unsigned|signed)\b", low):
                    _audit_add(findings, "medium", "deprecated_vhdl_arithmetic_package", path, root, idx,
                               "deprecated Synopsys arithmetic package; prefer ieee.numeric_std")
                # R4 (v0.5.x): shared variable
                if re.search(r"\bshared\s+variable\b", low):
                    _audit_add(findings, "medium", "shared_variable", path, root, idx,
                               "shared variable in RTL source; review synthesis support and race behavior")
                # R5 (v0.7b): testbench-only 'wait' (no 'for' / 'until') in
                # concurrent / process body — not synthesizable.
                if re.search(r"^\s*wait\s*;", low):
                    _audit_add(findings, "high", "vhdl_bare_wait_in_rtl", path, root, idx,
                               "bare 'wait;' in RTL is testbench-only; use clocked process for synthesizable logic")
                # R6 (v0.7b): assert / report in RTL source — typically
                # testbench-only (assertion libraries like PSL/OVL preferred
                # for synthesis-time assertion).
                if re.search(r"^\s*assert\s+", low):
                    _audit_add(findings, "medium", "vhdl_assert_in_rtl", path, root, idx,
                               "concurrent 'assert' in RTL source; use PSL/OVL for synthesizable assertions or keep in TB")
                if re.search(r"^\s*report\s+\"", low):
                    _audit_add(findings, "low", "vhdl_report_in_rtl", path, root, idx,
                               "VHDL 'report' is a simulation-only message; will be ignored during synthesis")
                # R7 (v0.7b): signal of type 'time' in RTL — sim-only type.
                if re.search(r"\bsignal\s+\w+\s*:\s*time\b", low):
                    _audit_add(findings, "high", "vhdl_time_signal", path, root, idx,
                               "signal of type 'time' is sim-only; use integer counters for synthesizable timing")
                # R8 (v0.7b): integer without range — synthesizes to 32 bits.
                if re.search(r"\bsignal\s+\w+\s*:\s*integer\s*[;:=]", low) and "range" not in low:
                    _audit_add(findings, "medium", "vhdl_integer_no_range", path, root, idx,
                               "integer signal without range constraint synthesizes to 32 bits; add 'range a to b'")
                # R9 (v0.7b): variable in concurrent context (process-less)
                # — likely a typo for signal, will not synthesize as expected.
                if re.search(r"^\s*variable\s+\w+\s*:", low) and "process" not in low:
                    # Only flag at top of architecture; inside a process it's fine.
                    pass  # leave to AST migration to disambiguate context
                # R10 (v0.7b): unconstrained array (open range) in RTL.
                if re.search(r"\barray\s*\(\s*\w+\s+range\s+<>", low):
                    _audit_add(findings, "low", "vhdl_unconstrained_array", path, root, idx,
                               "unconstrained array type in RTL; constrain at declaration so synthesis can size correctly")
                # R11 (v0.7b): for-generate range with a signal (must be
                # static constant). Flag identifiers in range that are not
                # all-uppercase (constants by convention).
                m = re.search(r"\bfor\s+\w+\s+in\s+(\w+)\s*to\s+(\w+)", low)
                if m:
                    a, b = m.group(1), m.group(2)
                    for token in (a, b):
                        # Heuristic: lowercase identifier that's not a digit
                        # is likely a signal/variable, not a constant.
                        if token.isidentifier() and not token.isdigit() and token != token.upper():
                            _audit_add(findings, "medium", "vhdl_generate_nonconst_range", path, root, idx,
                                       f"for/generate range uses '{token}'; must be a static constant for synthesis")
                            break
                # R12 (v0.7b): rising_edge AND falling_edge on the same line
                # — likely a dual-edge flip-flop attempt (not synthesizable
                # in most flows).
                if "rising_edge" in low and "falling_edge" in low:
                    _audit_add(findings, "high", "vhdl_dual_edge_ff", path, root, idx,
                               "mixing rising_edge and falling_edge in one expression; most fabrics don't support dual-edge FFs")
                # R13 (v0.7b): 'attribute' synthesis directive without
                # value — likely incomplete declaration.
                if re.search(r"^\s*attribute\s+\w+\s+of\s+\w+\s*:\s*\w+\s+is\s*;", low):
                    _audit_add(findings, "medium", "vhdl_empty_attribute", path, root, idx,
                               "attribute declaration with empty value; vendor synthesis may silently ignore")
                # R14 (v0.7b): positional port map (no '=>') — fragile.
                if re.search(r"\bport\s+map\s*\([^=>]*\)\s*;", low) and "=>" not in line:
                    _audit_add(findings, "medium", "vhdl_positional_port_map", path, root, idx,
                               "positional port map; use named association (sig => port) for maintainability")
                # R15 (v0.7b): use of 'bit' / 'bit_vector' (pre-std_logic).
                # Match ': bit' or ': bit_vector' followed by space/paren/;/:=.
                if re.search(r":\s*bit(_vector)?\s*(\(|;|:=|\s|$)", low):
                    _audit_add(findings, "low", "vhdl_legacy_bit_type", path, root, idx,
                               "'bit' / 'bit_vector' are pre-IEEE-1164; prefer std_logic / std_logic_vector for tool compatibility")
            _scan_case_defaults(path, root, lines, findings, vhdl=True)
            continue

        # Verilog/SystemVerilog raw-comment scan for synthesis pragmas.
        for idx, line in enumerate(raw_lines, 1):
            low_raw = line.lower()
            if "full_case" in low_raw or "parallel_case" in low_raw:
                _audit_add(findings, "high", "full_parallel_case", path, root, idx,
                           "full_case/parallel_case pragma can hide incomplete decode and sim/synth mismatch")

        for idx, line in enumerate(lines, 1):
            low = line.lower()
            if re.search(r"(^|[^'])#\s*\d", line):
                _audit_add(findings, "high", "delay_control_in_rtl", path, root, idx,
                           "delay control in RTL source; express hardware delay with counters/pipeline/clock enable")
            if re.search(r"\bcasex\s*\(", low):
                _audit_add(findings, "high", "casex_in_rtl", path, root, idx,
                           "casex treats X/Z as don't-care; avoid in synthesizable RTL")
            if re.search(r"\bcasez\s*\(", low):
                _audit_add(findings, "medium", "casez_in_rtl", path, root, idx,
                           "casez wildcard decode requires explicit review of masked bits")
            if re.search(r"\bdefparam\b", low):
                _audit_add(findings, "medium", "defparam", path, root, idx,
                           "defparam is fragile; prefer instance parameter overrides")
            if re.search(r"\binitial\b", low):
                _audit_add(findings, "medium", "initial_in_rtl", path, root, idx,
                           "initial block/value in RTL source; verify FPGA-specific init intent or replace with reset")
            if re.search(r"\b(force|release)\b", low):
                _audit_add(findings, "high", "force_release_in_rtl", path, root, idx,
                           "force/release belongs in testbench/debug, not synthesizable RTL")
            if re.search(r"\b(program|class|covergroup|mailbox|semaphore|randcase)\b", low):
                _audit_add(findings, "high", "sv_tb_construct_in_rtl", path, root, idx,
                           "SystemVerilog testbench construct appears in RTL source; keep classes/coverage/program/mailbox/semaphore out of synthesizable files")
            if re.search(r"\b(randomize\s*\(|randc?\s+)", low):
                _audit_add(findings, "high", "sv_randomization_in_rtl", path, root, idx,
                           "SystemVerilog randomization is a verification feature, not synthesizable RTL")
            if re.search(r"\bdpi-?c\b|\bimport\s+\"DPI", line, re.I):
                _audit_add(findings, "high", "dpi_in_rtl", path, root, idx,
                           "DPI imports/exports belong in simulation models or testbench code, not synthesizable RTL")
            if re.search(r"\balways_latch\b", low):
                _audit_add(findings, "medium", "explicit_latch", path, root, idx,
                           "always_latch documents an intentional latch; verify this is acceptable for the target and not an accidental storage element")
            if re.search(r"\$(display|strobe|monitor|finish|stop|random|urandom|dump\w*)\b", low):
                _audit_add(findings, "medium", "system_task_in_rtl", path, root, idx,
                           "simulation system task in RTL source; move to testbench or guard from synthesis")
            if re.search(r"\balways\s*@\s*\([^)]*\)", line) and not re.search(r"posedge|negedge|\*|all", line, re.I):
                _audit_add(findings, "medium", "manual_sensitivity_list", path, root, idx,
                           "manual combinational sensitivity list; prefer always_comb/always @*")

        _scan_case_defaults(path, root, lines, findings, vhdl=False)
        _scan_always_assignment_style(path, root, lines, findings)
        _scan_top_level_sv_declarations(path, root, lines, findings)
        _scan_sv_type_and_modeling_style(path, root, raw, lines, findings)

    # AST-only rules (multi-driver, clocked/comb mix, ...) run AFTER
    # the regex scan so the regex findings still appear when AST runs.
    # Only the AST-only rules are added — the regex set is the baseline.
    if ast_rules_active:
        from . import audit_ast
        # Filter to verilog/SV files; verible can't parse VHDL.
        sv_files = [p for p in files if p.suffix.lower() in {".v", ".vh", ".sv", ".svh"}]
        findings.extend(audit_ast.run_ast_rules(sv_files, root))

    summary = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        summary[f["severity"]] = summary.get(f["severity"], 0) + 1

    tail_lines = [
        f"{f['severity'].upper()} {f['file']}:{f['line']} {f['rule']} — {f['message']}"
        for f in findings[:25]
    ]
    if len(findings) > 25:
        tail_lines.append(f"... {len(findings)-25} more findings omitted from tail; see JSON findings")

    result = {
        "stage": "audit",
        "status": "pass",
        "tool": "built-in-source-audit",
        "audit_engine": engine,
        "files_scanned": len(files),
        "summary": summary,
        "findings": findings,
        "tail": "\n".join(tail_lines),
    }
    warnings = []
    if missing:
        warnings.append("some source files could not be read: " + "; ".join(missing[:3]))
    if summary.get("high", 0):
        warnings.append(f"source audit found {summary['high']} high-risk RTL issue(s); review before trusting sim/synth")
    if summary.get("medium", 0):
        warnings.append(f"source audit found {summary['medium']} medium-risk RTL issue(s); review or waive with rationale")
    if not files:
        warnings.append("source audit scanned no RTL files; check [project] src/src_ordered globs in flow.toml")
    if warnings:
        result["warnings"] = warnings

    return result

def _iter_tb_source_files(cfg: dict) -> list[Path]:
    root: Path = cfg["_root"]
    proj = cfg.get("project", {})
    patterns = proj.get("tb_ordered", proj.get("tb", []))
    files = []
    for f in _expand_globs(patterns, root):
        p = Path(f)
        if not p.is_absolute():
            p = root / p
        if p.exists() and p.suffix.lower() in TB_SOURCE_EXTS:
            files.append(p.resolve())
    seen, out = set(), []
    for p in files:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out

def run_testbench_audit(cfg: dict, *, print_cmd: bool = False) -> dict:
    """Built-in, tool-independent testbench quality audit.

    This is a heuristic review queue for the verification environment: it looks
    for self-checking behavior, deterministic randomization, coverage/checker
    balance, and obvious race-prone idioms before simulation is trusted.
    """
    root: Path = cfg["_root"]
    files = _iter_tb_source_files(cfg)
    if print_cmd:
        return {
            "stage": "tb-audit", "status": "dry-run", "tool": "built-in-testbench-audit",
            "files": [str(p.relative_to(root)) for p in files],
        }

    findings: list[dict] = []
    missing = []
    combined = ""
    for path in files:
        try:
            raw = path.read_text(errors="ignore")
        except OSError as exc:
            missing.append(f"{path}: {exc}")
            continue
        combined += "\n" + raw
        stripped = _strip_comments_for_audit(raw)
        lines = stripped.splitlines()
        suffix = path.suffix.lower()
        is_python = suffix == ".py"
        whole = stripped

        def add(sev: str, rule: str, line: int, msg: str) -> None:
            _audit_add(findings, sev, rule, path, root, line, msg)

        # Self-checking evidence. This is intentionally a signal, not a proof.
        check_pat = r"\b(assert|assert property)\b|\$(?:error|fatal)\b|uvm_(?:error|fatal)|scoreboard|compare|expected|mismatch|pytest|cocotb\.test"
        pass_pat = r"\b(PASS|TEST_PASS|SUCCESS|UVM_INFO)\b"
        finish_pat = r"\$(?:finish|stop)\b|std\.env\.finish|uvm_test_done|raise_objection|drop_objection"

        if not re.search(check_pat, whole, re.I):
            add("medium", "tb_no_visible_self_check", 1,
                "testbench has no visible assert/error/fatal/scoreboard/compare mechanism; avoid waveform-only tests")
        if not re.search(pass_pat, whole, re.I):
            add("low", "tb_no_pass_marker", 1,
                "testbench has no clear PASS/TEST_PASS/SUCCESS marker; CI result may be ambiguous")
        if not is_python and not re.search(finish_pat, whole, re.I):
            add("low", "tb_no_finish_or_objection", 1,
                "testbench has no visible finish/stop or UVM objection control; verify simulation terminates deterministically")

        has_random = False
        has_seed_log = False
        has_coverage = False
        has_clocking = False
        has_interface = False
        has_modport = False
        has_class = False
        has_mailbox = False
        has_thread = False

        if suffix in {".sv", ".svh"} and re.search(r"\b(module|interface|program|package)\b", whole) and not re.search(r"\btimeunit\b|`\s*timescale\b", raw, re.I):
            add("low", "tb_time_unit_unspecified", 1,
                "testbench has no visible timeunit/timeprecision or `timescale; delay and clock periods may depend on compile context")

        for idx, line in enumerate(lines, 1):
            low = line.lower()
            if re.search(r"\$random\b", low):
                add("medium", "tb_legacy_random", idx,
                    "uses $random; prefer seeded $urandom/randomize with logged seed for reproducible regression")
            if re.search(r"\b(randomize\s*\(|randc?\s+|\$urandom(?:_range)?\b)", low):
                has_random = True
            if re.search(r"\b(seed|ntb_random_seed|sv_seed|random_seed|UVM_TESTNAME)\b", line, re.I):
                has_seed_log = True
            if re.search(r"\bcovergroup\b|\bcoverpoint\b|\bcross\b|coverage", low):
                has_coverage = True
            if re.search(r"\bclocking\b", low):
                has_clocking = True
            if re.search(r"\binterface\b|\bvirtual\s+\w*interface\b|\bmodport\b", low):
                has_interface = True
            if re.search(r"\bmodport\b", low):
                has_modport = True
            if re.search(r"\bclass\b", low):
                has_class = True
            if re.search(r"\bmailbox\b|\bsemaphore\b|\bevent\b", low):
                has_mailbox = True
            if re.search(r"\bfork\b|\bjoin(?:_any|_none)?\b", low):
                has_thread = True
            if re.search(r"#\s*0\b", line):
                add("medium", "tb_zero_delay_race_fix", idx,
                    "#0 delay is a fragile race workaround; use clocking blocks, sampling discipline, or event-region-aware code")
            if re.search(r"@(posedge\s+\w+).*?=", line) and not re.search(r"<=", line):
                add("low", "tb_blocking_drive_on_clock_edge", idx,
                    "blocking drive on a clock edge can race the DUT; prefer a clocking block or defined drive skew")

        if has_random and not has_seed_log:
            add("medium", "tb_random_without_seed_log", 1,
                "random stimulus detected but no visible seed logging; failing random tests must be exactly replayable")
        if has_coverage and not re.search(check_pat, whole, re.I):
            add("medium", "tb_coverage_without_checkers", 1,
                "coverage appears without visible checkers; coverage is not meaningful unless tests are self-checking")
        if has_interface and not has_clocking:
            add("low", "tb_interface_without_clocking_block", 1,
                "SV interface/virtual interface detected without a visible clocking block; review DUT/TB race avoidance")
        if has_interface and not has_modport:
            add("low", "tb_interface_without_modport", 1,
                "SV interface detected without visible modport; define driver/monitor/DUT roles explicitly when the interface is reused")
        if has_thread and not re.search(r"\b(wait\s+fork|disable\s+fork|join(?:_all)?)\b", whole, re.I):
            add("low", "tb_thread_lifetime_unclear", 1,
                "fork/join concurrency detected; verify spawned threads are synchronized or cleanly disabled")
        if has_class and not re.search(r"\b(driver|monitor|scoreboard|generator|sequencer|environment|agent)\b", whole, re.I):
            add("low", "tb_class_without_role_names", 1,
                "classes detected but component roles are not obvious; name drivers, monitors, scoreboards, and generators clearly")
        if has_mailbox and not re.search(r"\b(?:put|get|peek)\s*\(", whole, re.I):
            add("low", "tb_ipc_object_without_use", 1,
                "mailbox/semaphore/event detected but no obvious IPC operation; review thread communication")

    summary = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        summary[f["severity"]] = summary.get(f["severity"], 0) + 1
    tail_lines = [
        f"{f['severity'].upper()} {f['file']}:{f['line']} {f['rule']} — {f['message']}"
        for f in findings[:25]
    ]
    if len(findings) > 25:
        tail_lines.append(f"... {len(findings)-25} more findings omitted from tail; see JSON findings")

    result = {
        "stage": "tb-audit",
        "status": "pass",
        "tool": "built-in-testbench-audit",
        "files_scanned": len(files),
        "summary": summary,
        "findings": findings,
        "tail": "\n".join(tail_lines),
    }
    warnings = []
    if missing:
        warnings.append("some testbench files could not be read: " + "; ".join(missing[:3]))
    if not files:
        warnings.append("testbench audit scanned no TB files; check [project] tb/tb_ordered globs in flow.toml")
    if summary.get("medium", 0):
        warnings.append(f"testbench audit found {summary['medium']} verification-quality issue(s); review before trusting regression results")
    if summary.get("high", 0):
        warnings.append(f"testbench audit found {summary['high']} high-risk issue(s)")
    if warnings:
        result["warnings"] = warnings
    return result
