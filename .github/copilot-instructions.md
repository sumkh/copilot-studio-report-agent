Follow the repository rules in [AGENTS.md](../AGENTS.md). In short:

- Edit `instructions.md` and `skills/report-development/` (the source). Never edit the copies in `agent/behaviors/`, `settings.mcs.yml`, any `*.mcs.yml` sidecar or the `.mcs/` folder; run `python dev/sync_to_agent.py` and use the Copilot Studio extension's Preview and Apply instead.
- Organisation values go in `org/org-settings.json` only; tracked source files keep `{{PLACEHOLDERS}}`.
- No credentials, secrets or real data in the repo. The agent stays read-only and never publishes.
- Skill scripts run in a sandbox without network: standard library first; UTF-8 without BOM, LF line endings.
- Run `python dev/tests/run_tests.py` after changing scripts, references or the spec format.
