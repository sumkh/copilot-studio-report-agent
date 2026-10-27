# Working on this repository (for coding assistants and developers)

This repository builds a Copilot Studio agent (GitHub Copilot harness) that helps business users develop paginated reports, Power BI reports and semantic models. The agent is set up from this repo with the Copilot Studio VS Code extension. Read `README.md` for what the agent does and `HANDOVER.md` for how the repo moves from the personal to the enterprise GitHub.

## Layout

| Path | Role | Edit? |
|---|---|---|
| `instructions.md` | Agent instructions (text below the `---` line), with `{{PLACEHOLDERS}}` | Yes: source of truth |
| `skills/report-development/` | The skill: `SKILL.md`, `references/`, `scripts/`, `config/org-config.json` (with placeholders), `templates/` | Yes: source of truth |
| `org/org-settings.example.json` | Shape of the organisation settings | Yes |
| `org/org-settings.json` | Real organisation values. **Enterprise repo only**; git-ignored by default | Only in the enterprise repo |
| `agent/` | The agent as cloned by the Copilot Studio extension (`agent.sync.yaml`, `settings.mcs.yml`, `behaviors/`, `capabilities/`, ...) | **No.** `dev/sync_to_agent.py` writes it; the extension owns `*.mcs.yml` and `.mcs/` |
| `tools/TOOLS.md` | How to add the agent's tools in Copilot Studio | Yes |
| `evals/` | Test set, manual scripts, synthetic samples | Yes |
| `dev/` | `render.py`, `sync_to_agent.py`, `package_skill.py`, `set_repo.py`, `tests/` | Yes |
| `project.json` | Project metadata, including the current repository URL (`dev/set_repo.py` maintains it) | Through `set_repo.py` |
| `dist/` | Build output | No (git-ignored) |

## Rules

1. Change behaviour in `instructions.md` or `skills/report-development/`, never in the copies under `agent/behaviors/` or in `settings.mcs.yml`. Then run `python dev/sync_to_agent.py` to copy them into `agent/`.
2. Never edit `*.mcs.yml` sidecars or anything under `.mcs/` by hand; the extension writes them.
3. No organisation-specific values in tracked files (tenant ids, server names, people, internal URLs, label names). Use `{{PLACEHOLDERS}}` in the source and put the values in `org/org-settings.json`. The only exception is a committed `org/org-settings.json` in the enterprise repo, if that repo's policy allows it.
4. No credentials, tokens, connection strings with secrets or real customer data anywhere. Samples in `evals/samples/` are synthetic (fictional Contoso data).
5. The agent stays read-only: it never publishes, refreshes, deletes or writes to data sources. Don't add tools or script code that does.
6. Skill scripts run in Copilot Studio's sandbox (Python, no network). Keep them standard-library first; `openpyxl` and `Pillow` are optional and the scripts degrade without them.
7. Text files are UTF-8 without a byte-order mark, with LF line endings (`.gitattributes` enforces this). `SKILL.md` must keep its YAML front matter (`name`, one-line `description`).
8. When you change a script, a reference or the spec format, update the tests and run them.

## Commands

```bash
python dev/tests/run_tests.py                 # all tests (needs openpyxl; Pillow and PyYAML optional)
python dev/tests/test_handover.py             # only the handover tooling tests (standard library)
python dev/package_skill.py                   # check SKILL.md and build dist/report-development.zip
python dev/sync_to_agent.py --dry-run         # what would change in agent/ (needs org/org-settings.json)
python dev/sync_to_agent.py                   # copy skill + instructions into agent/, then Preview/Apply in the extension
python dev/sync_to_agent.py --check           # exit 1 if agent/ differs from the source
python dev/render.py --instructions           # print the instructions with organisation values filled in
python dev/set_repo.py --show                 # current repository URL and remotes
```

Optional schema checks in the tests: set `RDL_XSD` (RDL 2016/01 XSD) and `PBIR_SCHEMA_DIR` (a local mirror of github.com/microsoft/json-schemas) and install `lxml` and `jsonschema`.
