# Step 5 of 8: Confirm the specification and layout (Gate B)

Goal: the user explicitly confirms how the report will look and behave (or, for a semantic model, how the model is designed) after seeing a preview.

Gate A must be confirmed first (`spec_tool.py check` shows `data gate: confirmed`).

## Paginated reports: fill the spec from the samples

Use `analysis/*_profile.json` › `rdl_suggestions` (Excel sample) and/or `analysis/*_rdl.json` (existing paginated report). Field-by-field rules are in `report-spec.md`.

| Spec part | Take it from | Notes |
|---|---|---|
| `layout.page` | `rdl_suggestions.page` or the sample RDL `page` | Points: A4 landscape = 842 x 595, Letter landscape = 792 x 612 |
| `layout.title`, `layout.subtitle_lines` | Title rows above the sample table | Turn period text into expressions, e.g. `="Period: " & Format(Parameters!StartDate.Value, "MMMM yyyy")` |
| `layout.table.columns` | `rdl_suggestions.columns` in sample order | Header text exactly as in the sample; `width_pt`, `format` (.NET), `align`, `aggregate` from `aggregate_hint` |
| Calculated columns | `formula_hint` | `expression` for detail rows plus `total_expression` (ratio of sums) with `aggregate: "Expression"` |
| `layout.table.row_groups` | `group_column_candidates` + subtotal rows | `subtotal_label` copies the sample's wording, e.g. `=Fields!Region.Value & " Total"` |
| `layout.table.grand_total` | Grand-total row | Label as in the sample |
| `layout.table.detail_sort` | Row order in the sample | Usually the second key column |
| Matrix (`mode: "matrix"`) | Crosstab samples (months across, two-row headers, pivot tables) | `row_groups` (with `width_pt`, `header`), one `column_group`, `values` |
| `style` | `rdl_suggestions.style` | Fonts, colours, fills, borders, alternate-row shading; `config` › `default_style` only when there's no sample |
| `excel_export.initial_sheet_name` | Sample sheet name | Max 31 characters |
| `excel_export.notes` | Fidelity notes + format notes | See `excel-export-rules.md` |
| One sheet per group | Sample has one sheet per region, etc. | `page_break: true`, `sheet_name: "=Fields!Region.Value"`; put the title in the page header (`title.placement: page_header`) |
| `parameters` | Sample RDL, or the filters behind the sample | Business-friendly prompts; sensible defaults (e.g. previous month); multi-value lists from a values dataset |
| `validation` | Step 1 answers | `sample_file`, `sample_sheet`, `sample_parameters`, `key_columns`, `measure_columns`, tolerance |

## Power BI reports: fill the spec

- `exemplar.file`: the user's PBIR sample (`pbi_inspect` › `exemplar.usable: true`), otherwise `config` › `pbir_starter_template`. If neither exists, ask for a PBIR sample (Power BI Desktop: **File > Save as > Power BI Project**, then zip the folder).
- `pages[].visuals[]`:
  - `type`: one of the exemplar's `visual_types` (others get plain default formatting).
  - `roles`: `card`: `Values`; `tableEx`: `Values`; `pivotTable`: `Rows`, `Columns`, `Values`; bar/column/line: `Category`, `Y`, optional `Series`; `slicer`: `Values`.
  - `position`: in pixels on a 1280 x 720 page, with no overlaps.
  - `title`, and optionally `sort`.
- Keep the exemplar's look (`keep_theme`, `keep_page_background`). Exemplar report filters are dropped unless requested.

## Semantic models (phase 1): design the model

Follow `model-design-rules.md`:
- `relationships`: from each fact key column to the dimension key (many-to-one, single direction). Check the dimension key is unique with SQL (`query-patterns.md`) and record `verified_unique: true`.
- `measures`: one explicit measure for every number in the sample (sums, counts, ratios with `DIVIDE`). Use format strings from the sample, a description each, and measures stored in the fact table.
- `date_table`: `create: true`, a range that covers the fact dates (from 1 January of the earliest year to 31 December of next year), and relationships from the fact date columns (set `date_only: true` on those columns).
- `check_page`: rows = the sample's key columns; measures = the sample's numbers. This becomes the "Model check" page and DAX query.
- `exemplar`: the user's PBIR sample or the starter template (needed for the model-check page).
- `validation`: as for reports, plus `measure_map` (sample column → measure).

## Preview

- Paginated: `python3 $SKILL/scripts/layout_preview.py work/<file_name>/spec.json --out work/<file_name>/build/<file_name>_layout_preview.xlsx --rows analysis/test_result.csv` (with `--rows`: up to 20 real rows; without: placeholders).
- Power BI: `layout_preview.py ... --out work/<file_name>/build/<file_name>_wireframe.png`.
- Semantic model: `layout_preview.py ... --out work/<file_name>/build/<file_name>_model_diagram.png` (tables, key columns, measures, relationships).
- Return the preview file to the user with the Gate B message. (If the channel can't show images, an `.svg` is produced instead. Describe it in words as well.)

## Validate, summarise, ask

1. `spec_tool.py validate work/<file_name>/spec.json`: no errors allowed.
2. `spec_tool.py summary work/<file_name>/spec.json --gate spec`: include it in the Gate B message (`message-templates.md` › Gate B), with the preview.
3. Wait for the reply, and handle it exactly as in `04-data-confirmation.md` › Handle the reply, using `--gate spec`.

## Changes after confirmation

1. Copy the spec (`spec_v<N>.json`), edit, run `spec_tool.py bump`, then `spec_tool.py diff old new` to see what changed and which gate it affects.
2. Show the user only the changed items, get confirmation for the affected gate(s), and record it.
3. Rebuild. File names follow `report.version`.
