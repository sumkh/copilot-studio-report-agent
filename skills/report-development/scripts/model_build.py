#!/usr/bin/env python3
"""Build a Power BI semantic model (TMDL) as a zipped Power BI Project from a confirmed model spec.

Usage:
  python model_build.py spec_model.json --exemplar STARTER_OR_SAMPLE --out build/<name>_v<N>_pbip.zip
                        [--schema-out analysis/model.json]

The package contains:
  <name>.pbip
  <name>.SemanticModel/   definition.pbism, definition/ (database, model, expressions, relationships,
                          tables/*.tmdl) and DAXQueries/Model check.dax
  <name>.Report/          a one-page "Model check" report bound to the local model (byPath),
                          cloned from the exemplar so it has the organisation's look
  HOW_TO_OPEN.txt
Tables load from SQL through Power Query (Sql.Database with server/database parameters).
A Date table is generated in Power Query when date_table.create is true.
The model has no data until the user refreshes it in Power BI Desktop (they sign in to the
source there). Refuses to run unless both confirmation gates are current.
"""
import argparse
import datetime
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402
import spec_tool  # noqa: E402
import tmdl  # noqa: E402
from pbip_build import load_exemplar, make_report_files, pbip_file, write_zip  # noqa: E402

PBISM_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json"
M_TYPES = {"string": "type text", "int64": "Int64.Type", "double": "type number", "decimal": "Currency.Type",
           "dateTime": "type datetime", "date": "type date", "boolean": "type logical"}
NS = uuid.UUID("6f1c3f7e-2b8a-4d1e-9a65-3c9d8e2f4a10")


def tag(*parts):
    """Deterministic lineage tag, so rebuilding the same spec gives the same tags."""
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


def m_string(s):
    """Power Query text literal content: escape quotes, '#(' and line breaks."""
    s = str(s).replace("#(", "#(#)(").replace('"', '""')
    return s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "#(lf)").replace("\t", "#(tab)")


def m_name(n):
    return '#"%s"' % str(n).replace('"', '""')


def param_names(ds):
    return "%s Server" % ds["name"], "%s Database" % ds["name"]


def sql_table_m(t, ds):
    server, database = param_names(ds)
    src = t["source"]
    cols = [c for c in t["columns"] if not c.get("expression")]
    types = ", ".join('{"%s", %s}' % (c["source_column"].replace('"', '""'),
                                      M_TYPES["date" if c.get("date_only") else c["data_type"]]) for c in cols)
    if src.get("query"):
        steps = ['    Source = Sql.Database(%s, %s, [Query="%s"]),' % (m_name(server), m_name(database), m_string(src["query"])),
                 "    Typed = Table.TransformColumnTypes(Source, {%s})" % types]
    else:
        names = ", ".join('"%s"' % c["source_column"].replace('"', '""') for c in cols)
        steps = ["    Source = Sql.Database(%s, %s)," % (m_name(server), m_name(database)),
                 '    Data = Source{[Schema="%s", Item="%s"]}[Data],' % (src.get("schema", "dbo"), src["object"]),
                 "    Selected = Table.SelectColumns(Data, {%s})," % names,
                 "    Typed = Table.TransformColumnTypes(Selected, {%s})" % types]
    return "let\n" + "\n".join(steps) + "\nin\n    Typed"


def date_table_m(dt):
    s = datetime.date.fromisoformat(dt["start"])
    e = datetime.date.fromisoformat(dt["end"])
    culture = dt.get("culture", "en-US")
    return "\n".join([
        "let",
        "    StartDate = #date(%d, %d, %d)," % (s.year, s.month, s.day),
        "    EndDate = #date(%d, %d, %d)," % (e.year, e.month, e.day),
        "    Dates = List.Dates(StartDate, Duration.Days(EndDate - StartDate) + 1, #duration(1, 0, 0, 0)),",
        '    AsTable = Table.FromList(Dates, Splitter.SplitByNothing(), {"Date"}),',
        '    Typed = Table.TransformColumnTypes(AsTable, {{"Date", type date}}),',
        '    Year = Table.AddColumn(Typed, "Year", each Date.Year([Date]), Int64.Type),',
        '    Quarter = Table.AddColumn(Year, "Quarter", each "Q" & Number.ToText(Date.QuarterOfYear([Date])), type text),',
        '    MonthNumber = Table.AddColumn(Quarter, "Month Number", each Date.Month([Date]), Int64.Type),',
        '    Month = Table.AddColumn(MonthNumber, "Month", each Date.ToText([Date], [Format="MMM", Culture="%s"]), type text),' % culture,
        '    YearMonthNumber = Table.AddColumn(Month, "Year Month Number", each Date.Year([Date]) * 100 + Date.Month([Date]), Int64.Type),',
        '    MonthYear = Table.AddColumn(YearMonthNumber, "Month Year", each Date.ToText([Date], [Format="MMM yyyy", Culture="%s"]), type text)' % culture,
        "in",
        "    MonthYear"])


DATE_COLUMNS = tmdl.DATE_COLUMNS


def prop(level, key, val):
    return "%s%s: %s" % ("\t" * level, key, tmdl.value(val) if " " not in str(val) else '"%s"' % str(val).replace('"', '""'))


def desc_lines(text, level):
    if not text:
        return []
    return ["%s/// %s" % ("\t" * level, line.strip()) for line in str(text).splitlines() if line.strip()]


def emit_column(model_name, table_name, c, level=1):
    out = desc_lines(c.get("description"), level)
    head = "%scolumn %s" % ("\t" * level, tmdl.name(c["name"]))
    expr_lines = []
    if c.get("expression"):
        suffix, expr_lines = tmdl.dax_default(c["expression"], level)
        head += suffix
    out.append(head)
    out += expr_lines
    out.append(prop(level + 1, "dataType", c["data_type"]))
    if c.get("hidden"):
        out.append("\t" * (level + 1) + "isHidden")
    if c.get("is_key"):
        out.append("\t" * (level + 1) + "isKey")
    if c.get("format"):
        out.append(prop(level + 1, "formatString", c["format"]))
    out.append(prop(level + 1, "lineageTag", tag(model_name, "column", table_name, c["name"])))
    out.append(prop(level + 1, "summarizeBy", c.get("summarize_by") or "none"))
    if not c.get("expression"):
        out.append(prop(level + 1, "sourceColumn", c["source_column"]))
    if c.get("sort_by"):
        out.append("%ssortByColumn: %s" % ("\t" * (level + 1), tmdl.name(c["sort_by"])))
    out.append("")
    return out


def emit_measure(model_name, table_name, m, level=1):
    out = desc_lines(m.get("description"), level)
    suffix, expr_lines = tmdl.dax_default(m["expression"], level)
    out.append("%smeasure %s%s" % ("\t" * level, tmdl.name(m["name"]), suffix))
    out += expr_lines
    if m.get("format"):
        out.append(prop(level + 1, "formatString", m["format"]))
    if m.get("display_folder"):
        out.append(prop(level + 1, "displayFolder", m["display_folder"]))
    if m.get("hidden"):
        out.append("\t" * (level + 1) + "isHidden")
    out.append(prop(level + 1, "lineageTag", tag(model_name, "measure", table_name, m["name"])))
    out.append("")
    return out


def emit_partition(name, mode, m_code):
    return ["\tpartition %s = m" % tmdl.name(name), "\t\tmode: %s" % mode, "\t\tsource ="] + tmdl.expression_block(m_code, 3) + [""]


def emit_table(model_name, t, measures, ds_by_name, date_table=None):
    out = desc_lines(t.get("description"), 0)
    out += ["table %s" % tmdl.name(t["name"]), prop(1, "lineageTag", tag(model_name, "table", t["name"]))]
    if date_table:
        out.append("\tdataCategory: Time")
    out.append("")
    for m in measures:
        out += emit_measure(model_name, t["name"], m)
    if date_table:
        for cname, dtype, fmt, hidden, sort_by in DATE_COLUMNS:
            out += emit_column(model_name, t["name"], {"name": cname, "data_type": dtype, "format": fmt, "hidden": hidden,
                                                         "is_key": cname == "Date", "summarize_by": "none",
                                                         "source_column": cname, "sort_by": sort_by})
        out += emit_partition(t["name"], "import", date_table_m(date_table))
    else:
        for c in t["columns"]:
            out += emit_column(model_name, t["name"], c)
        out += emit_partition(t["name"], "directQuery" if t.get("mode") == "directQuery" else "import",
                              sql_table_m(t, ds_by_name[t["data_source"]]))
    return "\n".join(out).rstrip("\n") + "\n"


def all_tables(spec):
    tables = list(spec["tables"])
    dt = spec.get("date_table") or {}
    if dt.get("create"):
        tables.append({"name": dt.get("name", "Date"), "columns": [{"name": c[0], "data_type": c[1]} for c in DATE_COLUMNS],
                       "_date": dt})
    return tables


def model_schema(spec):
    tables = {}
    for t in all_tables(spec):
        tables[t["name"]] = {"columns": [c["name"] for c in t["columns"]], "measures": []}
    for m in spec.get("measures") or []:
        tables[m["table"]]["measures"].append(m["name"])
    return {"tables": tables}


def build(spec, exemplar_path):
    spec_tool.require_confirmed(spec)
    errors, warnings = spec_tool.validate(spec)
    if errors:
        rk.fail("The spec has errors: " + "; ".join(e for _, e in errors))
    if spec["report_type"] != "semantic_model":
        rk.fail("model_build.py builds semantic models; use rdl_build.py or pbip_build.py for reports")
    name = spec["report"]["file_name"]
    culture = spec["report"].get("culture", "en-US")
    smf = name + ".SemanticModel/"
    out = {}
    ds_by_name = {d["name"]: d for d in spec["data_sources"]}
    measures_by_table = {}
    for m in spec.get("measures") or []:
        measures_by_table.setdefault(m["table"], []).append(m)

    # definition.pbism and database/model
    out[smf + "definition.pbism"] = {"$schema": PBISM_SCHEMA, "version": "4.0", "settings": {}}
    out[smf + "definition/database.tmdl"] = "database %s\n\tcompatibilityLevel: %d\n" % (
        tmdl.name(name), int(spec["report"].get("compatibility_level", 1567)))
    tables = all_tables(spec)
    query_order = [p for d in spec["data_sources"] for p in param_names(d)] + [t["name"] for t in tables]
    model_lines = ["model Model", "\tculture: %s" % culture, "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
                   "\tsourceQueryCulture: %s" % culture, "",
                   "annotation __PBI_TimeIntelligenceEnabled = 0", "",
                   "annotation PBI_QueryOrder = %s" % json.dumps(query_order, ensure_ascii=False, separators=(",", ":")), ""]
    model_lines += ["ref table %s" % tmdl.name(t["name"]) for t in tables]
    out[smf + "definition/model.tmdl"] = "\n".join(model_lines) + "\n"

    # Shared expressions: one server and one database parameter per data source
    exprs = []
    for d in spec["data_sources"]:
        for pname, val in zip(param_names(d), (d["server"], d["database"])):
            exprs += ['expression %s = "%s" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'
                      % (tmdl.name(pname), str(val).replace('"', '""')),
                      prop(1, "lineageTag", tag(name, "expression", pname)), "",
                      "\tannotation PBI_ResultType = Text", ""]
    out[smf + "definition/expressions.tmdl"] = "\n".join(exprs).rstrip("\n") + "\n"

    # Relationships (including Date table relationships)
    rels = list(spec.get("relationships") or [])
    dt = spec.get("date_table") or {}
    if dt.get("create"):
        for r in dt.get("relationships") or []:
            rels.append({"from_table": r["table"], "from_column": r["column"], "to_table": dt.get("name", "Date"),
                         "to_column": "Date", "active": r.get("active", True), "cross_filter": "single"})
    rel_lines = []
    for r in rels:
        rid = tag(name, "relationship", r["from_table"], r["from_column"], r["to_table"], r["to_column"])
        rel_lines.append("relationship %s" % rid)
        if r.get("active", True) is False:
            rel_lines.append("\tisActive: false")
        if r.get("cross_filter") == "both":
            rel_lines.append("\tcrossFilteringBehavior: bothDirections")
        rel_lines += ["\tfromColumn: %s" % tmdl.qualified(r["from_table"], r["from_column"]),
                      "\ttoColumn: %s" % tmdl.qualified(r["to_table"], r["to_column"]), ""]
    if rel_lines:
        out[smf + "definition/relationships.tmdl"] = "\n".join(rel_lines).rstrip("\n") + "\n"

    for t in tables:
        out[smf + "definition/tables/%s.tmdl" % t["name"].replace("/", "_")] = emit_table(
            name, t, measures_by_table.get(t["name"], []), ds_by_name, t.get("_date"))

    # Model check: DAX query file and a one-page report
    cp = spec.get("check_page") or {}
    rows = cp.get("rows") or []
    meas = cp.get("measures") or [m["name"] for m in (spec.get("measures") or [])][:4]
    mtable = {m["name"]: m["table"] for m in spec.get("measures") or []}
    dax = ["// Model check for '%s'. Run it in DAX query view after refreshing the model," % spec["report"]["name"],
           "// and compare the numbers with %s." % ((spec.get("validation") or {}).get("sample_file") or "your sample"),
           "EVALUATE", "SUMMARIZECOLUMNS("]
    args = ["    '%s'[%s]" % (r["table"].replace("'", "''"), r["column"]) for r in rows]
    args += ['    "%s", [%s]' % (m.replace('"', '""'), m) for m in meas]
    dax.append(",\n".join(args))
    dax.append(")")
    if rows:
        dax.append("ORDER BY " + ", ".join("'%s'[%s]" % (r["table"].replace("'", "''"), r["column"]) for r in rows))
    out[smf + "DAXQueries/Model check.dax"] = "\n".join(dax) + "\n"

    fields = {}
    for i, r in enumerate(rows):
        fields["row%d" % i] = {"table": r["table"], "name": r["column"], "kind": "column"}
    for i, m in enumerate(meas):
        fields["m%d" % i] = {"table": mtable[m], "name": m, "kind": "measure"}
    visuals = []
    for i, m in enumerate(meas[:4]):
        visuals.append({"type": "card", "title": m, "roles": {"Values": ["m%d" % i]},
                        "position": {"x": 24 + i * 312, "y": 24, "width": 296, "height": 120}})
    visuals.append({"type": "tableEx", "title": "Model check" + (" by " + ", ".join(r["column"] for r in rows) if rows else ""),
                    "roles": {"Values": ["row%d" % i for i in range(len(rows))] + ["m%d" % i for i in range(len(meas))]},
                    "position": {"x": 24, "y": 160, "width": 1232, "height": 536}})
    if not exemplar_path:
        rk.fail("A PBIR exemplar is needed for the model-check report: the user's PBIP sample or the starter template "
                "named in config/org-config.json (pbir_starter_template).")
    ex = load_exemplar(exemplar_path)
    out.update(make_report_files(ex, name + ".Report", [{"name": "Model check", "visuals": visuals}], fields,
                                 {"byPath": {"path": "../%s.SemanticModel" % name}}, spec.get("exemplar") or {}, warnings))
    out[name + ".pbip"] = pbip_file(name, name + ".Report")
    servers = ", ".join("%s / %s" % (d["server"], d["database"]) for d in spec["data_sources"])
    out["HOW_TO_OPEN.txt"] = (
        "Semantic model '%s' (spec version %s), built by the report-development assistant.\n\n"
        "1. Unzip this file to a local folder, keeping the folder structure.\n"
        "2. Open %s.pbip in Power BI Desktop (a current version).\n"
        "3. The model opens without data. Select Home > Refresh.\n"
        "4. When Power BI Desktop asks how to connect to %s, sign in with the method your organisation uses\n"
        "   for that database (usually your Microsoft work account or Windows account). Never type a shared password.\n"
        "%s"
        "5. Check the 'Model check' page (or run DAXQueries/Model check.dax in DAX query view) against your sample.\n"
        "6. Publish with Home > Publish to your workspace. In the Power BI service, the BI team or workspace admin\n"
        "   maps the data source to a gateway or cloud connection and sets scheduled refresh.\n"
        "7. Send the assistant the link to the published semantic model to continue with the report.\n"
        % (spec["report"]["name"], spec["report"].get("version", 1), name, servers,
           "   If Power BI Desktop asks for permission to run a native database query, check it is the query you\n"
           "   confirmed and select Run.\n" if any((t.get("source") or {}).get("query") for t in spec["tables"]) else ""))
    return out, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--exemplar")
    ap.add_argument("--out", required=True)
    ap.add_argument("--schema-out")
    a = ap.parse_args()
    spec = rk.load_json(a.spec)
    exemplar = a.exemplar or (spec.get("exemplar") or {}).get("file")
    files, warnings = build(spec, exemplar)
    write_zip(files, a.out)
    if a.schema_out:
        rk.dump_json(model_schema(spec), a.schema_out)
    for w in warnings:
        print("WARNING: " + w)
    print("wrote %s (%d files)" % (a.out, len(files)))


if __name__ == "__main__":
    main()
