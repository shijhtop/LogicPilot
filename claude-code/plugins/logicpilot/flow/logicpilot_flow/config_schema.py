"""Hand-written schema validator for flow.toml (v0.7a §4a.4).

Goals:
- Surface typos in section names + preset names early, with did-you-mean
  via difflib (no Levenshtein dependency).
- Stay in stdlib — explicitly rejects Pydantic v2 to preserve the "zero
  compiled Python deps" promise (Pydantic's core is Rust → wheel matrix
  pain on musl / Apple Silicon / ARM).
- Be a pure function. validate(dict) -> list[ValidationError]; no
  side effects, no global state, no implicit logging.

Coverage:
- Top-level keys: project / toolchain / pipeline / stages / activity /
  power / verification / metrics / plan / telemetry. Anything else →
  validation warning.
- [pipeline].preset name: yosys-nextpnr / vivado / asic-openlane.
- (out of scope for v0.7a — see /lp-doctor for runtime schema checks)
  Nested-field validation is intentionally minimal here; downstream
  consumers (resolve_stage, run_plan_check, etc.) already error on
  malformed values at use time. We catch the structural typos that
  silently fall through to default-then-fail-much-later behavior.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass


# v0.6 + v0.7a + post-capstone forward-compat. Add new sections here as
# features land — keep the allow-list small but tolerant of legitimate
# future additions (telemetry placeholder lives here for v1.x).
KNOWN_TOP_KEYS: frozenset[str] = frozenset({
    "project",
    "toolchain",
    "pipeline",
    "stages",
    "activity",
    "power",
    "verification",
    "metrics",
    "plan",
    "telemetry",
    "cdc",          # used by cdc-check + constraints to locate the inventory
    "constraints",  # used by constraints stage for output path overrides
})

# Shipped presets. Project-local presets are accepted unconditionally
# (resolve_stage handles unknown preset names via safe-preset fallback).
KNOWN_PIPELINE_PRESETS: frozenset[str] = frozenset({
    "yosys-nextpnr",
    "vivado",
    "asic-openlane",
})

# Internal `_`-prefixed keys are populated by load_config and are NOT
# user-facing; they never need did-you-mean suggestions.
_INTERNAL_KEY_PREFIX = "_"


@dataclass(frozen=True)
class ValidationError:
    """One validation issue. Immutable so callers can stash them safely."""
    path: str
    message: str
    suggestion: str | None = None

    def format(self) -> str:
        if self.suggestion:
            return f"{self.path}: {self.message} — {self.suggestion}"
        return f"{self.path}: {self.message}"


def _did_you_mean(
    unknown: str,
    known: frozenset[str] | set[str],
    *,
    n: int = 3,
    cutoff: float = 0.6,
) -> str | None:
    """Suggest the closest known names. Returns None when nothing is close
    enough — fabricating a poor suggestion is worse than no suggestion."""
    matches = difflib.get_close_matches(unknown, list(known), n=n, cutoff=cutoff)
    if not matches:
        return None
    return f"Did you mean: {', '.join(matches)}?"


def validate(config: dict) -> list[ValidationError]:
    """Return validation issues for a parsed flow.toml. Empty list = clean.

    Caller decides severity: in v0.7a these are non-fatal warnings the CLI
    prints alongside JSON output. /lp-doctor (v0.7a follow-up) reports them
    as part of the doctor check list. v0.8+ may upgrade specific checks to
    hard errors via deprecation cycle.
    """
    errors: list[ValidationError] = []

    if not isinstance(config, dict):
        errors.append(ValidationError(
            path="<root>",
            message=f"top-level must be a TOML table, got {type(config).__name__}",
        ))
        return errors

    # Top-level key allow-list with did-you-mean suggestions.
    for key in config:
        if key.startswith(_INTERNAL_KEY_PREFIX):
            continue
        if key in KNOWN_TOP_KEYS:
            continue
        errors.append(ValidationError(
            path=key,
            message=f"unknown top-level key '{key}'",
            suggestion=_did_you_mean(key, KNOWN_TOP_KEYS),
        ))

    # [pipeline].preset allow-list.
    pipeline = config.get("pipeline")
    if isinstance(pipeline, dict):
        preset = pipeline.get("preset")
        if isinstance(preset, str) and preset and preset not in KNOWN_PIPELINE_PRESETS:
            errors.append(ValidationError(
                path="pipeline.preset",
                message=f"unknown preset '{preset}'",
                suggestion=_did_you_mean(preset, KNOWN_PIPELINE_PRESETS),
            ))

    # [toolchain].preset (legacy location for the same value).
    toolchain = config.get("toolchain")
    if isinstance(toolchain, dict):
        preset = toolchain.get("preset")
        if isinstance(preset, str) and preset and preset not in KNOWN_PIPELINE_PRESETS:
            errors.append(ValidationError(
                path="toolchain.preset",
                message=f"unknown preset '{preset}'",
                suggestion=_did_you_mean(preset, KNOWN_PIPELINE_PRESETS),
            ))

    # Per-stage scheduler hints (added post-v1.0 with the DAG scheduler).
    # Catch obvious type errors so they surface as warnings instead of
    # silently breaking parallel runs.
    stages = config.get("stages")
    if isinstance(stages, dict):
        for name, spec in stages.items():
            if not isinstance(spec, dict):
                continue  # flat-string spec — nothing to validate
            errors.extend(_validate_scheduler_hints(name, spec))

    return errors


def _validate_scheduler_hints(stage: str, spec: dict) -> list[ValidationError]:
    """Type-check the optional scheduler hints on one stage spec.

    These are advisory — the scheduler treats missing/malformed values
    as "no constraint". The validator just warns the user so a typo in
    expected_mem_gb doesn't silently let an OOM happen.
    """
    out: list[ValidationError] = []

    deps = spec.get("depends_on")
    if deps is not None:
        if not isinstance(deps, list) or not all(isinstance(x, str) for x in deps):
            out.append(ValidationError(
                path=f"stages.{stage}.depends_on",
                message="must be a list of stage names (strings)",
            ))

    mem = spec.get("expected_mem_gb")
    if mem is not None and not (isinstance(mem, (int, float)) and mem >= 0):
        out.append(ValidationError(
            path=f"stages.{stage}.expected_mem_gb",
            message=f"must be a non-negative number; got {mem!r}",
        ))

    cpu = spec.get("expected_cpu_cores")
    if cpu is not None and not (isinstance(cpu, int) and cpu >= 1):
        out.append(ValidationError(
            path=f"stages.{stage}.expected_cpu_cores",
            message=f"must be a positive integer; got {cpu!r}",
        ))

    tok = spec.get("license_token")
    if tok is not None and not (isinstance(tok, str) and tok):
        out.append(ValidationError(
            path=f"stages.{stage}.license_token",
            message=f"must be a non-empty string; got {tok!r}",
        ))

    return out


def format_errors(errors: list[ValidationError]) -> list[str]:
    """Render a list of ValidationError as a list of human-readable strings,
    suitable for stuffing into a JSON 'warnings' array."""
    return [e.format() for e in errors]
