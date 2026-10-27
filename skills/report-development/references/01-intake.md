# Step 1 of 8: Intake

Goal: before any design work, get the user's goal and their sample reports. Samples tell you the data sources, the fields, the layout and formatting to copy, and the numbers the new report must reproduce.

## Your first reply to a new report request

Don't start designing. Ask for these, in one short message (template: `message-templates.md` › Intake):

1. **What the report is for:** who uses it, how often, and the output they need (Excel file, PDF, or an interactive Power BI report).
2. **Samples:** whatever they have, the more the better:
   - **The Excel report they produce today** (.xlsx): ideally a recent, final version. Ask which **period and filters** produced it (e.g. "September 2026, all regions"). You need these to check the numbers.
   - **The current paginated report** (.rdl), if one exists. It names the data sources and queries.
   - **The Power BI report** it comes from: the link from the browser address bar (not a "share" link) and/or the file.
   - Optional: a screenshot or PDF of the layout they want.
3. **What should differ from the sample**: new columns, filters, grouping, layout changes.

Tell them how to get the files (only the ones relevant to them):

| File | How to get it |
|---|---|
| Paginated report (.rdl) from the Power BI service | Use the report's **Download** option (in the open report's File menu, or under **More options (...)** next to it in the workspace; needs edit rights). Or open it in Power BI Report Builder and use **File > Save As**. |
| Paginated report from Report Server / SSRS | In the web portal, open **...** on the report, then **Download**. |
| Power BI report, live-connected (thin) | The browser link, plus optionally **File > Download this file** (.pbix). |
| Power BI report with its own (import) model | In Power BI Desktop: **File > Export > Power BI template** (.pbit). It contains the model's tables, measures and queries, without data. Or **File > Save as > Power BI Project (.pbip)** and zip the folder. |
| Excel built with "Analyze in Excel" or Power Query | Just the .xlsx: the connection details are inside the file. |

## File checks (do these as soon as files arrive)

- **Supported:** .xlsx, .xlsm (macros are never run), .csv (data only, no formatting), .rdl, .rds, .rsd, .pbix, .pbit, .zip (Power BI Project), .pdf/.png/.jpg (layout reference only).
- **Legacy .xls:** ask the user to save it as .xlsx.
- **Encrypted or password-protected files** can't be read. Ask for an unprotected copy only if your organisation's policy allows it (`config/org-config.json` › `sensitivity.allow_unprotected_copies`).
- **Sensitivity labels:** after profiling an Excel file, check `workbook.sensitivity_labels`. If a label is in `sensitivity.restricted_labels`, stop: tell the user this assistant can't process that file and suggest they contact the BI team.
- **Credentials in files:** if a file contains a password or key (the scripts flag this), tell the user, don't repeat it, and suggest they remove it from the file.

## Decide the output type

| The user wants... | Build |
|---|---|
| "Automate this Excel report", printable pages, exact layout, long lists, PDF | Paginated report (.rdl). The user exports Excel/PDF from it. |
| Interactive exploration, slicers, charts, drill-down | Power BI report (.pbip) on a published semantic model |
| Not sure | Recommend paginated for "produce this file regularly" requests; Power BI for "explore and analyse" requests. Confirm with the user. |

If no suitable semantic model exists, or the numbers are reused or need business logic, you may propose building a **semantic model first** and then the report on it (model-first plan; decided in step 2, see `model-design-rules.md`).

Tell the user early that in step 3 they'll be asked to **sign in to each data source with their own account**, and that development only starts once access to all the data is confirmed.

## Minimum to continue to step 2

- The goal, and
- at least one sample, **or** a semantic model / report link, or a server and database name the user can access, plus a description of the layout.

If the user has no Excel sample, say that you can still build the report but can only check numbers against the data source itself, not against a known-good report. Record this in `spec.samples` as `[]` and in `open_questions`.

Collect for the spec: report name (`report.name`, `report.file_name`), the requester's name (`report.requested_by`), and the sample's period and filters (`validation.sample_parameters`).
