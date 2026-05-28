"""Built-in plan-check stage.

Verifies the planning *process* happened, not the planning *content*. The
agent's job (via ``hardware-design-planning`` skill) is to interrogate the
user about ambiguities and capture decisions in markdown files under
``docs/``. This stage checks those docs exist as evidence the process ran.

Two scopes, auto-detected:

- **Block scope** (default) — single IP, peripheral, accelerator block,
  bridge, FIFO, filter. Validates ``docs/{spec,uarch,plan}.md``.
- **Project scope** — multi-partition design (SoC, large algorithm,
  multi-block accelerator, clocking subsystem, mixed-signal interface,
  …). Triggered by the *presence* of ``docs/arch.md``. Validates
  ``docs/arch.md``, ``docs/integration_plan.md``, ``docs/milestones.md``,
  parses arch.md's partition table — heading may be ``## Subsystems``,
  ``## Components``, ``## Pipeline stages``, ``## Units``, ``## Channels``,
  ``## Blocks``, or ``## Modules`` to match the design's natural
  terminology — and recursively validates
  ``docs/subsystems/<name>/{spec,uarch,plan}.md`` for every named
  partition unit (the on-disk directory is always ``subsystems/``
  regardless of the heading alias used).

The mode signal is the file ``arch.md`` itself — there is no flow.toml flag.
Writing the file IS the opt-in. This keeps block users on the simple path
and project users on a path that scales without per-project config.

It deliberately does NOT validate section names, table shapes, or domain
content. Schema enforcement produces false rigor — agents fill schema-
pleasing tables without thinking. Content quality is the agent's job,
guided by the skill, not the gate's. Configure the docs directory via
``[plan].docs_dir`` in ``flow.toml`` (default ``docs``).
"""
from __future__ import annotations

import re
from pathlib import Path

DEFAULT_DOCS_DIR = "docs"
SPEC_FILE = "spec.md"
UARCH_FILE = "uarch.md"
PLAN_FILE = "plan.md"
ARCH_FILE = "arch.md"
INTEGRATION_FILE = "integration_plan.md"
MILESTONES_FILE = "milestones.md"
SUBSYSTEMS_DIR = "subsystems"

# Deprecation cycle (v0.6 → v0.7b): when run_plan_check is invoked with
# soft_mode=True (the default for run_all in v0.6), would-be hard failures
# become status="pass" + per-finding warnings prefixed with the stable
# DEPRECATION_PREFIX, and the result carries a top-level `deprecation`
# field. CI integrators key off the prefix to detect pending deprecation
# (grep '^\[DEPRECATION-WILL-FAIL-IN-' in warnings[]). The prefix is
# milestone-versioned so the same protocol works for future deprecation
# cycles (e.g. v0.9 coverage_enforcement) — integrators only need to
# match the prefix shape, not a specific milestone.
DEPRECATION_PREFIX = "[DEPRECATION-WILL-FAIL-IN-v0.7b]"
DEPRECATION_NOTE = (
    "starting v0.7b, plan-check will hard-fail by default; "
    "use --no-plan-gate to silence, or LOGICPILOT_STRICT=1 to preview "
    "the v0.7b behavior now"
)

# Non-triviality threshold per doc. A real planning doc runs many lines.
# This floor catches "agent wrote 3 lines to satisfy the gate" without
# locking out genuinely small blocks.
MIN_BYTES = 200

# Template placeholder fragments that should NOT survive in a real doc.
# Conservative list — match prose phrases unlikely to appear in real specs.
TEMPLATE_LEFTOVER_PATTERNS = (
    r"\(One short paragraph",
    r"\(replace with your",
    r"<one-line",
    r"\(Bullets: anything you are NOT",
)

# arch.md must contain a '## Subsystems' (or '## Subsystem inventory')
# heading followed by a markdown table. The table's first column is the
# subsystem name and must be a legal directory name so the planner can
# create docs/subsystems/<name>/ underneath.
# The partition table can use any common hardware-design vocabulary as
# its heading. plan-check accepts all of these aliases so a clocking,
# analog, DFT, power, or RF design isn't forced to call its partition
# units "Subsystems" if the natural word for the design is "Components"
# or "Pipeline stages" or "Channels".
SUBSYSTEM_HEADING_RE = re.compile(
    r"^##\s+("
    r"Subsystems?(?:\s+inventory)?"
    r"|Components?"
    r"|Pipeline\s+stages?"
    r"|Units?"
    r"|Channels?"
    r"|Blocks?"
    r"|Modules?"
    r")\s*$",
    re.M | re.I,
)
SUBSYSTEM_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
# Single dash-only cell (with optional alignment colon). Used to detect
# table separator rows by checking each cell, which works for 1+ columns.
SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")


def _is_separator_row(line: str) -> bool:
    """A markdown table separator row: every cell is dashes (with optional
    alignment colons). Accepts the common GFM shapes:

    - ``|---|---|``         (outer pipes, compact)
    - ``| --- | --- |``     (outer pipes, spaced)
    - ``|------|``          (single column with outer pipes)
    - ``|---``  /  ``---|`` (one outer pipe only)
    - ``--- | ---``         (no outer pipes — GFM-legal multi-column form)

    A bare ``---`` line (no pipe at all) is NOT a separator — that's a
    markdown horizontal rule which can appear outside any table.
    """
    stripped = line.strip()
    if "|" not in stripped:
        return False
    body = stripped.strip("|").strip()
    if not body:
        return False
    cells = [c.strip() for c in body.split("|")]
    if not cells:
        return False
    return all(SEPARATOR_CELL_RE.match(c) for c in cells)


def _docs_dir(cfg: dict) -> Path:
    plan_cfg = cfg.get("plan") if isinstance(cfg.get("plan"), dict) else {}
    rel = str(plan_cfg.get("docs_dir", DEFAULT_DOCS_DIR))
    root: Path = cfg["_root"]
    return root / rel


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _add(
    findings: list[dict],
    severity: str,
    rule: str,
    file_rel: str,
    line: int,
    message: str,
) -> None:
    findings.append(
        {
            "severity": severity,
            "rule": rule,
            "file": file_rel,
            "line": line,
            "message": message,
        }
    )


def _check_doc(
    path: Path,
    name: str,
    root: Path,
    findings: list[dict],
    *,
    require_checkbox: bool = False,
) -> bool:
    """Validate one planning doc; append findings on failure.

    Returns True iff the doc exists, is non-trivial, contains no leftover
    placeholders, and (if ``require_checkbox`` is set) has at least one
    resumable checkbox. The caller uses the return value to decide whether
    to short-circuit downstream checks that depend on this doc.
    """
    rel = _rel(path, root)
    if not path.exists():
        _add(
            findings,
            "high",
            "plan_missing_file",
            rel,
            1,
            f"{name} missing — apply hardware-design-planning skill to produce it",
        )
        return False

    text = path.read_text(errors="ignore")
    stripped_len = len(text.strip())
    if stripped_len < MIN_BYTES:
        _add(
            findings,
            "high",
            "plan_doc_trivial",
            rel,
            1,
            f"{name} is too short ({stripped_len} bytes < {MIN_BYTES}); looks like "
            "a placeholder, not real design intent",
        )
        return False

    for pat in TEMPLATE_LEFTOVER_PATTERNS:
        m = re.search(pat, text)
        if m:
            line = text[: m.start()].count("\n") + 1
            _add(
                findings,
                "high",
                "plan_template_placeholder",
                rel,
                line,
                f"{name} contains unfilled exemplar placeholder near "
                f"'{m.group(0)[:40]}' — fill in real decisions or remove the line",
            )
            return False

    if require_checkbox and not re.search(r"^\s*[-*+]\s*\[[ xX]\]\s+\S", text, re.M):
        _add(
            findings,
            "high",
            "plan_no_checkboxes",
            rel,
            1,
            f"{name} has no '- [ ] task' checkboxes (markdown bullets - * + all "
            "accepted); plan.md is the resumable execution log — without "
            "checkboxes, a dropped session cannot pick up where it left off. "
            "See references/ exemplars for the pattern.",
        )
        return False

    return True


def _parse_subsystems(text: str) -> tuple[list[str], list[str]]:
    """Extract subsystem names from arch.md.

    Looks for '## Subsystems' or '## Subsystem inventory' heading, then the
    first markdown table after it. The FIRST table row is treated as the
    header (skipped unconditionally, regardless of its content — the user
    chooses their own column labels). If the next row is a separator row
    it is skipped too; otherwise it is treated as data. Every later table
    row's first column is a candidate subsystem name. Returns
    (names_deduped, parse_errors).

    A name is accepted iff it matches SUBSYSTEM_NAME_RE so it can be used
    as a directory name. Names are NOT filtered by content — a subsystem
    legitimately called ``module`` or ``name`` is just a subsystem.
    """
    m = SUBSYSTEM_HEADING_RE.search(text)
    if not m:
        return [], [
            "arch.md has no partition heading — project-scope planning "
            "requires one of '## Subsystems', '## Subsystem inventory', "
            "'## Components', '## Pipeline stages', '## Units', "
            "'## Channels', '## Blocks', or '## Modules' followed by a "
            "markdown table whose first column is the partition unit's "
            "name (used as the directory name under docs/subsystems/)"
        ]

    after = text[m.end():]
    lines = after.splitlines()

    # Find the separator row — it's the unambiguous marker of a markdown
    # table (a bare '|' in prose is too common to anchor on). Scan from
    # the heading until either a separator is found or the next heading
    # closes the section.
    sep_idx = -1
    for j in range(len(lines)):
        if lines[j].lstrip().startswith("#"):
            break
        if _is_separator_row(lines[j]):
            sep_idx = j
            break

    if sep_idx == -1:
        return [], [
            "arch.md's partition heading is not followed by a markdown "
            "table (no separator row like '|---|---|' or '--- | ---' was "
            "found before the next heading) — add a header row plus a "
            "separator row so plan-check can identify the table"
        ]

    # Data rows start after the separator and run until the first non-
    # table line (blank, prose, next heading, etc.). A real table row
    # contains at least one '|'.
    i = sep_idx + 1
    names: list[str] = []
    errors: list[str] = []
    while i < len(lines):
        line = lines[i].rstrip()
        if "|" not in line:
            break
        # Tolerate stray separator rows mid-table.
        if _is_separator_row(line):
            i += 1
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells:
            i += 1
            continue
        first = cells[0]
        if not first:
            # Empty leading cell (e.g. ``| | foo |``) — skip silently.
            i += 1
            continue
        if SUBSYSTEM_NAME_RE.match(first):
            names.append(first)
        else:
            errors.append(
                f"subsystem name '{first}' is not a legal directory name "
                "(expected ^[a-zA-Z][a-zA-Z0-9_-]*$); rename it in arch.md"
            )
        i += 1

    if not names and not errors:
        errors.append(
            "arch.md's partition table has no data rows — add one row "
            "per partition unit with its name in the first column"
        )

    # Detect duplicate names early — collisions break the per-subsystem
    # docs/subsystems/<name>/ layout.
    seen: dict[str, int] = {}
    for n in names:
        seen[n] = seen.get(n, 0) + 1
    duplicates = sorted(n for n, c in seen.items() if c > 1)
    for dup in duplicates:
        errors.append(f"subsystem name '{dup}' appears more than once in arch.md")

    # Return de-duplicated, order-preserved names so the caller checks each
    # subsystem directory exactly once even if the table is dirty.
    seen_set: set[str] = set()
    deduped: list[str] = []
    for n in names:
        if n not in seen_set:
            seen_set.add(n)
            deduped.append(n)
    return deduped, errors


def _check_subsystem(
    name: str,
    subsystems_dir: Path,
    root: Path,
    findings: list[dict],
) -> None:
    sub_dir = subsystems_dir / name
    if not sub_dir.is_dir():
        _add(
            findings,
            "high",
            "plan_missing_subsystem_dir",
            _rel(sub_dir, root),
            1,
            f"subsystem '{name}' listed in arch.md but "
            f"docs/subsystems/{name}/ does not exist — create the directory "
            "and produce spec.md, uarch.md, plan.md by running the per-"
            "subsystem Q&A (see hardware-design-planning skill)",
        )
        return
    _check_doc(sub_dir / SPEC_FILE, f"subsystems/{name}/spec.md", root, findings)
    _check_doc(sub_dir / UARCH_FILE, f"subsystems/{name}/uarch.md", root, findings)
    _check_doc(
        sub_dir / PLAN_FILE,
        f"subsystems/{name}/plan.md",
        root,
        findings,
        require_checkbox=True,
    )


def run_plan_check(
    cfg: dict, *, print_cmd: bool = False, soft_mode: bool = False
) -> dict:
    """Built-in: verify planning docs exist with non-trivial content.

    Auto-detects scope from the presence of ``docs/arch.md``:

    - absent → block scope: validates ``docs/{spec,uarch,plan}.md``
    - present → project scope: validates the top-4 docs plus every
      subsystem tree referenced by arch.md's ``## Subsystems`` table

    Returns the standard LogicPilot stage envelope with an extra ``mode``
    key. ``status='fail'`` when any high-severity finding fires, so the
    front-end chain stops here.

    With ``soft_mode=True`` (v0.6 deprecation cycle), would-be failures are
    demoted to ``status='pass'`` plus one prefixed warning per high finding
    (prefix: :data:`DEPRECATION_PREFIX`), and the result carries a
    top-level ``deprecation`` field pointing at :data:`DEPRECATION_NOTE`.
    Soft mode is selected by ``run_all`` for the default pipeline; direct
    callers (single-stage invocation, ``LOGICPILOT_STRICT=1``) keep the
    hard-fail behavior.
    """
    root: Path = cfg["_root"]
    docs = _docs_dir(cfg)
    arch_path = docs / ARCH_FILE
    docs_rel = _rel(docs, root)

    mode = "project" if arch_path.exists() else "block"

    if print_cmd:
        if mode == "project":
            top_files = (ARCH_FILE, INTEGRATION_FILE, MILESTONES_FILE)
        else:
            top_files = (SPEC_FILE, UARCH_FILE, PLAN_FILE)
        return {
            "stage": "plan-check",
            "status": "dry-run",
            "tool": "built-in-plan-check",
            "mode": mode,
            "docs_dir": docs_rel,
            "files": [
                _rel(docs / f, root) + ("" if (docs / f).exists() else " (missing)")
                for f in top_files
            ],
        }

    findings: list[dict] = []

    if mode == "block":
        _check_doc(docs / SPEC_FILE, "spec.md", root, findings)
        _check_doc(docs / UARCH_FILE, "uarch.md", root, findings)
        _check_doc(
            docs / PLAN_FILE, "plan.md", root, findings, require_checkbox=True
        )
    else:
        # Validate arch.md first. If it fails the basics (missing/trivial/
        # placeholder), short-circuit — there is no credible source for
        # the subsystem enumeration, and reporting downstream gaps the
        # user cannot fix without arch.md just buries the real advice
        # ("write arch.md first") in noise.
        arch_ok = _check_doc(arch_path, "arch.md", root, findings)
        if arch_ok:
            _check_doc(
                docs / INTEGRATION_FILE, "integration_plan.md", root, findings
            )
            # milestones.md is a roster of phases; checkbox not required.
            # plan.md inside each subsystem still requires a checkbox
            # (it's the resumable execution log for that subsystem).
            _check_doc(
                docs / MILESTONES_FILE, "milestones.md", root, findings
            )
            text = arch_path.read_text(errors="ignore")
            names, parse_errors = _parse_subsystems(text)
            arch_rel = _rel(arch_path, root)
            for err in parse_errors:
                _add(
                    findings, "high", "plan_arch_parse_error",
                    arch_rel, 1, err,
                )
            subsystems_dir = docs / SUBSYSTEMS_DIR
            for name in names:
                _check_subsystem(name, subsystems_dir, root, findings)

    summary = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        summary[f["severity"]] = summary.get(f["severity"], 0) + 1

    hard_fail = summary["high"] > 0
    tail = (
        "\n".join(
            f"{f['severity'].upper()} {f['file']}:{f['line']} {f['rule']} — {f['message']}"
            for f in findings[:25]
        )
        or f"plan-check passed ({mode} scope)"
    )

    if soft_mode and hard_fail:
        # Deprecation cycle: demote v0.7b-bound fail to pass + emit one
        # prefixed warning per high finding so CI can detect pending
        # deprecation by grepping warnings[] for DEPRECATION_PREFIX.
        status = "pass"
        warnings = [
            f"{DEPRECATION_PREFIX} {f['file']}:{f['line']} {f['rule']} — {f['message']}"
            for f in findings if f["severity"] == "high"
        ]
    elif hard_fail:
        status = "fail"
        warnings = [
            f"plan-check failed in {mode} scope: {summary['high']} blocking "
            "issue(s). Apply hardware-design-planning skill to interrogate "
            "the brief and capture real decisions; this stage only verifies "
            "the docs exist with non-trivial content."
        ]
    elif summary["medium"]:
        status = "pass"
        warnings = [
            f"plan-check passed with {summary['medium']} soft issue(s); see findings"
        ]
    else:
        status = "pass"
        warnings = []

    result = {
        "stage": "plan-check",
        "status": status,
        "tool": "built-in-plan-check",
        "mode": mode,
        "docs_dir": docs_rel,
        "summary": summary,
        "findings": findings,
        "tail": tail,
    }
    if soft_mode:
        result["deprecation"] = DEPRECATION_NOTE
    if warnings:
        result["warnings"] = warnings
    return result
