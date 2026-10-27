# Semantic model design rules

Use these when the plan is **model-first**: build a semantic model from SQL (phase 1), the user publishes it, then build the report on it (phase 2).

## When to recommend model-first

Recommend it at the end of step 2 and let the user decide. Record the decision in `plan` (confirmed at Gate A).

| Recommend **model-first** when... | Build the report **directly** when... |
|---|---|
| No suitable published semantic model exists and the user wants a **Power BI (interactive) report**, which needs a model | A certified/published semantic model already has the data: use it |
| Several reports or people will use the same numbers | It's a single operational listing (one paginated report, detail rows) |
| The numbers need business logic (ratios, margins, time comparisons) that should be defined once | Simple sums/counts that the SQL query does directly |
| The data needs friendly names, hidden technical columns, a calendar | The report needs data refreshed live on every run |
| Large volumes where pre-aggregated, compressed data helps |  |

Phase 2 needs the model **published and refreshed** in the Power BI service: a paginated report connects to it by its published id, and the numbers are checked through it. Tell the user this up front: two handovers, and a publish in between.

## Shape: star schema

- **Fact tables** hold events with numbers (sales lines, transactions). **Dimension tables** describe them (region, product, customer). A **Date** table holds the calendar.
- Relationships go from the fact's key column (many) to the dimension's unique key (one), filtering in a **single direction**. Avoid both-direction filters and many-to-many relationships. If you think one is needed, ask the BI team.
- One active relationship between any two tables. A second date relationship (e.g. ship date) is created **inactive**.
- Flatten small lookup chains (product → subcategory → category) with a SQL query on the dimension (`source.query`) rather than chaining dimensions.
- Prove every relationship key is unique on the one side with SQL (`query-patterns.md` › Key checks), then set `verified_unique: true`. Report orphan facts (keys missing from the dimension) to the user. They show as "(Blank)" in reports.

## Tables and columns

- Load only the columns that reports need, plus keys. Every extra column costs memory and refresh time.
- Business-friendly names with spaces ("Sales Amount", not "SalesAmt"); `source_column` keeps the SQL name.
- Hide keys and raw numeric columns that have a measure (`hidden: true`); use `summarize_by: none` on keys and IDs.
- Date columns that join to the Date table: `data_type: dateTime` with `date_only: true` (loads as a date, without a time part).
- Descriptions on tables, important columns and every measure.

### SQL to model data types

| SQL type | `data_type` |
|---|---|
| int, bigint, smallint, tinyint | `int64` |
| decimal, numeric, float, real | `double` |
| money, smallmoney | `decimal` (fixed decimal, 4 places) |
| date, datetime, datetime2, smalldatetime, datetimeoffset | `dateTime` (`date_only: true` for dates) |
| bit | `boolean` |
| char, varchar, nchar, nvarchar, text, uniqueidentifier | `string` |
| binary, image, xml, geography | don't load |

## Measures

- One explicit measure per number the reports show. Store them in the main fact table, with `format` from the sample and a `description`.
- Sums: `SUM('Sales'[Sales Amount])`. Counts: `COUNTROWS('Sales')` or `DISTINCTCOUNT('Sales'[Customer Key])`.
- Ratios: `DIVIDE([Total Sales] - [Total Cost], [Total Sales])`, never a column of row-level ratios.
- Reuse measures inside measures (`[Total Sales]`), so logic is written once.
- Time intelligence (year-to-date, last year) only when the user asks: `TOTALYTD([Total Sales], 'Date'[Date])`, `CALCULATE([Total Sales], SAMEPERIODLASTYEAR('Date'[Date]))`. Note that the SQL cross-check can't recompute these; they're checked in phase 2 with DAX.
- Measure names must differ from every column name in their table and be unique across the model.

## Date table

`date_table.create: true` generates a calendar in Power Query: Date, Year, Quarter, Month Number (hidden), Month, Year Month Number (hidden), Month Year. Month sorts by Month Number, and Month Year by Year Month Number. It's marked as the model's date table. The range runs from 1 January of the first year in the fact data to 31 December of next year (check `MIN`/`MAX` of the fact date with SQL). Relate it to the main fact date column; other date columns relate inactive.

## Storage mode

- **Import** (default): data is copied into the model at refresh. Fast, and needs scheduled refresh (and a gateway for on-premises SQL).
- **DirectQuery**: only when the user needs up-to-the-minute data and the database can handle report queries. Explain the performance trade-off and confirm with the BI team.
- Direct Lake, composite models, incremental refresh, calculation groups and row-level security roles are out of scope. Refer them to the BI team.

## Security and governance

- The published model is secured by its workspace permissions. If different users must see different rows, row-level security is needed: refer to the BI team before publishing.
- Recommend applying the source data's sensitivity label to the model in the Power BI service.
- Server and database are model parameters (`<source> Server`, `<source> Database`), so the BI team can point the model at test or production without editing queries.
