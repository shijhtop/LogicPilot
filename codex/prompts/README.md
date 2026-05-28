# Codex custom prompts (fallback)

The primary Codex install path is the LogicPilot marketplace package. These
prompt files are only a fallback for local development or hosts that cannot
install the plugin package.

Fallback install: copy these `.md` files to `~/.codex/prompts/` or
`$CODEX_HOME/prompts/`. Invoke in a Codex session by typing `/lp-run`,
`/lp-sim`, or `/lp-power`.

These prompts prefer `$LOGICPILOT_FLOW`; if unset, they use a project-local
`./codex/flow/logicpilot.py` when present, then fall back to the installed
`$CODEX_HOME/logicpilot/flow/logicpilot.py`.
