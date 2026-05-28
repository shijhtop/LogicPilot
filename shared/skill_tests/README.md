# Skill pressure tests

This directory holds **pressure-test scenarios** for the load-bearing
skills in `shared/skills/`. The idea is borrowed from superpowers'
`writing-skills` methodology: a skill is only useful if it changes agent
behavior under pressure. To know that, we need:

1. **Baseline scenarios** — realistic prompts where an unguarded agent
   would do the wrong thing (skip planning, accept a hand-wavy CDC
   argument, declare done from exit-code 0).
2. **Expected guarded behaviors** — what the agent must do *with* the
   skill loaded.
3. **Static guards** — specific phrases the skill's `SKILL.md` must
   contain to make (2) reachable.

The static-guard layer runs in CI on every commit. The
agent-in-the-loop layer is manual; run it with `run_pressure.py` when
you change a load-bearing skill or before tagging a release.

## Directory layout

```
shared/skill_tests/
├── README.md                  # this file
├── conftest.py                # pytest helpers
├── scenarios/
│   ├── cdc-multibit-bus.md
│   ├── cdc-reset-deassert.md
│   ├── discipline-vague-done.md
│   ├── planning-scope-shortcut.md
│   └── planning-no-ambiguity-questions.md
├── test_skill_guards.py       # CI: each scenario's `guards` must appear in target SKILL.md
└── run_pressure.py            # manual: dispatch scenario to a real Claude subagent
```

## Scenario file format

Each scenario is a single Markdown file with a YAML front matter:

```markdown
---
target_skill: hardware-cdc
scenario: cdc-multibit-bus
title: Multi-bit bus framed as "small enough to skip Gray-coding"
guards:
  - "Multi-bit bus through **parallel** 2-FF chains"
  - "Gray-coded"
  - "async FIFO"
gate_text:
  - "MUST"
  - "Definition of done"
---

## Scenario prompt
<text the user / driver would send to the agent>

## Baseline failure modes
<bullet list of what an unguarded agent typically does wrong>

## Expected guarded behaviors
<bullet list of what the agent must do with the skill loaded>
```

The static layer (`test_skill_guards.py`) parses the YAML and asserts:

- For every string in `guards`, `shared/skills/<target_skill>/SKILL.md`
  contains it verbatim.
- For every string in `gate_text`, `shared/skills/<target_skill>/SKILL.md`
  contains it verbatim. (Catches regressions where MUST language gets
  softened during edits.)

If you remove a guard string from a SKILL.md without first removing the
scenario that relies on it, CI fails — that is the contract.

## Running

### CI / static layer (every commit)

```bash
python3 -m pytest shared/skill_tests -q
```

Runs in well under a second. Validates every scenario's `guards` /
`gate_text` against the canonical `shared/skills/` content.

### Manual / agent-in-the-loop

```bash
python3 shared/skill_tests/run_pressure.py shared/skill_tests/scenarios/cdc-multibit-bus.md
```

This is the real pressure test. By default it prints the scenario prompt
so you can paste it into a fresh agent session yourself (the cheapest,
most portable harness). If `claude` CLI is available, it can also
dispatch to it directly — see `run_pressure.py --help`.

The expected workflow:

1. **RED**: run the scenario against an agent WITHOUT the target skill
   loaded. Confirm the baseline-failure-mode bullets actually happen.
2. **GREEN**: run with the skill loaded. Confirm the guarded-behavior
   bullets actually happen.
3. **REFACTOR**: if (1) doesn't fail or (2) doesn't pass, the skill is
   wrong (too weak, or guards in the wrong spot). Edit the SKILL.md and
   re-run.

This is hand-driven on purpose: the "is the agent really doing the right
thing?" judgment is the kind of thing static checks cannot make.

## When to add a scenario

Add a scenario when:

- You catch a real-world agent regression that a skill should have
  prevented.
- You add a new MUST-level rule to a skill — write the scenario that
  would have failed without it.
- You strengthen a Definition of done — write the "declares done
  prematurely" scenario.

Don't add scenarios for everything; add them for the rules you're
willing to defend with a CI failure. The list stays short and meaningful.
