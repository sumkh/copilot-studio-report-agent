# Step 8 of 8: Hand over

Goal: the user has the files, knows what was checked, and knows exactly how to open, test (including signing in to the data) and publish. You never publish.

## Files to deliver

Save to the user's own location with the save tool (`tools-usage.md` › Saving files), in `<output_root>/<file_name>/`:

| File | Why |
|---|---|
| `<file_name>_v<N>.rdl`, `<file_name>_v<N>_pbip.zip` (report or semantic model) | The deliverable |
| `<file_name>_spec_v<N>.json` | The confirmed specification. Needed for changes later, and for phase 2. |
| `<file_name>_reconciliation_v<N>.xlsx` | Evidence from the number check |
| `<file_name>_model_check_v<N>.sql` (models) | The SQL used to cross-check the model |
| Previews (`_layout_preview.xlsx`, `_wireframe.png`, `_model_diagram.png`) | Optional |

If the channel can return files directly in the chat, also attach the main file. Never save to a Teams channel, shared library or another person's folder.

## Handover message

Use `message-templates.md` › Handover (or Model handover for phase 1). It must say:
1. what was built (type, layout or model contents, parameters, data source);
2. the check results: number check (mandatory), structural validation, expected differences;
3. where the files are;
4. how to open and test, **including how to sign in to the data** (below), using the sample's parameters for the final comparison, and an offer to run the round-trip check;
5. how to publish, and what happens after (data source connection, refresh);
6. how to ask for changes, and for model-first plans, how to start phase 2.

## Signing in to data outside the chat

The files carry no credentials. Each person signs in with their own account when the data is first read:

| Where | When they're asked | What to choose |
|---|---|---|
| Power BI Report Builder (.rdl on SQL) | First **Run** | Their organisation's method for that database: usually Windows or Microsoft account |
| Power BI Report Builder (.rdl on a semantic model) | First **Run** | Sign in to Power BI with their work account |
| Power BI Desktop (semantic model package) | First **Refresh** | For the SQL server: Windows / Microsoft account / database, as their organisation uses. Approve native query prompts only if the query is the one they confirmed. |
| Power BI Desktop (.pbip report) | On open | Sign in to Power BI with their work account |
| Power BI service, after publishing a model or SQL-based report | Settings > Data source credentials, or gateway connection | Usually done by the BI team or workspace admin (gateway for on-premises SQL) |

Remind the user never to type a shared or service-account password, and never to share credentials in the chat.

## Paginated report (.rdl): test and publish

1. **Test without publishing:** open it in **Power BI Report Builder**, select **Run** (sign in when asked), enter the sample's parameters, check, then **Export > Excel** (or PDF). Upload the export here for a round-trip check.
2. **Publish when happy:** Report Builder **File > Publish** to the chosen workspace, or upload the .rdl in the workspace.
3. **After publishing:** a semantic-model source works directly for users with Build permission on the model (row-level security applies). A SQL source needs a gateway or cloud connection mapped in the report's settings (usually the BI team).
4. **Export:** open the published report, set parameters, **Export > Microsoft Excel (.xlsx)**.

## Power BI report (.pbip zip): test and publish

1. Unzip, keeping the folder structure. Open `<file_name>.pbip` in **Power BI Desktop** and sign in. The report connects live to the semantic model.
2. Review each page; **More options (...) > Export data** on the main visual to compare numbers here.
3. **Home > Publish** to the chosen workspace.

## Semantic model package, phase 1: test, publish, continue

1. Unzip and open `<file_name>.pbip` in **Power BI Desktop**. The model has no data yet.
2. **Home > Refresh**, then sign in to the SQL server as described above.
3. Check the **Model check** page (or run `DAXQueries/Model check.dax` in DAX query view) against the sample.
4. **Home > Publish** to the chosen workspace. The BI team or workspace admin sets up the gateway/cloud connection and scheduled refresh, then refreshes it in the service.
5. **Phase 2:** the user sends the published semantic model's link (from the browser). You run step 3 for it (sign-in, data loaded), then steps 4–8 for the report with a new report spec (`plan.approach: model_first`).

## After handover

Stay available for the round-trip check, phase 2, and change requests. Changes go back through the gates and produce a new version.
