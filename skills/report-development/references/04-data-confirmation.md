# Step 4 of 8: Confirm the data (Gate A)

Goal: the user explicitly confirms the **plan** and **which data sources and fields** will be used, after you've test-run the queries.

Precondition: step 3 passed for every source. If any source isn't verified, go back to step 3. You can't confirm or build anything on unverified data, and `spec_tool.py` rejects it.

## 1. Map fields and check values

- Match each sample column to a field: a table/column/measure in the semantic model (from `GetSemanticModelSchema`), or a SQL column (from `INFORMATION_SCHEMA.COLUMNS`, see `query-patterns.md`). Prefer **model measures** over re-implementing logic.
- For values the report filters or groups on (regions, products), check they exist: `ValueSearch` (models) or `SELECT DISTINCT ... WHERE ... = '...'` (SQL).
- For a SQL source, start from the sample's query (RDL dataset or Power Query `[Query="..."]`).

## 2. Write and test-run the queries

### Paginated report (direct, or phase 2 on a new model)
Follow `query-patterns.md`. Test-run with the sample's period and filters (`validation.sample_parameters`):
- semantic model: Fabric IQ `ExecuteQuery`, with literals substituted in a **test copy** of the DAX; `maxRows` ≤ 1000; aggregate to the report's grain;
- SQL: the SQL query tool, `SELECT TOP 1000 ...` with literal test values.

Save the result as `analysis/test_result.csv` (column names exactly as returned). Record `datasets[].verified = {"executed": true, "rows": N, "at": "<UTC>", "notes": "<what you ran>"}`. Early check (recommended): `reconcile.py` against the sample. Investigate differences now (`07-validation.md`) and explain them at the gate.

### Power BI report
No dataset query. Test the main numbers with the DAX equivalent of the main visual (`SUMMARIZECOLUMNS` of its fields) and note the result in the spec's `fields[].description` or `agent_notes`.

### Semantic model (phase 1 of a model-first plan)
Follow `model-design-rules.md`:
1. List the columns and types of each table or view: `INFORMATION_SCHEMA.COLUMNS`.
2. Choose only the columns the reports need, plus keys. Name them for business users. Map SQL types to model types.
3. Row counts per table (`COUNT_BIG(*)`), date range of the fact table, orphan keys (facts without a matching dimension row).
4. Record `tables[].verified = {"executed": true, "rows": N, "at": ..., "notes": ...}` for every table.

## 3. Write the data part of the spec

```
python3 $SKILL/scripts/spec_tool.py new --type paginated|powerbi|semantic_model --name "<name>" --out work/<file_name>/spec.json
```

Always fill `plan`:
- `{"approach": "direct", "reason": "..."}`: the report reads an existing semantic model or SQL directly.
- `{"approach": "model_first", "next": "paginated" | "powerbi", "reason": "..."}`: phase 1 builds a semantic model; phase 2 builds the report on it once published. Use the criteria in `model-design-rules.md`, and make the reason concrete (reuse, business logic, security, performance).

Then fill the data sections (`report-spec.md`):
- `data_sources[]` with `access_verified: true` (only after step 3 passed);
- paginated: `datasets[]` (query, `query_parameters`, `fields`, `verified`); Power BI: `fields[]`; semantic model: `tables[]` (source object or query, mode, columns, `verified`);
- connection details:
  - semantic model (paginated): `data_provider` `PBIDATASET`, `connect_string` `Data Source=pbiazure://api.powerbi.com/;Identity Provider="https://login.microsoftonline.com/common, https://analysis.windows.net/powerbi/api, <tenant_id>";Initial Catalog=sobe_wowvirtualserver-<model_id>;Integrated Security=ClaimsToken` (copy it from a sample RDL when there is one);
  - SQL (paginated): `data_provider` from the sample RDL or `config` › `sql_data_providers`, `connect_string` `Data Source=<server>;Initial Catalog=<database>`;
  - SQL (semantic model): `server`, `database`;
  - Power BI report: `workspace`, `model_name`, `model_id` (or `pbir_connection_string`).

Check: `spec_tool.py validate work/<file_name>/spec.json --gate data` must report no errors.

## 4. Ask for confirmation

`spec_tool.py summary work/<file_name>/spec.json --gate data`, then send it in the Gate A message (`message-templates.md` › Gate A), with the test-run results and anything approximate. Wait for the reply. Don't present Gate B in the same message.

## 5. Handle the reply

- **Clear approval** ("CONFIRM DATA", "Yes, confirmed", "Approved"):
  `spec_tool.py confirm work/<file_name>/spec.json --gate data --reply "<the user's exact words>" --by "<user name>"`.
  If the approval contains words like "no" or "change" ("No changes, confirmed"), add `--reply-is-approval`.
- **Any change request**, even alongside "looks good": apply it, re-test, show what changed (`spec_tool.py diff`), ask again.
- **A question:** answer it, then ask for confirmation again.
- **Unclear:** ask "Shall I take that as confirmation of the plan, data sources and fields above?"

Never record a confirmation without a user reply that approves the summary you showed.
