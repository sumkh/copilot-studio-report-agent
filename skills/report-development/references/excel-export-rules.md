# How paginated reports export to Excel

The user will export the report to Excel themselves. Use these facts (from Microsoft's documentation of the Excel renderer) when you design the layout and when you set the user's expectations at Gate B. Put the relevant ones in `excel_export.notes`.

## What the export does

- **Values, not formulas.** Every textbox is evaluated by the report; Excel receives the value. The sample's `=SUM()`, `=SUBTOTAL()` or ratio formulas become numbers.
- **One textbox = one cell.** Fonts, font size, bold/italic, colours, fills, borders and number formats carry over. Number formats are converted from .NET to Excel; most Excel formats (`#,##0.00`, `0.0%`, `dd/MM/yyyy`) round-trip unchanged.
- **Merged cells appear when items don't line up.** The renderer keeps the layout by merging cells. The builder prevents this: whole-point sizes, title boxes exactly as wide as the table, everything left-aligned at 0.
- **Page header to the top rows of each sheet.** By default the page header is written into the sheet's first rows, which become locked rows. The table's own header row is **not frozen** in the export.
- **Page footer to Excel's print footer.** Not visible in the grid. Max 256 characters.
- **Sheets come from page breaks.** The first sheet is named by `InitialPageName` (`excel_export.initial_sheet_name`). A group with `page_break` + `sheet_name` creates one sheet per value (duplicates get a number suffix). Sheet names: max 31 characters, no `[ ] : * ? / \`.
- **Row groups with header columns leave blank cells** under the group value. Our table layout repeats the group value on every detail row (`repeat_group_values: true`) so the sheet stays sortable and filterable. Use `false` only if the user wants the "grouped look".
- **Charts, sparklines, data bars, gauges and maps export as pictures.** Their data isn't in the workbook.
- **Not produced:** pivot tables, native Excel charts, conditional-formatting rules (the export has the resulting static colours), data validation, AutoFilter, comments, frozen table headers, grouping outlines (except for toggled items), hidden columns.
- **Page setup:** paper size is matched from the report page size; orientation is landscape when the page is wider than tall.
- Excel adds about 3.75 pt padding inside cells. Columns barely wide enough for their text may wrap. The widths copied from the sample are usually fine.
- Limits: 1,048,576 rows and 16,384 columns per sheet; 32,767 characters per cell; row height max 409 pt.

## Design rules (the builder follows them; keep them when you write specs)

1. One table or matrix per sheet; title and subtitle lines above it, same width.
2. Column widths and row heights in whole points (`width_pt`, `row_height_pt`).
3. Header text exactly as in the sample; number formats from the sample profile.
4. Subtotal and grand-total rows styled like the sample (bold, fill, top border).
5. If the user needs one sheet per group (e.g. per region), use `page_break` + `sheet_name` and put the title in the page header.
6. If the sample has frozen panes, an AutoFilter or formulas, tell the user at Gate B that the export won't have them. Excel's "Freeze Panes" and "Filter" take two clicks after export.

## Typical Gate B notes

- "Excel formulas in your sample (Margin %, the SUBTOTAL rows) will be exported as values."
- "The column headers won't be frozen in the export; the title rows at the top will be."
- "The pivot table on sheet 'Summary' can't be reproduced; I'll lay it out as a crosstab (matrix) with the same rows and columns."
- "Your sample's custom colour rule (negative numbers in red) becomes a font colour rule in the report; Excel will show the colours but not a conditional-formatting rule."
