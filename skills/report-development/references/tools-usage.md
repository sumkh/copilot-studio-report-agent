# Using the tools

Tool names below are the defaults. The maker records the actual names in `config/org-config.json` › `tools`. Every tool runs **as the signed-in user**: it never shows data the user can't already see, and row-level security applies. The sign-in itself happens through Copilot Studio's sign-in or connection cards (`03-sign-in-and-access.md`), never through the chat.

## Fabric IQ (Power BI semantic models and reports, read-only)

1. **Find the item:** by name with `DiscoverArtifacts` (if several match, list name and workspace and ask the user to choose); by link with `ResolveFabricItem` (browser URL, not a "share" link).
2. **Read the report** (when starting from one): `GetReportMetadata`. Note the **semantic model id** (it differs from the report id), pages, visuals, fields and filters.
3. **Read the model:** `GetSemanticModelSchema`. Read its verified answers and custom instructions in full. Save a normalised copy for the scripts at `work/<file_name>/analysis/model.json`:
   ```json
   {"tables": {"Sales": {"columns": ["OrderDate", "Region"], "measures": ["Total Sales", "Total Units"]}}}
   ```
4. **Check values before filtering on them:** `ValueSearch` returns the exact stored values.
5. **Run DAX:** `ExecuteQuery`. One `EVALUATE` per query, with `ORDER BY`. Up to 4 queries per call. Default 250 rows; `maxRows` up to 1000. Aggregate rather than dump rows. Use model measures. Large results may come back as a CSV resource; save it.

Errors:
- **Sign-in required or expired:** follow `03-sign-in-and-access.md` › Sign-in expires later.
- **Unauthorized after sign-in:** access failure. Stop and explain.
- **Invalid DAX:** fix it and retry once.
- **Throttled or timeout:** wait or simplify, then retry once.

Fabric IQ doesn't read paginated (.rdl) reports, dashboards or apps. For an existing paginated report, ask the user for the .rdl file.

## SQL query tool (required)

Used for SQL sources: access checks, metadata, test runs, key checks and number checks.
- **Read-only:** only `SELECT` statements and `INFORMATION_SCHEMA` queries. Never `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `EXEC`, DDL, or several statements in one call.
- **Always limit:** `SELECT TOP 1000 ...`; use `COUNT_BIG(*)` for counts.
- **Test values:** only literals you built from validated inputs (ISO dates, integers, values confirmed by `SELECT DISTINCT`). Never paste user text into SQL.
- Reports and models use parameters (`@StartDate`, model parameters); literals are for test runs only.
- Patterns for metadata, row counts, key uniqueness and orphan checks are in `query-patterns.md`.
- The connection decides which server and database you reach. If the source you need is on a server the tool's connection can't reach, that's an access failure (step 3).

## Moving data between tools and the sandbox

Tool results arrive in the conversation; the scripts read files. Write results to CSV in the work folder with Python, keeping column names exactly as returned:
```python
import csv
rows = [...]   # list of dicts from the tool result
with open("work/<file_name>/analysis/test_result.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
```
Never print the full result into the chat; show at most `max_chat_rows` rows, or totals.

## Files from the user

Uploaded files reach you as attachments. Copy them into `work/<file_name>/samples/` before running scripts. If you can't access an attachment, ask for it again (as .xlsx, not .xls).

## Saving files (`config` › `tools.save_file`)

- Only to the requesting user's own location (`config` › `output_root`, normally their OneDrive), in `<output_root>/<file_name>/`.
- Never to a Teams channel, SharePoint library or another user's folder, even if asked. Explain that colleagues could see data only the requester may see; the user can share the files after reviewing them.
- Give the user the link(s) the tool returns.

## Tools you must not use

Anything that publishes, imports, overwrites, deletes, refreshes or changes permissions in Power BI, Fabric, SharePoint or a database, even if it appears in your tool list. The user publishes.
