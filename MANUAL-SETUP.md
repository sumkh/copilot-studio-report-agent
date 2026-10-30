# Manual setup: copy the files into your cloned agent

Use this guide to set up the agent by copying files into the folder the Copilot Studio VS Code extension cloned. You don't need to move the Git repository (that route is in [HANDOVER.md](HANDOVER.md)).

**Starting point.** You've created an agent in Copilot Studio and connected it in VS Code. Its folder, for example `PowerBI_Developer_Agent/`, contains `.mcs/`, `settings/`, `agent.sync.yaml`, `icon.png` and `settings.mcs.yml`.

Work in this order: first everything in the portal (steps 2 and 3), then **Get changes** once, then the local files (steps 4 and 5), then **Apply** once (step 6).

## 1. Check the agent's harness

Open `settings.mcs.yml`. It should contain `template: cliagent-1.0.0` and `kind: CLICopilotRecognizer`. Together with `agent.sync.yaml`, that means the agent is on the **GitHub Copilot harness**, which skills need.

If the folder has `agent.mcs.yml` instead, it's a standard agent. Create a new agent on the GitHub Copilot harness and clone it again.

## 2. Get the files

On this repository's GitHub page, select **Code › Download ZIP** and extract it **outside** the agent folder.

If downloads are blocked, open each file on GitHub, select **Raw**, copy, and paste into a new file in VS Code. The checklist at the end lists the 42 files. VS Code saves UTF-8 without a byte-order mark by default; keep it that way, especially for `SKILL.md`.

Only `skills/report-development/` goes into the agent folder. The rest stays outside:
- `instructions.md` is pasted in step 3;
- `tools/TOOLS.md` is followed in the portal;
- `evals/` is used for testing.

## 3. In the Copilot Studio portal

1. **Settings:** turn on file uploads for the agent.
2. **Tools:** add the three tools as described in `tools/TOOLS.md`, each with end-user authentication. Write down the exact names you give them; they go into `org-config.json` in step 5.
3. **Instructions:** open `instructions.md` and copy everything **below** the `---` line. Replace the placeholders (table below), paste the text into the agent's Instructions, and save.

   | Placeholder | What to write | Example |
   |---|---|---|
   | `{{AGENT_NAME}}` | The agent's name as users see it | PowerBI Developer Agent |
   | `{{ORG_NAME}}` | Your organisation | Contoso |
   | `{{MAX_CHAT_ROWS}}` | Most rows of data shown in chat | 20 |
   | `{{OUTPUT_LOCATION}}` | Where files are saved; use the same folder as `output_root` in step 5 | the user's own OneDrive folder '/PowerBI Developer Agent' |
   | `{{RESTRICTED_LABELS}}` | Sensitivity labels the agent must not process, comma-separated | Highly Confidential |
   | `{{BI_TEAM_CONTACT}}` (appears twice) | Where users get human help | the BI Help channel in Teams |

   Before saving, search the text for `{{`; there should be none left.
4. **In VS Code,** open the Copilot Studio extension and select **Get changes**. Your instructions and tools now appear in the agent folder.

You could edit the instructions in `settings.mcs.yml` instead, but that file stores them as an indented YAML block and hand-pasting breaks it easily. The value sits under `instructions: › segments: › - kind: StaticSegment` as `value: |-`, with every line indented two spaces more than `value:`.

## 4. Copy the skill into the agent folder

In VS Code, create `behaviors/report-development/` inside the agent folder and copy the **contents** of `skills/report-development/` into it:

```
PowerBI_Developer_Agent/
├── .mcs/                          (don't touch)
├── settings/
├── agent.sync.yaml
├── icon.png
├── settings.mcs.yml
└── behaviors/
    └── report-development/        (must match "name:" in SKILL.md)
        ├── SKILL.md
        ├── config/org-config.json
        ├── references/   (23 files)
        ├── scripts/      (16 files)
        └── templates/README.md
```

Don't create any `.mcs.yml` files; the extension adds them in step 6.

## 5. Fill in `config/org-config.json` (the copy in the agent folder)

| Placeholder | What to write |
|---|---|
| `{{ORG_NAME}}`, `{{AGENT_NAME}}`, `{{BI_TEAM_CONTACT}}` | The same values as in the instructions |
| `{{TENANT_ID}}` | Your Microsoft Entra tenant ID (a GUID). It's also shown as `TenantId` in the agent's `.mcs/conn.json` |
| `{{PUBLISHING_GUIDE_URL}}` | Your intranet page on publishing Power BI content. If there isn't one, use Microsoft Learn's page on publishing from Power BI Desktop |
| `{{OUTPUT_ROOT}}` | The folder in each user's OneDrive, for example `/PowerBI Developer Agent` |
| `{{SQL_QUERY_TOOL_NAME}}`, `{{SAVE_FILE_TOOL_NAME}}` | The exact names of the SQL and Save file tools from step 3. Also check that `"fabric_iq"` matches your Fabric IQ tool's name |
| `{{RESTRICTED_LABEL_1}}`, `{{RESTRICTED_LABEL_2}}` | Label names. With only one label, remove the second entry: `["Highly Confidential"]` |

Search for `{{` afterwards. Only the `_comment` line should still mention one, and it can stay.

If the agent will build Power BI reports for users who have no Power BI sample, also add the starter template and set `pbir_starter_template` (see `templates/README.md`).

## 6. Apply

In VS Code, open the extension's **Agent Changes** view:
1. **Preview changes.** You should see the new `report-development` skill and its files.
2. **Apply changes.**
3. **Get changes.** The extension adds `skill.mcs.yml` and one `.mcs.yml` file next to each skill file. Don't edit these.

If Apply rejects some file types, zip the **contents** of `behaviors/report-development/` (with `SKILL.md` at the top of the zip). Upload it in the portal (Build › Skills › Add skill › Upload a skill), then use **Get changes**.

## 7. Test

- In the Copilot Studio test pane, upload files from `evals/samples/` and follow `evals/manual-test-scripts.md`.
- Then go to the **Evaluate** tab and upload `evals/test-set.csv`.
- Publish to Teams only after the tests pass, starting with a pilot group.

## Updating later

When the skill changes on GitHub:
1. Download it again.
2. Replace the files in `behaviors/report-development/`, **except** your filled-in `config/org-config.json`. Copy any new settings into that file by hand.
3. Delete files that no longer exist on GitHub, together with their `.mcs.yml`.
4. Preview, Apply, then Get changes.

**Shortcut, if Python 3.10+ is on the laptop.** In the extracted download, copy `org/org-settings.example.json` to `org/org-settings.json` and fill it in. Then run:

```
python dev/sync_to_agent.py --agent "C:\path\to\PowerBI_Developer_Agent"
```

It does steps 4 and 5 and the instructions for you, removes outdated files, and never touches the `.mcs.yml` files. Add `--dry-run` first to see what it would change.

## Keep company details out of the public repository

This repository is public. Never copy anything from the agent folder back into it. That includes:
- `.mcs/conn.json` (tenant, environment and agent IDs);
- your filled-in `org-config.json`;
- `settings.mcs.yml`;
- tool or connection files.

## Checklist: the 42 skill files

- `SKILL.md`, `config/org-config.json`, `templates/README.md`
- `references/01-intake.md`, `references/02-sample-analysis.md`, `references/03-sign-in-and-access.md`, `references/04-data-confirmation.md`, `references/05-spec-and-layout.md`, `references/06a-build-paginated.md`, `references/06b-build-powerbi.md`, `references/06c-build-semantic-model.md`, `references/07-validation.md`, `references/08-handoff.md`
- `references/excel-export-rules.md`, `references/message-templates.md`, `references/model-design-rules.md`, `references/query-patterns.md`, `references/report-spec.md`, `references/security-and-privacy.md`, `references/tools-usage.md`
- `references/spec-example-paginated.json`, `references/spec-example-powerbi.json`, `references/spec-example-semantic-model.json`, `references/spec-template-paginated.json`, `references/spec-template-powerbi.json`, `references/spec-template-semantic-model.json`
- `scripts/layout_preview.py`, `scripts/model_build.py`, `scripts/model_sql_check.py`, `scripts/model_validate.py`, `scripts/pbi_inspect.py`, `scripts/pbip_build.py`, `scripts/pbip_validate.py`, `scripts/rdl_build.py`, `scripts/rdl_inspect.py`, `scripts/rdl_validate.py`, `scripts/reconcile.py`, `scripts/reportkit.py`, `scripts/spec_tool.py`, `scripts/tmdl.py`, `scripts/xlsx_compare.py`, `scripts/xlsx_profile.py`
