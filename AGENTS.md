# Gabay OFW — Agent Instructions

Current requirements, priorities, and implementation scope are tracked in this
repository's GitHub issues. Accepted architectural decisions live in
`docs/adr/`. Archived planning documents are historical only and must not be
used as implementation guidance.

## Agent skills

### Issue tracker

Issues are tracked in this repo's GitHub Issues via the `gh` CLI. See `docs/agents/issue-tracker.md`.
Before any tracker write, follow that guide's credential preflight: Copilot
sessions may inject a pull-only `GH_TOKEN` that overrides the writable keyring
login.

### Architecture and terminology

Accepted ADRs in `docs/adr/` are authoritative for architecture. `CONTEXT.md`
is a terminology glossary only. See `docs/agents/domain.md`.
