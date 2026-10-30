# Report Development Assistant: Copilot Studio agent pack

A Microsoft Teams agent, available to everyone in the organisation, that turns a business user's existing reports (Excel, paginated, Power BI) into new Power BI **files**:
- **paginated reports (.rdl)**, typically to automate an Excel report the user then exports from the paginated report;
- **Power BI report projects (.pbip, zipped)**, live-connected to a published semantic model;
- **semantic models (Power BI Project with a TMDL model)** built from SQL, when a model is the better foundation. The user publishes the model, and the report is then built on it.

The user signs in to every data source first, and development only starts once access to all the data is confirmed. The user confirms the data and then the design before anything is built. Numbers are always checked against the user's sample. The user publishes the files themselves.

Audience: the Copilot Studio maker who sets the agent up, and the admins who approve it.

## Design decisions (confirmed)

| Decision | Detail |
|---|---|
| Power BI **service** (Fabric) | Not Power BI Report Server |
| Outputs go to **each user's own OneDrive** | Never Teams channels or shared libraries |
| Reports connect **live to published semantic models**; the agent **builds a semantic model first** when that's the better approach | Model-first plans run in two phases: model, then the user publishes, then the report on it |
| Copilot Studio **GitHub Copilot harness** | Needed for skills and the Python sandbox |
| **SQL access is required** | The agent verifies access to all data before development, builds from SQL, and validates numbers with SQL. It stops if it can't reach all the data. |
| The agent **prompts users to sign in** | Each tool shows a sign-in or connection card when needed; the agent triggers it, waits, retries, and asks again when a session expires |

## What's in this folder

| Path | What it is | Where it goes |
|---|---|---|
| `instructions.md` | Agent instructions (about 4,500 characters), with `{{PLACEHOLDERS}}` | Synced into the agent's `settings.mcs.yml` |
| `skills/report-development/` | The skill: `SKILL.md` (8-step workflow), `references/` (step guides, model design rules, message templates, security), `scripts/` (Python toolkit), `config/org-config.json` (with placeholders), `templates/` (starter template) | Synced into the agent's `behaviors/report-development/` |
| `org/org-settings.example.json` | Shape of the organisation settings. The real `org/org-settings.json` exists in the enterprise repo only | Filled into rendered copies; the source files stay generic |
| `agent/` | *(enterprise only)* The agent as cloned by the Copilot Studio VS Code extension | Preview and Apply in the extension |
| `HANDOVER.md` | Personal repo → enterprise repo → Copilot Studio, step by step | Read first on the enterprise side |
| `MANUAL-SETUP.md` | Copy the files by hand into an agent cloned with the VS Code extension | Alternative to HANDOVER.md |
| `AGENTS.md` | Rules for developers and coding assistants (Claude Code, GitHub Copilot) | |
| `tools/TOOLS.md` | Setting up Fabric IQ, the SQL query tool and Save file, with end-user sign-in; tools **not** to add | Copilot Studio › Tools |
| `evals/test-set.csv` | 35 single-turn test cases | Copilot Studio › Evaluate › upload CSV |
| `evals/manual-test-scripts.md` | Multi-turn scenarios: sign-in, access stop, model-first, security | Your test plan |
| `evals/samples/` | Synthetic sample files (fictional Contoso data) | Upload when testing |
| `cards/handoff-card.json` | Optional Adaptive Card for the handover | Only if you post cards from a flow |
| `dev/` | `render.py`, `sync_to_agent.py`, `package_skill.py`, `set_repo.py`, the test suite, optional TOM check | Your machine or CI; not uploaded |
| `project.json` | Project metadata, including the repository URL | Maintained by `dev/set_repo.py` |
| `.vscode/`, `*.code-workspace`, `.github/` | Recommended extensions and editor settings, a two-folder workspace (pack + agent), CI tests | |
| `dist/report-development.zip` | Built skill package (git-ignored) | Only for the web-portal upload route |

## How it works

```
Teams user ──► Copilot Studio agent (GitHub Copilot harness)
                │  instructions.md + skill "report-development"
                │   scripts run in the agent's sandbox (no network):
                │     analyse      xlsx_profile · rdl_inspect · pbi_inspect
                │     gates        spec_tool (confirmations + hashes; blocks unverified data)
                │     build+check  rdl_build/rdl_validate · pbip_build/pbip_validate · model_build/model_validate
                │     numbers      reconcile · model_sql_check · xlsx_compare · layout_preview
                ├─► Fabric IQ MCP ──(user's sign-in)──► Power BI semantic models / reports   (read-only)
                ├─► SQL query tool ──(user's sign-in)─► SQL Server / Azure SQL / Fabric SQL   (read-only)
                └─► Save file ──(user's sign-in)──► the user's OneDrive
User: Report Builder / Desktop (signs in to data) ─► publishes ─► exports Excel / PDF
```

**The eight steps:**
1. Intake.
2. Analyse samples and choose the approach.
3. **Sign in and check access to all data** (hard stop if anything fails).
4. **Gate A:** plan, data and fields (queries test-run).
5. **Gate B:** design, with a preview.
6. Build and validate the structure.
7. **Number check against the sample** (mandatory).
8. Hand over.

Model-first plans run steps 4–8 for the model (phase 1). After the user publishes it and sends the link, they run steps 3–8 for the report (phase 2).

The rules are enforced in code, not just in instructions. `spec_tool.py` refuses confirmations, and the builders refuse to run, when a data source isn't access-verified, a query or table hasn't been test-run, a relationship key hasn't been checked, or anything changed after the user confirmed.

## What has been tested

`dev/tests/run_tests.py` runs 19 tests. Seven of them (`dev/tests/test_handover.py`) cover the handover tooling: rendering organisation settings, packaging, and syncing into a fake agent clone modelled on the VS Code extension's GitHub Copilot harness layout. They also cover moving the repository URL and keeping the MANUAL-SETUP.md file checklist complete. The other 12 are end-to-end tests on synthetic samples:
- profiling Excel, RDL, PBIX, PBIT and PBIP files;
- gates, verification rules and change detection;
- table and matrix paginated reports;
- Power BI projects;
- semantic models, including tampered-model detection;
- SQL cross-checks;
- reconciliation, formatting comparison and previews.

During development, generated files were also validated against Microsoft's published schemas: the RDL 2016/01 XML schema (MS-RDL, section 5.8) and the PBIR/PBIP JSON schemas. The schema copies aren't included.

Generated **TMDL** follows Microsoft's documented syntax and passes `model_validate.py`. It hasn't yet been loaded by Microsoft's own parser. `dev/tests/tom_validate.ps1` does that: it downloads Microsoft's TOM library from NuGet and deserializes the model. Run it on your machine if your policies allow (loading those libraries was blocked in the environment where this pack was built).

**Not yet tested:**
- the scripts running in Copilot Studio's sandbox;
- sign-in cards and tool connections in your tenant;
- generated files opened in Power BI Report Builder and Desktop;
- publishing and refreshing a generated model.

`evals/manual-test-scripts.md` covers these. Run them before a pilot.

## Before you start

- **Copilot Studio** agent on the **GitHub Copilot harness** (usage billed in Copilot Credits).
- **Fabric IQ MCP** available in your tenant (home region supports all Fabric workloads; not sovereign clouds) and an **Entra app registration**.
- A **SQL query tool** with end-user authentication and read-only database access for users. For on-premises SQL, an on-premises data gateway. See `tools/TOOLS.md`.
- **OneDrive for Business** for every user.
- A **starter template** (PBIR) for Power BI reports and semantic model packages (`skills/report-development/templates/README.md`).
- **Users:** access to the data they report on; **Power BI Report Builder** and/or **Power BI Desktop** to test and publish. Viewers of a paginated report on a semantic model need Build permission on the model.
- **Admins:** a data (DLP) policy for the environment; gateway connections and scheduled refresh for published models; Teams app approval for organisation-wide rollout.

## Set up

The full route, from personal repo to enterprise repo to a working agent, is in **[HANDOVER.md](HANDOVER.md)**. To copy the files into an agent you've already cloned, without moving the repository, follow **[MANUAL-SETUP.md](MANUAL-SETUP.md)**. In short:

1. **Run the tests** (Python 3.10+ with `openpyxl`; `Pillow` optional): `python dev/tests/run_tests.py`.
2. **Organisation settings** (enterprise repo): copy `org/org-settings.example.json` to `org/org-settings.json` and fill it in (table below). Add the starter template (`skills/report-development/templates/README.md`).
3. **Create the agent** in Copilot Studio on the **GitHub Copilot harness**:
   - enable file uploads;
   - add the three tools (`tools/TOOLS.md`), all with end-user authentication;
   - don't add the excluded tools.
4. **Clone it** with the Copilot Studio VS Code extension into `agent/`.
5. **Sync and apply:**
   - `python dev/sync_to_agent.py` copies the skill and the instructions into `agent/` with your values filled in;
   - then, in the extension: **Preview changes** › **Apply changes** › **Get changes**;
   - commit.
6. **Test** in the test pane and in Teams with users who have different permissions (`evals/manual-test-scripts.md`).
7. **Evaluate:** Evaluate tab › upload `evals/test-set.csv`. Download Copilot Studio's CSV template first and rename the two headers if they differ. Re-run after every change.
8. **Publish to Teams:** pilot group first; then organisation-wide through the Teams admin center.

Without the extension: run `python dev/package_skill.py --strict` and upload `dist/report-development.zip` (Build › Skills › Upload a skill). Then paste the output of `python dev/render.py --instructions` into Instructions.

## Placeholders

Source files keep these placeholders so the repository carries no organisation values. `dev/render.py` fills them from `org/org-settings.json` in the copies it writes to `agent/` or `dist/`.

| Placeholder | Where | Setting in `org-settings.json` | Example |
|---|---|---|---|
| `{{AGENT_NAME}}` | instructions, config | `agent_name` | Report Builder Assistant |
| `{{ORG_NAME}}` | instructions, config | `org_name` | Contoso |
| `{{TENANT_ID}}` | config | `tenant_id` | Entra tenant GUID (used in semantic-model connection strings) |
| `{{BI_TEAM_CONTACT}}` | instructions, config | `bi_team_contact` | "the BI Help channel in Teams (bi-help@contoso.com)" |
| `{{PUBLISHING_GUIDE_URL}}` | config | `publishing_guide_url` | Your intranet page on publishing Power BI content |
| `{{OUTPUT_ROOT}}` / `{{OUTPUT_LOCATION}}` | config / instructions | `output_root` | `/Report Development Assistant` in the user's OneDrive |
| `{{SQL_QUERY_TOOL_NAME}}` | config | `tools.sql_query` | Name of the SQL tool in your agent |
| `{{SAVE_FILE_TOOL_NAME}}` | config | `tools.save_file` | Name of the OneDrive "Create file" tool |
| *(Fabric IQ tool name)* | config | `tools.fabric_iq` | Fabric IQ |
| `{{MAX_CHAT_ROWS}}` | instructions, config | `max_chat_rows` | 20 |
| `{{RESTRICTED_LABELS}}`, `{{RESTRICTED_LABEL_n}}` | instructions, config | `restricted_labels` | Highly Confidential |

Optional settings that override the skill's defaults: `allow_unprotected_copies`, `pbir_starter_template`, `sql_data_providers`, `default_style`, `default_page`, `semantic_model_defaults` and `validation`. Another one, `agent_folder`, sets where the agent is cloned (default `agent`).

## Security and governance checklist

- [ ] Every tool uses **end-user authentication**: each user signs in through their own sign-in or connection card. No shared or maker connections.
- [ ] No tool can publish, import, refresh, delete or write (see the excluded list in `tools/TOOLS.md`).
- [ ] Users reach SQL through **read-only** roles or views. `INFORMATION_SCHEMA` is readable for metadata checks.
- [ ] Files are saved only to the user's own OneDrive; there are no channel or library upload tools.
- [ ] `restricted_labels` reflects your information-protection policy; `allow_unprotected_copies` is decided.
- [ ] The DLP policy groups Fabric IQ, the SQL tool and OneDrive, and blocks other outbound connectors.
- [ ] Data residency: Copilot Studio's processing location and the selected model meet policy (samples and query results are processed by the agent).
- [ ] Transcript retention and access are configured.
- [ ] The publishing process for agent-built models is agreed (workspace, gateway, refresh, owner, sensitivity label, row-level security review).
- [ ] Pilot results reviewed: sign-in cards appeared; development never started without access; gates held; no data dumps in chat; files in the right place.

## Known limitations

- **No rendering inside the agent.** The agent can't run a paginated report or refresh a model. Before handover it checks the query results (reports) or recomputes the measures in SQL (models). After the user runs the report or refreshes the model, it checks again with their export or the published model.
- **Semantic models:** tables from SQL (import or DirectQuery), relationships, measures, a Power Query date table, formats, descriptions, hidden and sort-by columns. Not generated: row-level security roles, calculation groups, incremental refresh, Direct Lake, perspectives, translations. DAX is checked for syntax and references but only evaluated after refresh. The phase-2 check covers that.
- **Paginated layouts:** one table or matrix with title, subtitles, parameters, groups and subtotals, grand total and page footer. Charts, multiple data regions, subreports, custom code and stored procedures aren't generated.
- **Excel export fidelity:** formulas become values; pivot tables, native charts, conditional-formatting rules, AutoFilter and frozen table headers aren't produced (`references/excel-export-rules.md`).
- **Power BI reports** are cloned from a PBIR exemplar (user sample or starter template). Report-level measures, custom visuals, bookmarks and drill-through pages aren't generated.
- **Supported data sources** are Power BI semantic models (Fabric IQ) and SQL (the SQL tool). Anything else stops at the access check.
- **Fabric IQ** returns at most 1,000 rows per query (the agent aggregates) and doesn't read paginated reports (users upload the .rdl).

## Updating the pack

- Edit the skill or `instructions.md` (never the copies in `agent/`). Run `python dev/tests/run_tests.py`, then `python dev/sync_to_agent.py`. In the extension, use **Preview changes**, **Apply changes**, then **Get changes**, and commit. `python dev/sync_to_agent.py --check` confirms that `agent/` matches the source.
- Keep wording in `references/message-templates.md`, and keep organisation values in `org/org-settings.json` (not in `config/org-config.json`, which keeps placeholders).
- Re-run the evaluation after each change and compare with the previous run.
- PBIR schema versions change monthly with Power BI Desktop. The builders copy the exemplar's own schema versions, so keep the starter template saved with a current Desktop.
- Optional: save the RDL 2016/01 schema (MS-RDL section 5.8) as `skills/report-development/references/ReportDefinition.xsd`; `rdl_validate.py` then also checks against it (needs lxml in the sandbox). Check redistribution with your legal team first.

## Repository

<!-- repo:start -->
Repository (personal): https://github.com/sumkh/copilot-studio-report-agent.git
<!-- repo:end -->
