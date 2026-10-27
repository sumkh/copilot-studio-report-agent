# Step 6 of 8: Build the Power BI report project

Precondition: `spec_tool.py check work/<file_name>/spec.json` shows both gates `confirmed`. The report connects live to a **published** semantic model: an existing one, or the one built in phase 1 of a model-first plan and published by the user.

## Exemplar

`pbip_build.py` clones an **exemplar** report in PBIR format so the new report gets the same theme, page settings and visual formatting:
1. the user's sample, if `pbi_inspect.py` reported `exemplar.usable: true`;
2. otherwise the starter template in `config/org-config.json` › `pbir_starter_template`;
3. otherwise stop and ask for a PBIR sample (Power BI Desktop: **File > Save as > Power BI Project**, then zip the folder).

Visual types missing from the exemplar are created as plain visuals with default formatting; the builder warns you. Tell the user.

## Build

```
python3 $SKILL/scripts/pbip_build.py work/<file_name>/spec.json --exemplar <exemplar file> --out work/<file_name>/build/<file_name>_v<version>_pbip.zip
```

- `<file_name>.pbip` and `<file_name>.Report/`, with `definition.pbir` bound live to the semantic model (`byConnection`).
- The exemplar's report settings, theme files and static resources are copied.
- Each page and visual is built from the exemplar's matching visual type, keeping formatting that isn't tied to the exemplar's own fields, and bound to the confirmed fields.
- The exemplar's report filters (unless `keep_report_filters`), bookmarks, report-level measures and field-specific formatting are dropped.
- A `HOW_TO_OPEN.txt` file is included.

## Validate the structure

```
python3 $SKILL/scripts/pbip_validate.py work/<file_name>/build/<file_name>_v<version>_pbip.zip --model-schema work/<file_name>/analysis/model.json
```

Must report **0 errors**: package structure, names and folders, page bounds, and every table/column/measure existing in the semantic model. `analysis/model.json` comes from `GetSemanticModelSchema` (normalised; see `tools-usage.md`) or, in phase 2, from `model_build.py --schema-out`.

## Limits to tell the user

- Opening, reviewing and publishing needs **Power BI Desktop** (a current version with PBIR support).
- Report-level measures from the sample aren't carried over. Use model measures, or add them to the model (model-first plan).
- Custom visuals, bookmarks, drill-through and tooltip pages, and field parameters aren't generated.
- Fine-tuning (exact fonts per visual, conditional formatting) is done in Desktop.

## Then

Short build message, then step 7 (number check with DAX equivalent to the main visuals: mandatory).
