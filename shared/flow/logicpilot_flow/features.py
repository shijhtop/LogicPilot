"""Experimental feature flag registry (v0.10 §7.2.3 / v1.0).

Pattern: `--experimental-<name>` CLI flags + matching env vars
(`LOGICPILOT_EXPERIMENTAL_<NAME>`) opt the driver into work that is
not yet part of the v1 contract freeze. Behaviour MAY change between
any two minor versions. CHANGELOG calls this out per flag.

When a flag matures, the experimental version becomes the default and
the flag becomes a no-op alias for one minor version (back-compat),
then is removed.

Currently registered:

- ``ast``: use Verible AST for audit / cdc instead of the regex fallback.
  Wiring is live — when the flag is set AND ``verible-verilog-syntax``
  is on PATH, ``cdc-check`` enumerates apparent CDC drivers from the
  AST and applies R7 (driver missing from inventory → fail) and R8
  (inventory crossing with no RTL driver → warn). The ``audit_engine``
  field in every audit / cdc-check JSON envelope discloses which path
  ran. If the flag is set but Verible isn't installed, the stage
  silently degrades to regex and a warning row surfaces the no-op.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    """One experimental feature row."""
    name: str
    description: str
    status: str   # "stub" | "preview" | "default-pending" | "removed-alias"
    since: str
    notes: str


# Registry — sorted alphabetically by name. Each entry's `status`
# governs what happens at runtime:
#   - stub:            accepted, emits warning, no behaviour change
#   - preview:         accepted, behaviour changes, may be unstable
#   - default-pending: behaviour now the default; flag is no-op alias
#   - removed-alias:   flag accepted but does literally nothing
REGISTRY: dict[str, Feature] = {
    "ast": Feature(
        name="ast",
        description=(
            "Use Verible AST for audit / cdc-check instead of the regex "
            "fallback. Enables cdc-check rules R7 (apparent CDC driver "
            "missing from inventory) and R8 (inventory row not visible "
            "in RTL)."
        ),
        status="preview",
        since="v1.0",
        notes=(
            "Requires verible-verilog-syntax on PATH. Behaviour MAY "
            "change between any two minor versions while the AST walker "
            "matures — pin the LogicPilot version in CI if you depend "
            "on the exact rule set. The audit_engine field "
            "('regex' vs 'verible-ast') in every JSON envelope lets "
            "agents tell which path actually ran."
        ),
    ),
    "formal": Feature(
        name="formal",
        description=(
            "Run a formal stage (bounded model check / prove / cover / "
            "live) on declared SystemVerilog assertions. Vendor-agnostic "
            "envelope; dispatches to whichever backend is installed "
            "(sby / jaspergold / vcf / qverify)."
        ),
        status="preview",
        since="v1.1",
        notes=(
            "Today only the SBY (SymbiYosys + yosys + SMT solver) "
            "backend has a real parser; the three commercial backends "
            "are accepted in the candidate list and surface "
            "'vendor parser not yet implemented' until a contributor "
            "with the license adds them. The envelope shape (mode / "
            "depth / properties / counterexamples / summary) is "
            "stable across backends — agents can rely on it. Without "
            "this flag, /lp-formal returns blocked + a pointer to "
            "set --experimental-formal."
        ),
    ),
    # Reserved for v1.1+:
    #   "lec":     yosys equiv_struct / equiv_induct stage
    #   "pattern-lib": shared/rtl-patterns/ pre-baked Cells
}


def parse_flags(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split argv into (experimental_flags, remaining_argv).

    Accepts ``--experimental-<name>`` flags anywhere in argv. Returns
    the parsed feature names + an argv with those flags removed.
    Unknown experimental flags are NOT consumed — they fall through
    to argparse so the user gets a normal error.
    """
    flags: list[str] = []
    remaining: list[str] = []
    prefix = "--experimental-"
    for token in argv:
        if token.startswith(prefix):
            name = token[len(prefix):]
            if name in REGISTRY:
                flags.append(name)
                continue
        remaining.append(token)
    return flags, remaining


def flags_from_env() -> list[str]:
    """Pick up ``LOGICPILOT_EXPERIMENTAL_<NAME>=1`` env vars.
    Truthy values: 1 / true / yes / on (case-insensitive)."""
    out: list[str] = []
    truthy = {"1", "true", "yes", "on"}
    for name in REGISTRY:
        env_name = "LOGICPILOT_EXPERIMENTAL_" + name.upper().replace("-", "_")
        raw = os.environ.get(env_name, "").strip().lower()
        if raw in truthy:
            out.append(name)
    return out


def collect_active(argv: list[str]) -> tuple[set[str], list[str]]:
    """Return (active_feature_names, argv_with_experimental_flags_stripped).
    Merges CLI flags + env vars."""
    cli_flags, remaining = parse_flags(argv)
    env_flags = flags_from_env()
    return set(cli_flags) | set(env_flags), remaining


def warnings_for_active(active: set[str]) -> list[str]:
    """Generate the warning rows the CLI surfaces in output when
    experimental flags are set. One row per active flag.
    """
    out: list[str] = []
    for name in sorted(active):
        feature = REGISTRY[name]
        prefix = f"[EXPERIMENTAL:{name}]"
        if feature.status == "stub":
            out.append(
                f"{prefix} flag accepted but NOT yet wired — behaviour "
                f"unchanged in this version. {feature.notes}"
            )
        elif feature.status == "preview":
            out.append(
                f"{prefix} preview behaviour active; may change between "
                f"minor versions. {feature.description}"
            )
        elif feature.status == "default-pending":
            out.append(
                f"{prefix} this behaviour is now the default; the flag "
                f"is a no-op alias and will be removed in a future version."
            )
        elif feature.status == "removed-alias":
            out.append(
                f"{prefix} flag accepted for back-compat but does nothing."
            )
    return out
