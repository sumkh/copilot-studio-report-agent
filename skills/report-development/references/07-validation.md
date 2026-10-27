# Step 7 of 8: Check the numbers (mandatory)

Goal: show the user, with evidence, that the new report or model produces the same numbers as their sample, and explain any difference. **You can't hand over without a number check result**: either PASS, or differences that you explained and the user accepted.

You can't render reports yourself, so the check compares the data the report or model will show. A round-trip check of the rendered export follows once the user runs it.

## Which check for which build

| Build | Check before handover | Tool |
|---|---|---|
| Paginated report on a semantic model | The report's DAX query, with the sample's parameters, vs the sample | Fabric IQ `ExecuteQuery` + `reconcile.py` |
| Paginated report on SQL | The report's SQL query, with the sample's parameters, vs the sample | SQL query tool + `reconcile.py` |
| Power BI report | DAX equivalent of the main table/chart vs the sample | Fabric IQ + `reconcile.py` |
| Semantic model (phase 1) | The model's measures recomputed in SQL from the model spec vs the sample | `model_sql_check.py` + SQL query tool + `reconcile.py` |
| Phase 2 report on the new model | The published model's "Model check" DAX vs the sample (this proves the model's DAX), then the report's own query as above | Fabric IQ + `reconcile.py` |

## Running the check

1. **Get the numbers for the sample's period and filters.**
   - Report queries: run the confirmed query with `validation.sample_parameters` substituted (test copy only). Keep the result at the sample's grain, at most 1000 rows per call. Larger samples: reconcile at a higher grain (e.g. the first key column) plus totals, and say so.
   - Semantic model (phase 1): generate the SQL:
     ```
     python3 $SKILL/scripts/model_sql_check.py work/<file_name>/spec.json --group "<Table[Column],...>" \
       --measures "<measure,...>" --date-from <from> --date-to <to> --alias "<model name>=<sample header>" ... \
       --out work/<file_name>/validation/model_check_v<N>.sql
     ```
     Run the printed query with the SQL query tool. Measures it can't translate (CALCULATE, time intelligence) are listed as notes. Tell the user they'll be checked in phase 2.
   - Phase 2: run the Model check DAX (from the model package's `DAXQueries/Model check.dax`, with the sample's filters added) through Fabric IQ.
   - Save the result as `validation/actual_v<N>.csv`.
2. **Reconcile:**
   ```
   python3 $SKILL/scripts/reconcile.py --sample samples/<sample>.xlsx --sample-sheet "<sheet>" \
     --actual validation/actual_v<N>.csv --keys "<key columns>" --measures "<measure columns>" \
     --tolerance-abs <validation.tolerance_abs> --out validation/<file_name>_reconciliation_v<N>.xlsx
   ```
   Columns are matched by header (also `Table[Column]` and `[Measure]` forms). Use `--map "Sample header=Actual header"` when names differ (for models, from `validation.measure_map`).
3. **Read the result:** `status`, `totals` per measure (and whether the sample's printed totals match its own rows), `counts`, `first_differences`.

### No sample Excel?

Cross-check against the source instead: compare the report's or model's totals by the main key with an independent query on the base tables (SQL `SUM ... GROUP BY`, or a DAX query on an existing model). Say plainly that there was no known-good sample.

## Explaining differences

Don't change a query or measure just to force a match. Find the cause, explain it, and let the user decide.

| Pattern | Likely cause | What to check |
|---|---|---|
| Every number off by a similar % | Different period, currency or unit | Date filter, parameters, the sample's title |
| A few keys missing or extra | Filters (inactive items, excluded categories), renamed members, orphan keys | `ValueSearch` / `SELECT DISTINCT`; filters in the sample RDL/report; orphan check |
| One or two values off | Data changed after the sample was produced, or manual edits in the sample | Refresh time vs sample date; `sample_internally_consistent` |
| Totals off but rows match | Hidden or filtered rows in the sample, or subtotal logic | Sample's hidden rows, SUBTOTAL vs SUM |
| Ratios off only in totals | Sum of ratios vs ratio of sums | `total_expression` / `DIVIDE` measure |
| Model numbers off, report query correct | Relationship or measure definition | Relationship keys, many-to-one direction, measure DAX |
| Rounding-level differences | Display rounding in the sample | Tolerance (agree it with the user) |

If the fix changes data sections (Gate A) or design (Gate B), show the change, get confirmation again, rebuild and re-check.

## Round-trip check (after the user runs it)

Ask the user (`message-templates.md` › Round-trip) to run the report with the **sample's parameters**:
- Paginated: open the .rdl in **Power BI Report Builder** and select **Run** (they sign in to the data source when asked), or upload it to **My workspace**; then **Export > Excel**.
- Power BI: open the .pbip in **Power BI Desktop**, then use **More options (...) > Export data** on the main visual.
- Semantic model: open the model package in Desktop, select **Refresh** (sign in to the database when asked), and check the Model check page or run the DAX query.

When they upload the export:
```
python3 $SKILL/scripts/reconcile.py --sample samples/<sample>.xlsx --actual samples/<export>.xlsx --keys ... --measures ...
python3 $SKILL/scripts/xlsx_compare.py samples/<sample>.xlsx samples/<export>.xlsx
```
`xlsx_compare` grades differences **major**, **minor** or **expected** (documented export limitations). Fix majors through the spec and rebuild. Explain the expected ones.

## Reporting

Use `message-templates.md` › Validation result: one-line verdict; a totals table (sample, new, difference); up to 5 example differences with likely causes (respect `max_chat_rows`); expected differences; the reconciliation workbook attached or saved. Never present numbers you didn't get from a tool or a file.
