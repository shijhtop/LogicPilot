"""Unit tests for the plan-check built-in stage.

Two scopes, auto-detected by presence of ``docs/arch.md``:

- **Block scope** (default): docs/{spec,uarch,plan}.md must exist, be
  non-trivial, contain no leftover placeholders, plan.md must have at least
  one checkbox.
- **Project scope**: docs/arch.md, docs/integration_plan.md,
  docs/milestones.md plus per-subsystem docs/subsystems/<name>/{spec,uarch,
  plan}.md trees enumerated from arch.md's ``## Subsystems`` table.

Tests deliberately do NOT touch section names or table shapes for content
beyond what plan-check itself parses — content quality is the agent's job
(driven by the hardware-design-planning skill), not the gate's.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.plan_check import MIN_BYTES, run_plan_check  # noqa: E402


def _cfg(tmp_path: Path) -> dict:
    return {"_root": tmp_path}


def _write_block(
    tmp_path: Path,
    spec: str | None = None,
    uarch: str | None = None,
    plan: str | None = None,
    docs_dir: str = "docs",
) -> None:
    d = tmp_path / docs_dir
    d.mkdir(parents=True, exist_ok=True)
    if spec is not None:
        (d / "spec.md").write_text(spec)
    if uarch is not None:
        (d / "uarch.md").write_text(uarch)
    if plan is not None:
        (d / "plan.md").write_text(plan)


def _write_project_top(
    tmp_path: Path,
    arch: str | None = None,
    integration: str | None = None,
    milestones: str | None = None,
    docs_dir: str = "docs",
) -> None:
    d = tmp_path / docs_dir
    d.mkdir(parents=True, exist_ok=True)
    if arch is not None:
        (d / "arch.md").write_text(arch)
    if integration is not None:
        (d / "integration_plan.md").write_text(integration)
    if milestones is not None:
        (d / "milestones.md").write_text(milestones)


def _write_subsystem(
    tmp_path: Path,
    name: str,
    spec: str | None = None,
    uarch: str | None = None,
    plan: str | None = None,
    docs_dir: str = "docs",
) -> None:
    d = tmp_path / docs_dir / "subsystems" / name
    d.mkdir(parents=True, exist_ok=True)
    if spec is not None:
        (d / "spec.md").write_text(spec)
    if uarch is not None:
        (d / "uarch.md").write_text(uarch)
    if plan is not None:
        (d / "plan.md").write_text(plan)


# Long-enough content that satisfies MIN_BYTES without trying to look like
# a real spec. The whole point of the design is that shape is not validated
# — only presence and non-triviality.
LONG_PROSE = (
    "This block does foo. " * 30
    + "\nDecisions: reset is async, deassert sync. AXIL latency 2 cycles. "
    + "Failure mode on overflow: drop and set status flag. "
    + "All decisions came from explicit Q&A with the user."
)

PLAN_WITH_CHECKBOX = (
    "# plan\n\n## Phase 1\n"
    + "- [ ] rtl/foo_top.sv ← uarch.md \n"
    + "- [ ] tb/foo_tb.sv  ← uarch.md \n"
    "\nNotes: this is the resumable execution log; check items off as work\n"
    "completes so a dropped session can pick up by reading unchecked rows.\n"
    "Additional context follows the checkboxes to satisfy the size floor.\n"
)


def _arch_with_subsystems(*names: str) -> str:
    """Build a minimal arch.md that satisfies the parser for the named
    subsystems. The text is padded over MIN_BYTES with real-looking prose.
    """
    rows = "\n".join(f"| {n} | role of {n} | clk_100 | always-on | AXIL |" for n in names)
    return (
        "# Project arch\n\nThis is a small project covering compute, "
        + "control, and IO subsystems. Decisions taken from architecture "
        + "Q&A:\n\n"
        + "- Top-level bus: AXI4-Lite\n- Single clock domain at 100 MHz\n"
        + "- Single async-deassert reset\n- Memory map: 64 KB total\n\n"
        + "## Subsystems\n\n"
        + "| name | role | clock | power | bus iface |\n"
        + "|------|------|-------|-------|-----------|\n"
        + rows
        + "\n\n"
        + "## Memory map\n\nDecisions captured above.\n"
        + "## Clock plan\n\nSingle 100 MHz domain shared by all subsystems.\n"
    )


def _full_subsystem_set(tmp_path: Path, *names: str) -> None:
    for name in names:
        _write_subsystem(
            tmp_path, name,
            spec=LONG_PROSE, uarch=LONG_PROSE, plan=PLAN_WITH_CHECKBOX,
        )


# ============================================================================
# Block-scope tests (legacy behavior — arch.md absent)
# ============================================================================

def test_block_pass_when_all_three_docs_present_and_substantial(tmp_path):
    _write_block(tmp_path, spec=LONG_PROSE, uarch=LONG_PROSE, plan=PLAN_WITH_CHECKBOX)
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "pass", r["findings"]
    assert r["mode"] == "block"
    assert r["summary"] == {"high": 0, "medium": 0, "low": 0}


def test_block_dry_run_lists_paths(tmp_path):
    r = run_plan_check(_cfg(tmp_path), print_cmd=True)
    assert r["status"] == "dry-run"
    assert r["mode"] == "block"
    assert r["tool"] == "built-in-plan-check"
    assert all("(missing)" in f for f in r["files"])
    assert any(f.endswith("spec.md (missing)") for f in r["files"])


def test_block_fails_when_all_files_missing(tmp_path):
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    rules = {f["rule"] for f in r["findings"]}
    assert rules == {"plan_missing_file"}
    assert len(r["findings"]) == 3


def test_block_fails_when_spec_missing_only(tmp_path):
    _write_block(tmp_path, uarch=LONG_PROSE, plan=PLAN_WITH_CHECKBOX)
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_missing_file" and f["file"].endswith("spec.md")
        for f in r["findings"]
    )


def test_block_fails_when_spec_is_trivially_short(tmp_path):
    _write_block(tmp_path, spec="placeholder.\n", uarch=LONG_PROSE, plan=PLAN_WITH_CHECKBOX)
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_doc_trivial" and "spec.md" in f["file"]
        for f in r["findings"]
    )


def test_block_fails_when_uarch_is_just_a_heading(tmp_path):
    _write_block(tmp_path, spec=LONG_PROSE, uarch="# uarch\n", plan=PLAN_WITH_CHECKBOX)
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(f["rule"] == "plan_doc_trivial" for f in r["findings"])


def test_block_fails_when_template_placeholder_left_in_spec(tmp_path):
    bad_spec = LONG_PROSE + "\n## Function\n\n(One short paragraph: what this block does)\n"
    _write_block(tmp_path, spec=bad_spec, uarch=LONG_PROSE, plan=PLAN_WITH_CHECKBOX)
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_template_placeholder" and "spec.md" in f["file"]
        for f in r["findings"]
    )


def test_block_plan_without_checkboxes_blocks(tmp_path):
    plan_no_box = (
        "# plan\n\nWe will write the RTL, then the TB, then run sim.\n"
        + "More words to clear the byte floor. " * 10
    )
    _write_block(tmp_path, spec=LONG_PROSE, uarch=LONG_PROSE, plan=plan_no_box)
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(f["rule"] == "plan_no_checkboxes" for f in r["findings"])


@pytest.mark.parametrize("bullet", ["-", "*", "+"])
def test_block_plan_accepts_any_markdown_bullet_style(tmp_path, bullet):
    plan = (
        f"# plan\n\n## Phase 1\n{bullet} [ ] rtl/foo.sv ← uarch §...\n"
        + "Filler text to clear the byte floor. " * 8
    )
    _write_block(tmp_path, spec=LONG_PROSE, uarch=LONG_PROSE, plan=plan)
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "pass", r["findings"]


def test_block_custom_docs_dir_via_config(tmp_path):
    _write_block(
        tmp_path, spec=LONG_PROSE, uarch=LONG_PROSE, plan=PLAN_WITH_CHECKBOX,
        docs_dir="design",
    )
    cfg = {"_root": tmp_path, "plan": {"docs_dir": "design"}}
    r = run_plan_check(cfg)
    assert r["status"] == "pass"
    assert r["docs_dir"] == "design"
    assert r["mode"] == "block"


def test_block_result_has_standard_envelope(tmp_path):
    _write_block(tmp_path, spec=LONG_PROSE, uarch=LONG_PROSE, plan=PLAN_WITH_CHECKBOX)
    r = run_plan_check(_cfg(tmp_path))
    for key in ("stage", "status", "tool", "mode", "docs_dir", "summary", "findings", "tail"):
        assert key in r, f"missing envelope key: {key}"
    assert r["stage"] == "plan-check"
    assert r["tool"] == "built-in-plan-check"


def test_block_failure_includes_warnings(tmp_path):
    r = run_plan_check(_cfg(tmp_path))
    assert "warnings" in r
    assert any("plan-check failed" in w for w in r["warnings"])


def test_block_min_bytes_threshold_is_a_constant_not_magic_number(tmp_path):
    just_under = "x" * (MIN_BYTES - 1)
    just_over = "x" * (MIN_BYTES + 50)
    _write_block(tmp_path, spec=just_under, uarch=just_over, plan=PLAN_WITH_CHECKBOX)
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_doc_trivial" and "spec.md" in f["file"]
        for f in r["findings"]
    )
    assert not any(
        f["rule"] == "plan_doc_trivial" and "uarch.md" in f["file"]
        for f in r["findings"]
    )


# ============================================================================
# Project-scope tests (arch.md present)
# ============================================================================

def test_project_pass_with_arch_integration_milestones_and_full_subsystem_tree(tmp_path):
    _write_project_top(
        tmp_path,
        arch=_arch_with_subsystems("crypto_core", "csr_block"),
        integration=LONG_PROSE,
        milestones=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "crypto_core", "csr_block")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "pass", r["findings"]
    assert r["mode"] == "project"


def test_project_dry_run_lists_top_four_files(tmp_path):
    _write_project_top(tmp_path, arch=_arch_with_subsystems("a", "b"))
    r = run_plan_check(_cfg(tmp_path), print_cmd=True)
    assert r["status"] == "dry-run"
    assert r["mode"] == "project"
    files_str = " ".join(r["files"])
    assert "arch.md" in files_str
    assert "integration_plan.md" in files_str
    assert "milestones.md" in files_str


def test_project_fails_when_integration_plan_missing(tmp_path):
    _write_project_top(
        tmp_path,
        arch=_arch_with_subsystems("crypto_core"),
        milestones=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "crypto_core")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_missing_file" and "integration_plan.md" in f["file"]
        for f in r["findings"]
    )


def test_project_fails_when_milestones_missing(tmp_path):
    _write_project_top(
        tmp_path,
        arch=_arch_with_subsystems("crypto_core"),
        integration=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "crypto_core")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_missing_file" and "milestones.md" in f["file"]
        for f in r["findings"]
    )


def test_project_fails_when_arch_has_no_subsystems_heading(tmp_path):
    arch_no_heading = "# Arch\n\n" + LONG_PROSE + "\nNo subsystems heading anywhere here."
    _write_project_top(
        tmp_path,
        arch=arch_no_heading,
        integration=LONG_PROSE,
        milestones=LONG_PROSE,
    )
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_arch_parse_error"
        and "Subsystems" in f["message"]
        for f in r["findings"]
    )


def test_project_fails_when_subsystems_heading_has_no_table(tmp_path):
    arch_no_table = (
        "# Arch\n\n" + LONG_PROSE
        + "\n## Subsystems\n\nWe will figure them out later.\n\n## Memory map\n"
        + LONG_PROSE
    )
    _write_project_top(
        tmp_path,
        arch=arch_no_table,
        integration=LONG_PROSE,
        milestones=LONG_PROSE,
    )
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(f["rule"] == "plan_arch_parse_error" for f in r["findings"])


def test_project_fails_when_subsystem_name_has_space(tmp_path):
    arch = (
        "# Arch\n\n" + LONG_PROSE
        + "\n## Subsystems\n\n"
        + "| name | role |\n|------|------|\n"
        + "| Crypto Core | does crypto |\n"
        + "| csr_block | does csr |\n\n"
        + "## Memory map\n\n" + LONG_PROSE
    )
    _write_project_top(
        tmp_path, arch=arch,
        integration=LONG_PROSE, milestones=LONG_PROSE,
    )
    # csr_block tree present, only the illegal-named row should fail
    _full_subsystem_set(tmp_path, "csr_block")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_arch_parse_error" and "Crypto Core" in f["message"]
        for f in r["findings"]
    )


def test_project_fails_when_duplicate_subsystem_names(tmp_path):
    arch = (
        "# Arch\n\n" + LONG_PROSE
        + "\n## Subsystems\n\n"
        + "| name | role |\n|------|------|\n"
        + "| dup | first |\n| dup | second |\n\n"
        + "## Memory map\n\n" + LONG_PROSE
    )
    _write_project_top(
        tmp_path, arch=arch,
        integration=LONG_PROSE, milestones=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "dup")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_arch_parse_error" and "more than once" in f["message"]
        for f in r["findings"]
    )


def test_project_fails_when_subsystem_dir_missing(tmp_path):
    _write_project_top(
        tmp_path,
        arch=_arch_with_subsystems("crypto_core", "csr_block"),
        integration=LONG_PROSE,
        milestones=LONG_PROSE,
    )
    # Only one of the two subsystems has its tree.
    _full_subsystem_set(tmp_path, "crypto_core")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_missing_subsystem_dir"
        and "csr_block" in f["file"]
        for f in r["findings"]
    )


def test_project_fails_when_subsystem_spec_missing(tmp_path):
    _write_project_top(
        tmp_path,
        arch=_arch_with_subsystems("crypto_core"),
        integration=LONG_PROSE,
        milestones=LONG_PROSE,
    )
    _write_subsystem(tmp_path, "crypto_core", uarch=LONG_PROSE, plan=PLAN_WITH_CHECKBOX)
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_missing_file"
        and "subsystems/crypto_core/spec.md" in f["file"]
        for f in r["findings"]
    )


def test_project_fails_when_subsystem_plan_has_no_checkbox(tmp_path):
    _write_project_top(
        tmp_path,
        arch=_arch_with_subsystems("crypto_core"),
        integration=LONG_PROSE,
        milestones=LONG_PROSE,
    )
    plan_no_box = "# plan\n\n" + LONG_PROSE
    _write_subsystem(
        tmp_path, "crypto_core",
        spec=LONG_PROSE, uarch=LONG_PROSE, plan=plan_no_box,
    )
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_no_checkboxes"
        and "subsystems/crypto_core/plan.md" in f["file"]
        for f in r["findings"]
    )


def test_project_skips_subsystem_parsing_when_arch_is_trivial(tmp_path):
    # arch.md exists but is tiny — should fire plan_doc_trivial on arch
    # and NOT cascade into parse-error noise from a partial file.
    _write_project_top(
        tmp_path,
        arch="# Arch\n\nTBD.\n",
        integration=LONG_PROSE,
        milestones=LONG_PROSE,
    )
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(
        f["rule"] == "plan_doc_trivial" and "arch.md" in f["file"]
        for f in r["findings"]
    )
    # No parse-error or subsystem-dir noise — they're suppressed when arch
    # didn't pass the non-triviality bar.
    assert not any(f["rule"] == "plan_arch_parse_error" for f in r["findings"])
    assert not any(
        f["rule"] == "plan_missing_subsystem_dir" for f in r["findings"]
    )


def test_project_arch_trivial_short_circuits_other_top_docs(tmp_path):
    # When arch.md is trivial AND integration_plan.md + milestones.md
    # are also absent, plan-check fires the arch finding ONLY — it does
    # not cascade into 'integration_plan.md missing' / 'milestones.md
    # missing' noise. Rationale: the user cannot write the other docs
    # credibly without arch.md, so surface that one problem clearly.
    d = tmp_path / "docs"
    d.mkdir()
    (d / "arch.md").write_text("# Arch\n\nTBD.\n")
    # integration_plan.md and milestones.md deliberately absent.
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    rules = [f["rule"] for f in r["findings"]]
    # Exactly one finding: arch.md is trivial. Everything else is
    # suppressed because there's no credible arch to enumerate from.
    assert rules == ["plan_doc_trivial"], r["findings"]
    assert "arch.md" in r["findings"][0]["file"]


def test_project_single_column_subsystems_table_parses(tmp_path):
    # A subsystems table with only the name column should parse —
    # other columns (role/clock/etc.) are recommended but optional.
    arch = (
        "# Arch\n\n" + LONG_PROSE
        + "\n## Subsystems\n\n"
        + "| name |\n|------|\n"
        + "| foo |\n\n"
        + "## Memory map\n\n" + LONG_PROSE
    )
    _write_project_top(
        tmp_path, arch=arch,
        integration=LONG_PROSE, milestones=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "foo")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "pass", r["findings"]


def test_project_subsystem_named_module_is_accepted(tmp_path):
    # A subsystem legitimately named 'module' (a legal directory name)
    # must NOT be silently dropped because the parser confused it with a
    # header-row label. The header row is identified positionally (always
    # the first table row), not by content.
    arch = (
        "# Arch\n\n" + LONG_PROSE
        + "\n## Subsystems\n\n"
        + "| name | role |\n|------|------|\n"
        + "| module | does module stuff |\n"
        + "| name   | does naming stuff |\n\n"
        + "## Memory map\n\n" + LONG_PROSE
    )
    _write_project_top(
        tmp_path, arch=arch,
        integration=LONG_PROSE, milestones=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "module", "name")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "pass", r["findings"]


def test_project_gfm_no_outer_pipe_table_parses(tmp_path):
    # GFM allows tables without leading/trailing pipes on each row.
    # plan-check must accept the form so users who copy markdown out of
    # tools that omit outer pipes (some editors, some doc generators)
    # don't trip the gate.
    arch = (
        "# Arch\n\n" + LONG_PROSE
        + "\n## Subsystems\n\n"
        + "name | role\n"
        + "--- | ---\n"
        + "foo | does foo\n"
        + "bar | does bar\n\n"
        + "## Memory map\n\n" + LONG_PROSE
    )
    _write_project_top(
        tmp_path, arch=arch,
        integration=LONG_PROSE, milestones=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "foo", "bar")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "pass", r["findings"]


def test_project_alignment_colons_in_separator_accepted(tmp_path):
    # GFM allows ``:---`` / ``---:`` / ``:---:`` in the separator row
    # to denote column alignment. The parser should accept all forms.
    arch = (
        "# Arch\n\n" + LONG_PROSE
        + "\n## Subsystems\n\n"
        + "| name | role | clock |\n"
        + "| :--- | :---: | ---: |\n"
        + "| foo | x | y |\n\n"
        + "## Memory map\n\n" + LONG_PROSE
    )
    _write_project_top(
        tmp_path, arch=arch,
        integration=LONG_PROSE, milestones=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "foo")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "pass", r["findings"]


def test_project_horizontal_rule_alone_is_not_a_separator(tmp_path):
    # A bare ``---`` line (markdown horizontal rule) must NOT be treated
    # as a 1-column separator — otherwise the parser anchors on stray
    # rules in prose and starts treating subsequent text as table rows.
    arch = (
        "# Arch\n\n" + LONG_PROSE
        + "\n## Subsystems\n\n"
        + "---\n\n"
        + "Some prose follows the rule.\n\n"
        + "## Memory map\n\n" + LONG_PROSE
    )
    _write_project_top(
        tmp_path, arch=arch,
        integration=LONG_PROSE, milestones=LONG_PROSE,
    )
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any(f["rule"] == "plan_arch_parse_error" for f in r["findings"])


def _arch_with_heading(heading: str, *names: str) -> str:
    """Variant of _arch_with_subsystems that uses an alternate partition
    heading (e.g. '## Components' instead of '## Subsystems')."""
    rows = "\n".join(
        f"| {n} | role of {n} | clk_100 | always-on | AXIL |" for n in names
    )
    return (
        "# Project arch\n\nA project using an alternate partition "
        + "vocabulary because the natural word here isn't 'subsystem'.\n\n"
        + "- Top-level bus: AXI4-Lite\n- Single clock 100 MHz\n"
        + "- Single async-deassert reset\n\n"
        + f"## {heading}\n\n"
        + "| name | role | clock | power | bus iface |\n"
        + "|------|------|-------|-------|-----------|\n"
        + rows
        + "\n\n"
        + "## Memory map\n\nDecisions captured above.\n"
    )


@pytest.mark.parametrize(
    "heading",
    [
        "Components",
        "Pipeline stages",
        "Units",
        "Channels",
        "Blocks",
        "Modules",
        "Subsystem inventory",  # spelling variant already accepted previously
    ],
)
def test_project_alternate_partition_heading_accepted(tmp_path, heading):
    # plan-check should accept any of the canonical hardware-partition
    # vocabularies as the table heading — not just "Subsystems". The
    # on-disk directory is still docs/subsystems/<name>/ regardless of
    # the heading word used.
    arch = _arch_with_heading(heading, "core_a", "core_b")
    _write_project_top(
        tmp_path, arch=arch,
        integration=LONG_PROSE, milestones=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "core_a", "core_b")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "pass", (heading, r["findings"])


def test_project_no_partition_heading_lists_all_aliases_in_error(tmp_path):
    # The user-facing error when arch.md is missing any partition heading
    # should enumerate the accepted aliases so the user knows their
    # options.
    arch = "# Arch\n\n" + LONG_PROSE + "\nNo partition heading anywhere here.\n"
    _write_project_top(
        tmp_path, arch=arch,
        integration=LONG_PROSE, milestones=LONG_PROSE,
    )
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    msg = next(
        f["message"] for f in r["findings"]
        if f["rule"] == "plan_arch_parse_error"
    )
    # Spot-check that the message names the aliases the user can pick.
    for alias in ("Subsystems", "Components", "Pipeline stages"):
        assert alias in msg, f"alias '{alias}' missing from error message"


def test_project_milestones_does_not_require_checkbox(tmp_path):
    # milestones.md is a phase roster; checkbox requirement applies to
    # plan.md only (per scope).
    _write_project_top(
        tmp_path,
        arch=_arch_with_subsystems("crypto_core"),
        integration=LONG_PROSE,
        milestones="# Milestones\n\n" + LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "crypto_core")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "pass", r["findings"]


def test_project_warns_with_mode_project_in_failure_message(tmp_path):
    # arch.md present, everything else missing — failure should call out
    # project scope so the user knows which docs to produce.
    _write_project_top(tmp_path, arch=_arch_with_subsystems("a"))
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "fail"
    assert any("project scope" in w for w in r["warnings"])


def test_project_subsystem_inventory_heading_also_accepted(tmp_path):
    # The skill allows either '## Subsystems' or '## Subsystem inventory'.
    arch = (
        "# Arch\n\n" + LONG_PROSE
        + "\n## Subsystem inventory\n\n"
        + "| name | role |\n|------|------|\n"
        + "| crypto_core | does crypto |\n\n"
        + "## Memory map\n\n" + LONG_PROSE
    )
    _write_project_top(
        tmp_path, arch=arch,
        integration=LONG_PROSE, milestones=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "crypto_core")
    r = run_plan_check(_cfg(tmp_path))
    assert r["status"] == "pass", r["findings"]


def test_project_envelope_has_mode_field(tmp_path):
    _write_project_top(
        tmp_path,
        arch=_arch_with_subsystems("crypto_core"),
        integration=LONG_PROSE,
        milestones=LONG_PROSE,
    )
    _full_subsystem_set(tmp_path, "crypto_core")
    r = run_plan_check(_cfg(tmp_path))
    assert r["mode"] == "project"
    assert "mode" in r
