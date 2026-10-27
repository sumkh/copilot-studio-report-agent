# Handover: personal repo → enterprise repo → Copilot Studio

This repo is developed in two places:

1. **Personal machine (now).** Preliminary development with Claude Code: the skill, scripts, instructions and tests. This repo holds no organisation values.
2. **Enterprise machine (later).** Refinement in VS Code with the Copilot Studio extension, against your enterprise Copilot Studio environment. Organisation values are added here.

Work flows one way only, from personal to enterprise. Nothing from the enterprise side (organisation settings, the cloned `agent/` folder, enterprise data) ever goes back to the personal repo.

---

## A. Personal machine: put the pack on your private GitHub

Run these in the `copilot-studio-report-agent` folder; it is the repository root.

```bash
pip install openpyxl pillow
python dev/tests/run_tests.py            # all tests should pass
python dev/package_skill.py              # checks SKILL.md; placeholders are expected here

git init -b main
git add .
git status --ignored                     # org/org-settings.json, dist/, work/ and .mcs/ must show as ignored
git commit -m "Report development agent pack"
```

1. Create an **empty private** repository on your personal GitHub (no README, licence or .gitignore).
2. Record it and set the remote:

   ```bash
   python dev/set_repo.py --url https://github.com/<you>/copilot-studio-report-agent.git
   git commit -am "Record personal repository"
   git push -u origin main
   ```

**Before every push, check:**
- No organisation values in tracked files: tenant ids, server or database names, people, internal URLs, label names. Source files keep `{{PLACEHOLDERS}}`.
- `org/org-settings.json` isn't tracked: `git ls-files org/` lists only the example.
- Only synthetic samples are present (fictional Contoso data).

**Optional.** If you have a personal Copilot Studio trial environment, you can rehearse sections D and E here too. Use a personal `org/org-settings.json` filled with test values; it's git-ignored, so it stays local.

Before handing over, tag the state you hand over: `git tag handover-1 && git push origin handover-1`.

## B. Copy the repo to the enterprise GitHub

Check your company's policy on bringing in external code first. Some enterprises require a review or a specific import route. If the enterprise GitHub uses Enterprise Managed Users, your enterprise account can't read your personal repo directly; use option 2.

Create an **empty private** repository in the enterprise GitHub organisation (no README, licence or .gitignore). Then use one of these options.

**Option 1: the enterprise machine can reach your personal repo.**

```bash
git clone https://github.com/<you>/copilot-studio-report-agent.git
cd copilot-studio-report-agent
python dev/set_repo.py --url https://github.com/<enterprise-org>/copilot-studio-report-agent.git --keep-previous-as personal
git commit -am "Move to enterprise repository"
git push -u origin main --tags
```

`--keep-previous-as personal` keeps the personal repo as a **fetch-only** remote; pushing to it is disabled. Later preliminary work comes across with `git fetch personal && git merge personal/main`. Leave the option out to drop the personal remote entirely.

**Option 2: no network path (or Enterprise Managed Users).** On the personal machine:

```bash
git bundle create report-agent-handover-1.bundle --all
```

Move the file through an approved channel. On the enterprise machine:

```bash
git clone report-agent-handover-1.bundle copilot-studio-report-agent
cd copilot-studio-report-agent
python dev/set_repo.py --url https://github.com/<enterprise-org>/copilot-studio-report-agent.git
git commit -am "Move to enterprise repository"
git push -u origin main --tags
```

Later updates use an incremental bundle: on the personal machine, run `git bundle create update.bundle handover-1..main`; on the enterprise machine, run `git pull update.bundle main`.

**Commit identity.** Commits made on the personal machine carry your personal Git name and email. If the enterprise repo must contain corporate identities only, start it from one fresh commit instead of the history. Run this before the first push, and push without `--tags`, because the tags point at the personal history:

```bash
git config user.name "Your Name" && git config user.email you@company.com
git checkout --orphan enterprise-main && git commit -m "Initial import" && git branch -M main
git push -u origin main
```

`set_repo.py` updates `project.json` (where the URL is recorded, with history) and the repository line at the end of `README.md`, and it re-points `origin`. It never pushes. Run `python dev/set_repo.py --show` to see the current state.

## C. Enterprise machine: set up VS Code

1. Open `copilot-studio-report-agent.code-workspace` (File › Open Workspace from File) and install the recommended extensions when prompted:
   - **Copilot Studio** (`ms-CopilotStudio.vscode-copilotstudio`);
   - Python;
   - TMDL.

   Sign in to the Copilot Studio extension with your enterprise account.
2. Install Python 3.10 or later, run `pip install openpyxl pillow pyyaml` (or your internal package mirror), then run `python dev/tests/run_tests.py`. PyYAML is optional. With it installed, `sync_to_agent.py --check` reads the instructions in whatever YAML style the extension writes.
3. Copy `org/org-settings.example.json` to `org/org-settings.json` and fill in your organisation's values. The tool names must match the tools you add in section D.
4. **Decide whether to commit `org/org-settings.json`.** It's ignored by default. If the enterprise repo is private and policy allows, delete its line from `.gitignore` and commit it, so teammates share one configuration.
5. **Starter template.** Add the PBIR starter template to `skills/report-development/templates/` and set `pbir_starter_template` in the settings (see `skills/report-development/templates/README.md`).

## D. Create the agent and clone it into `agent/`

The Copilot Studio web portal is still needed for what the extension can't create: the agent itself, and tool connections that need sign-in.

1. **In Copilot Studio (web),** in your development environment, create the agent on the **GitHub Copilot harness**. Skills and the Python sandbox need this harness.
   - Turn on file uploads.
   - Type any placeholder text in Instructions. The sync script replaces it.
   - Add the three tools as described in `tools/TOOLS.md`, each with end-user authentication.
2. **In VS Code,** open the Copilot Studio extension, select the environment, right-click the agent and choose **Clone agent**. Choose the `agent` folder at the repo root (create it), and the extension clones into it.
   - If the extension creates a subfolder named after the agent inside `agent/`, the sync script finds it.
   - The extension also opens the cloned folder. Go back to the workspace file afterwards.
3. **Check that the clone is a GitHub Copilot harness agent.**
   - `agent/agent.sync.yaml` and `agent/settings.mcs.yml` exist, and `agent/behaviors/` holds the skills.
   - If you see `agent.mcs.yml` instead, the agent is on the standard harness. Create it again on the GitHub Copilot harness.
4. **Commit the baseline:** `git add agent && git commit -m "Clone agent"`. The hidden `agent/.mcs/` folder (your connection, cache and change token) is git-ignored; see section F.

## E. Development loop

```bash
python dev/tests/run_tests.py            # 1. test the source
python dev/sync_to_agent.py --dry-run    # 2. see what will change in agent/
python dev/sync_to_agent.py              # 3. copy skill + instructions (org values filled in) into agent/
```

**4. In the extension's Agent Changes view:**
- **Preview changes**: review what will change in Copilot Studio.
- **Apply changes**: this updates the agent in the environment.
- **Get changes**: the extension then writes the skill's metadata (`skill.mcs.yml` and one `.mcs.yml` per file).

**5. Confirm and commit:**

```bash
python dev/sync_to_agent.py --check      # prints "In sync."
git add -A && git commit -m "..."        # source and agent/ together
```

**6. Test** in the Copilot Studio test pane, then run the evaluation set (`evals/test-set.csv`) and the manual scripts. Publishing to Teams is still done in Copilot Studio.

**Rules for the loop:**
- Change the skill and instructions only in the source (`skills/report-development/`, `instructions.md`), then sync. Edits made directly in `agent/behaviors/` or in the portal are overwritten by the next sync.
- If someone changed the skill or instructions in the portal, run **Get changes**. `sync_to_agent.py --check` then shows the drift; copy the change into the source and sync again.
- Tools, knowledge, connections and agent settings are managed in the portal or the extension, not by the sync script. After changing them, run **Get changes** and commit.

## F. Teammates and other environments

- **A teammate** clones the enterprise repo, opens the workspace and runs **Copilot Studio: Reattach Agent** on the `agent` folder. This recreates their own `.mcs/` connection. They also need `org/org-settings.json`, unless it's committed.
- **Test and production environments:** use **Copilot Studio: Reattach Agent** to point the folder at another environment, or use your Power Platform solution and pipeline process.

## G. If the extension route is blocked

- Run `python dev/package_skill.py --strict`, then upload `dist/report-development.zip` (Build › Skills › Upload a skill; if it's rejected, use `--layout folder`).
- Run `python dev/render.py --instructions` and paste the output into Instructions.

## Troubleshooting

| Message or symptom | Fix |
|---|---|
| `doesn't look like a cloned GitHub Copilot harness agent` | Clone the agent into `agent/` first, or pass `--agent <folder>` |
| `is a standard-harness agent` | Re-create the agent on the GitHub Copilot harness and clone again |
| `older packaged layout` | Use **Get changes** once (the extension converts it), then sync again |
| `no 'agentSettings:' section` | Type any text in Instructions in the portal, **Get changes**, then sync again |
| `organisation settings not found` / `missing` | Create or complete `org/org-settings.json` (section C) |
| `--check` reports changes right after Apply | Use **Get changes**, then run `--check` again |
| Preview shows changes to `.mcs.yml` files you didn't make | Use **Get changes** first, then run the sync again |
| The skill is rejected on Apply | Run `python dev/package_skill.py --strict` and fix what it reports (front matter, BOM, placeholders) |

## Compatibility note

The extension's documentation on Microsoft Learn covers standard agents. Support for GitHub Copilot harness agents (`agent.sync.yaml`, `settings.mcs.yml`, `behaviors/<skill>/SKILL.md`) is visible in the extension's source code and tests.

`sync_to_agent.py` relies only on that layout and stops with an explanation if a clone looks different. Check it on your first clone (section D, step 3). If your extension version lays agents out differently, use section G until the scripts are adjusted.
