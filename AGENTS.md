# Gabay OFW — Agent Instructions

Project handoff and full context: `initial-plan-nogrilling-v0/PROJECT_HANDOFF.md` and `initial-plan-nogrilling-v0/copilot-instructions.md`.

## Agent skills

### Issue tracker

Issues are tracked in this repo's GitHub Issues via the `gh` CLI. See `docs/agents/issue-tracker.md`.
Before any tracker write, follow that guide's credential preflight: Copilot
sessions may inject a pull-only `GH_TOKEN` that overrides the writable keyring
login.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
