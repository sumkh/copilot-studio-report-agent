# The spec (`spec.json`)

The spec is the contract between the user and the build scripts. Create it with `spec_tool.py new --type paginated|powerbi|semantic_model`. Full examples: `spec-example-paginated.json`, `spec-example-powerbi.json`, `spec-example-semantic-model.json`.

| Type | Gate A (data) | Gate B (spec) |
|---|---|---|
| `paginated` | `plan`, `data_sources`, `datasets` | `report`, `parameters`, `layout`, `style`, `excel_export`, `validation` |
| `powerbi` | `plan`, `data_sources`, `fields` | `report`, `exemplar`, `pages`, `style`, `validation` |
| `semantic_model` | `plan`, `data_sources`, `tables` | `report`, `relationships`, `measures`, `date_table`, `check_page`, `exemplar`, `validation` |

Keys named `verified`, `access_verified`, `verified_unique` and `agent_notes` are bookkeeping: changing them doesn't invalidate a gate. Any other change in a gate's sections does.

**Verification is required.** `spec_tool.py` reports errors (so gates can't be confirmed and nothing can be built) unless:
- every `data_sources[]` has `access_verified: true`, set after the access check in step 3;
- every paginated `datasets[]` has `verified.executed: true`, and every model `tables[]` has `verified.executed: true`, set after a successful test query;
- every model relationship has `verified_unique: true`, set after the SQL key check.

`plan`: `{"approach": "direct" | "model_first", "next": "paginated" | "powerbi" (model_first only), "reason": "..."}`. A `semantic_model` spec always has `approach: "model_first"`. The phase-2 report spec repeats the plan with `approach: "model_first"` and uses the published model as its data source.

## Common

| Key | Meaning |
|---|---|
| `spec_version` | `"1.0"` |
| `report_type` | `"paginated"` or `"powerbi"` |
| `report.name` | Display name |
| `report.file_name` | File base name: letters, digits, space, `_ . - ( )` |
| `report.description`, `report.requested_by` | Shown in the report's properties |
| `report.primary_export` | Paginated: `"excel"` or `"pdf"` |
| `report.version` | Integer; `spec_tool.py bump` increases it after a change |
| `report.language` | Optional culture, e.g. `"en-GB"` (affects default date/number display) |
| `samples[]` | `{"file", "role"}` for each sample used |
| `open_questions[]` | Anything unresolved; shown at both gates |
| `confirmations` | Written only by `spec_tool.py confirm` |

## Paginated: data (Gate A)

`data_sources[]`: `name` (identifier), `kind` (`powerbi_semantic_model`, `sql`, ...), `data_provider` (`PBIDATASET`, `SQL`, `SQLAZURE`, ...), `connect_string` (no credentials), `display`, `identified_from`, `access_verified`, optional `integrated_security`.

`datasets[]`: `name`, `data_source`, `query_language` (`DAX`/`SQL`), `command_text`, `query_parameters[]` (`{"name", "value"}`; DAX names without `@`, SQL with `@`), `fields[]` (`{"name", "data_field", "type", "description"}` or a calculated field `{"name", "value": "=..."}`; `type`: `String`, `Integer`, `Float`, `Decimal`, `DateTime`, `Boolean`), `verified`.

## Paginated: specification (Gate B)

`parameters[]`:

| Key | Values |
|---|---|
| `name` | Identifier, used as `Parameters!<name>.Value` |
| `data_type` | `String`, `Integer`, `Float`, `DateTime`, `Boolean` |
| `prompt` | Business-friendly label |
| `default` | Expression or literal, or a list for multi-value |
| `default_from_dataset` | `{"dataset", "value_field"}` (e.g. all regions) |
| `valid_values` | `{"dataset", "value_field", "label_field"}` or `{"static": [{"value", "label"}]}` |
| `multi_value`, `allow_blank`, `nullable`, `hidden` | Booleans |

`layout.page`: `orientation`, `width_pt`, `height_pt`, `margins_pt` `{top, bottom, left, right}`.
`layout.title`: `text`, `placement` (`body` = top of the first sheet/page; `page_header` = every page/sheet).
`layout.subtitle_lines[]`: text or expressions.
`layout.footer`: `page_number` (bool), `execution_time` (bool), `text`.

`layout.table` (`mode: "table"`):

| Key | Meaning |
|---|---|
| `dataset` | Dataset name |
| `columns[]` | `header`, `field` **or** `expression`, `width_pt`, `format` (.NET), `align` (`Left`/`Center`/`Right`/`General`), `aggregate` (`Sum`, `Avg`, `Min`, `Max`, `Count`, `CountDistinct`, `Expression`, or `null`), `total_expression` (required for `Expression`), optional `color`/`background`/`font_weight` (value or expression, detail rows) |
| `row_groups[]` | Outer to inner: `field`, `subtotal` (bool), `subtotal_label` (text or expression), `sort` (`Ascending`/`Descending`), `sort_expression`, `page_break` (bool), `sheet_name` (expression) |
| `detail_sort[]` | `{"field", "direction"}` |
| `grand_total` | `{"show", "label"}` |
| `repeat_header_rows`, `repeat_group_values` | Booleans (default true) |
| `header_row_height_pt`, `row_height_pt` | Defaults 20 and 15 |

`layout.table` (`mode: "matrix"`): `row_groups[]` (`field`, `header`, `width_pt`, `subtotal`, `subtotal_label`, `sort`), `column_group` (`field`, `sort_expression`, `header_expression`, `total`, `total_label`), `values[]` (`header`, `field` or aggregate `expression`, `aggregate` default `Sum`, `format`, `width_pt`, `align`), `grand_total`, row heights.

`style`: `font_family`, `font_size_pt`, and parts `title`, `subtitle`, `header`, `detail`, `subtotal`, `grand_total`, each with any of `font_family`, `font_size_pt`, `font_weight` (`Bold`/`Normal`), `font_style` (`Italic`/`Normal`), `underline`, `color`, `background`, `border_style` (`None`/`Solid`/`Dashed`/`Dotted`/`Double`), `border_color`, `border_width_pt`, `border_sides` (subset of `top`,`bottom`,`left`,`right`), `text_align`, `vertical_align` (`Top`/`Middle`/`Bottom`), `wrap`. Plus `alt_row_background` (detail rows alternate).

`excel_export`: `initial_sheet_name`, `notes[]`.

`validation`: `sample_file`, `sample_sheet`, `sample_parameters` (`{"StartDate": "2026-09-01"}`), `key_columns[]` and `measure_columns[]` (sample header names), `tolerance_abs`, `tolerance_rel`.

## Power BI

Gate A: `data_sources[0]` (`kind: powerbi_semantic_model`, `workspace`, `model_name`, `model_id`, or `pbir_connection_string`), `fields[]` (`id`, `table`, `name`, `kind` `column`/`measure`, `description`).

Gate B: `exemplar` (`file`, `keep_theme`, `keep_page_background`, `keep_report_filters`); `pages[]` (`name`, `width`, `height`, `visuals[]` with `type`, `title`, `roles` {role: [field ids]}, `position` {x, y, width, height}, optional `sort` {field id, direction}); `style.notes`; `validation`.

## Semantic model

Gate A:
- `data_sources[]` (`kind: sql`, `server`, `database`, `display`, `identified_from`, `access_verified`).
- `tables[]`:
  - `name`, `role` (`fact`/`dimension`), `description`, `data_source`;
  - `source` (`{"schema", "object"}` for a table or view, or `{"query": "SELECT ..."}`);
  - `mode` (`import`/`directQuery`);
  - `verified`;
  - `columns[]`: `name`, `source_column`, `data_type` (`string`, `int64`, `double`, `decimal`, `dateTime`, `boolean`), `date_only`, `format`, `hidden`, `summarize_by` (`none`, `sum`, `count`, `min`, `max`, `average`, `distinctCount`), `sort_by`, `is_key`, `description`, or `expression` (DAX calculated column, with `data_type`).

Gate B:
- `relationships[]`: `from_table`, `from_column` (many side), `to_table`, `to_column` (one side), `active`, `cross_filter` (`single`/`both`), `verified_unique`.
- `measures[]`: `table`, `name`, `expression` (DAX), `format`, `description`, `display_folder`, `hidden`.
- `date_table`: `create`, `name`, `start`, `end` (YYYY-MM-DD), `relationships[]` (`table`, `column`, `active`).
- `check_page`: `rows[]` (`table`, `column`) and `measures[]`. Builds the "Model check" page and DAX query.
- `exemplar`: `file`, for the Model check page's look.
- `validation`: as for reports, plus `measure_map` (sample header → measure name).
- `report.culture` (default `en-US`) and `report.compatibility_level` (default 1567).
