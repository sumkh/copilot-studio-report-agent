# Query patterns for paginated report datasets

The dataset query lives in `datasets[].command_text`; its fields in `datasets[].fields` (`name` = report field, `data_field` = column name exactly as the query returns it).

## DAX on a Power BI semantic model (`data_provider: PBIDATASET`)

### Shape
```dax
DEFINE
    VAR __Start = DATEVALUE(@StartDate)
    VAR __End   = DATEVALUE(@EndDate)
EVALUATE
    SUMMARIZECOLUMNS(
        'Geography'[Region],
        'Product'[Category],
        FILTER(ALL('Date'[Date]), 'Date'[Date] >= __Start && 'Date'[Date] <= __End),
        "Units", [Total Units],
        "Sales Amount", [Total Sales]
    )
ORDER BY 'Geography'[Region], 'Product'[Category]
```
- Group by exactly the columns the layout needs; aggregate with **model measures**.
- Field mapping: group-by column `'Geography'[Region]` → `data_field: "Geography[Region]"`; named measure column `"Sales Amount"` → `data_field: "[Sales Amount]"`. Report field `name` must be an identifier (`SalesAmount`).

### Parameters
- Query parameter **names have no `@`** (`"name": "StartDate"`). The DAX text references them as `@StartDate`.
- Pass dates as text and convert in DAX: query parameter value `=Format(Parameters!StartDate.Value, "yyyy-MM-dd")`, DAX `DATEVALUE(@StartDate)`.
- Single value: `TREATAS({@Region}, 'Geography'[Region])` as a SUMMARIZECOLUMNS filter argument.
- Multi-value, option 1 (portable): value `=Join(Parameters!Region.Value, "|")`, filter `FILTER(ALL('Geography'[Region]), PATHCONTAINS(@Region, 'Geography'[Region]))`.
- Multi-value, option 2 (Report Builder's DAX designer): `RSCustomDaxFilter(@Region, EqualToCondition, [Geography].[Region], String)` as a filter argument, expanded at run time. It can't be test-run through Fabric IQ, so prefer option 1.
- Value lists for parameters: a second dataset `EVALUATE VALUES('Geography'[Region]) ORDER BY 'Geography'[Region]` with field `Region` / `data_field: "Geography[Region]"`; use it in `valid_values` and, for "all selected by default", `default_from_dataset`.

### Test runs through Fabric IQ
Replace each `@Param` with a literal in a **test copy**: `DATEVALUE("2026-09-01")`, `"EMEA"`, `PATHCONTAINS("EMEA|APAC", ...)`. Run it with `ExecuteQuery`. The spec keeps the parameterised version.

### Don'ts
- No `INFO.*` functions or DMVs. Fabric IQ doesn't support them, and reports shouldn't depend on them.
- Don't re-implement a measure that the model already has.
- Avoid row-level dumps. If the report really is a detail listing, include only needed columns and filter by parameters.

## SQL (`data_provider: SQL`, `SQLAZURE`, or as in the sample RDL)

```sql
SELECT r.RegionName AS Region, p.Category AS ProductCategory,
       SUM(f.Units) AS Units, SUM(f.SalesAmount) AS SalesAmount
FROM dbo.FactSales AS f
JOIN dbo.DimRegion  AS r ON r.RegionKey  = f.RegionKey
JOIN dbo.DimProduct AS p ON p.ProductKey = f.ProductKey
JOIN dbo.DimDate    AS d ON d.DateKey    = f.DateKey
WHERE d.[Date] BETWEEN @StartDate AND @EndDate
  AND r.RegionName IN (@Region)          -- multi-value parameters expand automatically
GROUP BY r.RegionName, p.Category
ORDER BY r.RegionName, p.Category;
```
- Query parameter **names start with `@`** and match the SQL text; values `=Parameters!StartDate.Value`.
- Alias every column to its report field name; no `SELECT *`.
- Reuse the sample's query (RDL dataset or Power Query `[Query="..."]`) where possible; change only what the user asked for.
- Stored procedures aren't supported by the builder; ask the BI team or rewrite as a SELECT.

## SQL checks (access, metadata, model design)

Run them with the SQL query tool (read-only). Replace names with the real schema/table/column.

```sql
-- Access check (step 3), once per table or view the report/model uses
SELECT TOP 1 1 AS ok FROM dbo.FactSales;

-- Columns and types (step 4)
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'FactSales'
ORDER BY ORDINAL_POSITION;

-- Row count and date range of a fact table
SELECT COUNT_BIG(*) AS row_count, MIN(OrderDate) AS first_date, MAX(OrderDate) AS last_date FROM dbo.FactSales;

-- Key checks: is the one-side key unique? (relationships[].verified_unique)
SELECT COUNT_BIG(*) AS row_count, COUNT_BIG(DISTINCT RegionKey) AS distinct_keys,
       SUM(CASE WHEN RegionKey IS NULL THEN 1 ELSE 0 END) AS null_keys
FROM dbo.DimRegion;

-- Orphans: fact rows whose key has no dimension row (they show as "(Blank)")
SELECT COUNT_BIG(*) AS orphan_rows
FROM dbo.FactSales AS f
LEFT JOIN dbo.DimRegion AS d ON d.RegionKey = f.RegionKey
WHERE d.RegionKey IS NULL;
```

The model's numbers before it's published: `model_sql_check.py` (see `07-validation.md`).

## DAX checks on a published model (phase 2)

```dax
// Is the model refreshed? (step 3, phase 2)
EVALUATE ROW("Rows", COUNTROWS('Sales'), "Latest", MAX('Sales'[Order Date]))

// Model check at the sample's grain (step 7, phase 2): from DAXQueries/Model check.dax, plus the sample's filters
EVALUATE
SUMMARIZECOLUMNS(
    'Region'[Region], 'Product'[Category],
    FILTER(ALL('Date'[Date]), 'Date'[Date] >= DATE(2026, 9, 1) && 'Date'[Date] <= DATE(2026, 9, 30)),
    "Total Units", [Total Units], "Total Sales", [Total Sales]
)
ORDER BY 'Region'[Region], 'Product'[Category]
```

## Calculations: query or report?

| Calculation | Put it in |
|---|---|
| Business logic (margins, YTD, currency conversion) | Model measure (best) or SQL |
| Simple row ratios shown in the report | Column `expression` + `total_expression` with ratio of sums, e.g. `=IIf(Sum(Fields!SalesAmount.Value) = 0, 0, (Sum(Fields!SalesAmount.Value) - Sum(Fields!Cost.Value)) / Sum(Fields!SalesAmount.Value))` |
| Labels and titles | Report expressions |

## Common report expressions

| Need | Expression |
|---|---|
| Period title | `="Period: " & Format(Parameters!StartDate.Value, "MMMM yyyy")` |
| Subtotal label | `=Fields!Region.Value & " Total"` |
| Previous month start / end (defaults) | `=DateSerial(Year(Today()), Month(Today()) - 1, 1)` / `=DateAdd("d", -1, DateSerial(Year(Today()), Month(Today()), 1))` |
| Year to date start | `=DateSerial(Year(Today()), 1, 1)` |
| Safe division | `=IIf(Sum(Fields!B.Value) = 0, Nothing, Sum(Fields!A.Value) / Sum(Fields!B.Value))` |
| Negative numbers in red | `Color` expression `=IIf(Me.Value < 0, "Red", "Black")` (Excel exports the static colour) |
| Selected multi-values | `=Join(Parameters!Region.Label, ", ")` |
