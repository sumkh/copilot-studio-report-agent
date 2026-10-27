# Step 6 of 8: Build the semantic model (phase 1 of a model-first plan)

Precondition: `spec_tool.py check work/<file_name>/spec.json` shows both gates `confirmed` for the **semantic model spec**. Also needed: an exemplar for the "Model check" page, either the user's PBIR sample or `config` › `pbir_starter_template`.

## Build

```
python3 $SKILL/scripts/model_build.py work/<file_name>/spec.json --exemplar <exemplar file> \
  --out work/<file_name>/build/<file_name>_v<version>_pbip.zip --schema-out work/<file_name>/analysis/model.json
```

The package is a Power BI Project:
- `<file_name>.SemanticModel/`: `definition.pbism` and a TMDL `definition/` folder (database, model, Power Query parameters for each SQL server and database, relationships, one file per table with columns, measures and the Power Query that loads it), plus `DAXQueries/Model check.dax`;
- `<file_name>.Report/`: a one-page "Model check" report (cards and a table of the check measures) bound to the model in the same project;
- `<file_name>.pbip` and `HOW_TO_OPEN.txt`.

The model contains **no data** until the user refreshes it in Power BI Desktop, which is when they sign in to the database (see `08-handoff.md`). No credentials are stored.

## Validate the structure

```
python3 $SKILL/scripts/model_validate.py work/<file_name>/build/<file_name>_v<version>_pbip.zip
```

Must report **0 errors**. It checks:
- definition files present;
- partitions on every table; data types and source columns;
- unique names, and no measure named like a column;
- sort-by columns;
- relationships: columns exist, data types match, no duplicate or ambiguous active paths;
- the date table's key column;
- DAX syntax, and that every `'Table'[Column]` / `[Measure]` reference exists;
- Power Query parameter references;
- no credentials;
- the Model check page's fields.

What it can't check: whether the DAX evaluates correctly, and whether the SQL returns data. The first is covered by the phase-2 DAX check; the second by the test queries in step 4 and the SQL cross-check in step 7.

## Fixing problems

Errors come from the spec (a typo in a column name, mismatched key types). Fix the spec. Changes to confirmed sections need re-confirmation. Never edit the generated TMDL by hand.

## Limits to tell the user

- Model features generated: import or DirectQuery tables from SQL, relationships, measures, a Power Query date table, formats, descriptions, hidden columns, sort-by columns.
- Not generated (BI team): row-level security roles, calculation groups, incremental refresh, Direct Lake, perspectives, translations, aggregations.
- The BI team (or workspace admin) maps the published model to a gateway or cloud connection and schedules refresh.

## Then

Step 7: the SQL cross-check of the model's measures against the sample (mandatory). Then step 8: the phase-1 handover. Phase 2 (the report) starts when the user sends the published model's link.
