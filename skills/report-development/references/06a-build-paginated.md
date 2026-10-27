# Step 6 of 8: Build the paginated report

Precondition: `python3 $SKILL/scripts/spec_tool.py check work/<file_name>/spec.json` prints both gates as `confirmed`. If not, go back to the gate it names. Never try to get around the check.

## Build

```
python3 $SKILL/scripts/rdl_build.py work/<file_name>/spec.json --out work/<file_name>/build/<file_name>_v<version>.rdl
```

The builder writes an RDL 2016/01 file that Power BI Report Builder and the Power BI service open:
- embedded data source(s) and dataset(s) from the spec; credentials are never written;
- report parameters with prompts, defaults and value lists, and a parameter panel layout;
- the title block (in the body, or in the page header if `title.placement` is `page_header`), the table or matrix, and a page footer with page numbers;
- all sizes in whole points, aligned edges, and title boxes the same width as the table, to keep Excel exports free of merged cells;
- `InitialPageName` for the Excel sheet name, and `PageName` per group when groups start new sheets.

## Validate the structure

```
python3 $SKILL/scripts/rdl_validate.py work/<file_name>/build/<file_name>_v<version>.rdl
```

It must report **0 errors**. It checks tablix integrity (member counts, cells per row, corner, header depth), unique names, field/parameter/report-item references, query parameter naming (`@` for SQL, none for DAX), embedded credentials, shared data sources, expression syntax and page fit. If `references/ReportDefinition.xsd` and lxml are present, it also validates against Microsoft's schema.

Warnings to act on:
- *body width + margins exceeds page width*: PDF output gets blank extra pages. Narrow the columns or switch to landscape (a spec change, so it needs Gate B confirmation).
- *query parameter not used in the query*: check the dataset query.

## Fixing problems

- Validator errors come from the spec. Fix the spec and rebuild. If the fix touches a confirmed section, the build refuses until the user re-confirms; show them the change (`spec_tool.py diff`).
- Never edit the generated .rdl by hand to pass validation.
- Outside what the builder can express (charts, several data regions on a page, subreports, custom code, stored procedures): tell the user. Offer the closest supported layout, or a handover to the BI team with the spec and analysis.

## Then

Tell the user in one short message what was built and that the structure check passed, then go straight to step 7. The number check is mandatory before handover.
