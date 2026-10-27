#!/usr/bin/env python3
"""Inspect a paginated report (.rdl), shared data source (.rds) or shared dataset (.rsd).

Usage:
  python rdl_inspect.py REPORT.rdl [--out inspect.json] [--summary]

Extracts data sources (provider, server/database or semantic model, security),
datasets (query text, query parameters, fields), report parameters, page setup,
tablix layout (columns, header text, detail expressions, groups, formats) and
styles, plus warnings for things the Power BI service won't accept as-is
(shared data sources/datasets, embedded credentials, custom assemblies).
Passwords found in connection strings are masked and never reused.
"""
import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402

ITEM_TAGS = ("Tablix", "Textbox", "Image", "Chart", "Subreport", "Rectangle", "Map", "GaugePanel", "Line",
             "CustomReportItem", "List", "Table", "Matrix")
FIELD_RE = re.compile(r"Fields!([A-Za-z_][\w]*)\.Value")
PARAM_RE = re.compile(r"Parameters!([A-Za-z_][\w]*)\.(?:Value|Label)")
AGG_RE = re.compile(r"\b(Sum|Avg|Count|CountDistinct|Min|Max|First|Last|Aggregate|RunningValue)\s*\(", re.I)


def strip_ns(root):
    schema = None
    for el in root.iter():
        if isinstance(el.tag, str) and el.tag.startswith("{"):
            ns, local = el.tag[1:].split("}", 1)
            if local == "Report" and "reportdefinition" in ns:
                schema = ns
            el.tag = local
    return schema


def txt(el, path, default=None):
    if el is None:
        return default
    f = el.find(path)
    return f.text if f is not None and f.text is not None else default


def textbox_info(tb):
    runs = tb.findall(".//TextRun")
    values = [txt(r, "Value", "") for r in runs]
    run_style = runs[0].find("Style") if runs else None
    para = tb.find(".//Paragraph/Style")
    box = tb.find("Style")
    style = {}
    for k in ("FontFamily", "FontSize", "FontWeight", "FontStyle", "TextDecoration", "Color", "Format"):
        v = txt(run_style, k)
        if v is not None:
            style[k] = v
    if txt(para, "TextAlign"):
        style["TextAlign"] = txt(para, "TextAlign")
    for k in ("BackgroundColor", "VerticalAlign"):
        if txt(box, k):
            style[k] = txt(box, k)
    border = box.find("Border") if box is not None else None
    if border is not None:
        style["Border"] = {k: txt(border, k) for k in ("Color", "Style", "Width") if txt(border, k)}
    return {"name": tb.get("Name"), "value": "".join(values) if len(values) <= 1 else " | ".join(values), "style": style}


def members(container, depth=0, out=None):
    """Flatten a TablixRowHierarchy/TablixColumnHierarchy into a list of member descriptors."""
    out = [] if out is None else out
    tm = container.find("TablixMembers") if container is not None else None
    if tm is None:
        return out
    for m in tm.findall("TablixMember"):
        g = m.find("Group")
        entry = {"depth": depth, "dynamic": g is not None}
        if g is not None:
            entry["group"] = g.get("Name")
            entry["expressions"] = [e.text for e in g.findall("GroupExpressions/GroupExpression")]
            pb = g.find("PageBreak")
            if pb is not None:
                entry["page_break"] = txt(pb, "BreakLocation")
            if txt(g, "PageName"):
                entry["page_name"] = txt(g, "PageName")
        sorts = [s.text for s in m.findall("SortExpressions/SortExpression/Value")]
        if sorts:
            entry["sort"] = sorts
        hdr = m.find("TablixHeader")
        if hdr is not None:
            tb = hdr.find(".//Textbox")
            entry["header"] = textbox_info(tb) if tb is not None else None
            entry["header_size"] = txt(hdr, "Size")
        for k in ("KeepWithGroup", "RepeatOnNewPage", "FixedData", "HideIfNoRows"):
            if txt(m, k):
                entry[k] = txt(m, k)
        children_start = len(out)
        out.append(entry)
        members(m, depth + 1, out)
        entry["leaf"] = len(out) == children_start + 1
    return out


def classify_row(cells):
    vals = " ".join(c["value"] or "" for c in cells)
    if AGG_RE.search(vals):
        return "total"
    if FIELD_RE.search(vals):
        return "detail"
    return "header" if any((c["value"] or "").strip() for c in cells) else "empty"


def tablix_info(tx):
    cols = [txt(c, "Width") for c in tx.findall("TablixBody/TablixColumns/TablixColumn")]
    rows = []
    for r in tx.findall("TablixBody/TablixRows/TablixRow"):
        cells = []
        for cell in r.findall("TablixCells/TablixCell"):
            tb = cell.find(".//Textbox")
            info = textbox_info(tb) if tb is not None else {"name": None, "value": None, "style": {}}
            span = txt(cell, "CellContents/ColSpan")
            if span:
                info["col_span"] = int(span)
            cells.append(info)
        rows.append({"height": txt(r, "Height"), "kind": classify_row(cells), "cells": cells})
    row_members = members(tx.find("TablixRowHierarchy"))
    col_members = members(tx.find("TablixColumnHierarchy"))
    header_row = next((r for r in rows if r["kind"] == "header"), None)
    detail_row = next((r for r in rows if r["kind"] == "detail"), None)
    columns = []
    row_header_cols = [m for m in row_members if m.get("header") and m["depth"] == 0]
    if row_header_cols:
        hdr_member = next((m for m in row_header_cols if not m["dynamic"]), None)
        grp_member = next((m for m in row_header_cols if m["dynamic"]), None)
        columns.append({"header": (hdr_member or {}).get("header", {}).get("value") if hdr_member else None,
                        "expression": (grp_member or {}).get("header", {}).get("value") if grp_member else None,
                        "width": row_header_cols[0].get("header_size"), "row_header": True,
                        "style": (grp_member or {}).get("header", {}).get("style") if grp_member else None})
    for i, w in enumerate(cols):
        h = header_row["cells"][i] if header_row and i < len(header_row["cells"]) else None
        d = detail_row["cells"][i] if detail_row and i < len(detail_row["cells"]) else None
        columns.append({"header": h["value"] if h else None, "expression": d["value"] if d else None, "width": w,
                        "format": (d or {}).get("style", {}).get("Format"),
                        "align": (d or {}).get("style", {}).get("TextAlign")})
    has_col_groups = any(m["dynamic"] for m in col_members)
    return {
        "name": tx.get("Name"), "dataset": txt(tx, "DataSetName"),
        "layout": "matrix" if has_col_groups else "table",
        "columns": columns, "rows": [{"kind": r["kind"], "height": r["height"]} for r in rows],
        "row_groups": [m for m in row_members if m["dynamic"] and m.get("group") != "Details"],
        "has_details_group": any(m.get("group") == "Details" for m in row_members),
        "column_groups": [m for m in col_members if m["dynamic"]],
        "styles": {
            "header": header_row["cells"][0]["style"] if header_row and header_row["cells"] else None,
            "detail": detail_row["cells"][0]["style"] if detail_row and detail_row["cells"] else None,
            "total": next((r["cells"][-1]["style"] for r in rows if r["kind"] == "total" and r["cells"]), None),
        },
        "repeat_column_headers": txt(tx, "RepeatColumnHeaders"),
        "page_name": txt(tx, "PageName"),
        "position": {k: txt(tx, k) for k in ("Top", "Left", "Height", "Width")},
    }


def walk_items(container, out, path="Body"):
    items = container.find("ReportItems") if container is not None else None
    if items is None:
        return
    for el in items:
        if el.tag not in ITEM_TAGS:
            continue
        entry = {"type": el.tag, "name": el.get("Name"), "in": path}
        if el.tag == "Tablix":
            entry.update(tablix_info(el))
        elif el.tag == "Textbox":
            entry.update(textbox_info(el))
        elif el.tag == "Image":
            entry.update({"source": txt(el, "Source"), "value": txt(el, "Value")})
        elif el.tag == "Subreport":
            entry.update({"report_name": txt(el, "ReportName")})
        elif el.tag == "Chart":
            entry.update({"chart_type": txt(el, ".//ChartSeries/Type"), "dataset": txt(el, "DataSetName")})
        out.append(entry)
        if el.tag in ("Rectangle", "List"):
            walk_items(el, out, path + "/" + (el.get("Name") or el.tag))


def inspect_rdl(root, schema, warnings):
    res = {"schema": schema, "description": txt(root, "Description"), "author": txt(root, "Author"),
           "initial_page_name": txt(root, "InitialPageName")}
    sources = []
    for ds in root.findall("DataSources/DataSource"):
        cp = ds.find("ConnectionProperties")
        conn_raw = txt(cp, "ConnectString", "")
        conn, secret = rk.mask_secrets(conn_raw)
        entry = {"name": ds.get("Name"), "data_provider": txt(cp, "DataProvider"), "connect_string": conn,
                 "integrated_security": txt(cp, "IntegratedSecurity"), "prompt": txt(cp, "Prompt"),
                 "security_type": txt(ds, "SecurityType"), "shared_reference": txt(ds, "DataSourceReference")}
        if entry["shared_reference"]:
            entry["kind"] = "shared_data_source"
            warnings.append("Data source '%s' references a shared data source (%s). The Power BI service needs an "
                            "embedded data source: ask the user for the server and database." % (ds.get("Name"), entry["shared_reference"]))
        else:
            entry.update(rk.classify_connection(entry["data_provider"], conn_raw))
        if secret or "user id=" in conn_raw.lower() or "uid=" in conn_raw.lower():
            entry["embedded_credentials"] = True
            warnings.append("Data source '%s' contains credentials in its connection string. They were masked and must "
                            "not be reused; the published report should use a gateway or cloud connection." % ds.get("Name"))
        sources.append(entry)
    res["data_sources"] = sources
    datasets = []
    for d in root.findall("DataSets/DataSet"):
        q = d.find("Query")
        fields = []
        for f in d.findall("Fields/Field"):
            fields.append({"name": f.get("Name"), "data_field": txt(f, "DataField"), "value": txt(f, "Value"),
                           "type": txt(f, "TypeName")})
        entry = {"name": d.get("Name"), "data_source": txt(q, "DataSourceName"), "command_type": txt(q, "CommandType", "Text"),
                 "command_text": txt(q, "CommandText"), "shared_dataset": txt(d, "SharedDataSet/SharedDataSetReference"),
                 "query_parameters": [{"name": p.get("Name"), "value": txt(p, "Value")} for p in q.findall("QueryParameters/QueryParameter")] if q is not None else [],
                 "fields": fields, "filters": len(d.findall("Filters/Filter"))}
        if entry["shared_dataset"]:
            warnings.append("Dataset '%s' uses a shared dataset (%s); Power BI paginated reports need it embedded." % (d.get("Name"), entry["shared_dataset"]))
        text = entry["command_text"] or ""
        entry["query_language"] = "DAX" if re.match(r"(?is)\s*(DEFINE|EVALUATE)\b", text) else (
            "MDX" if re.match(r"(?is)\s*(WITH|SELECT)\b.*\bON\s+(COLUMNS|0)\b", text) else "SQL/other")
        datasets.append(entry)
    res["datasets"] = datasets
    params = []
    for p in root.findall("ReportParameters/ReportParameter"):
        dv = p.find("DefaultValue")
        vv = p.find("ValidValues")
        entry = {"name": p.get("Name"), "data_type": txt(p, "DataType"), "prompt": txt(p, "Prompt"),
                 "multi_value": txt(p, "MultiValue") == "true", "nullable": txt(p, "Nullable") == "true",
                 "allow_blank": txt(p, "AllowBlank") == "true", "hidden": txt(p, "Hidden") == "true"}
        if dv is not None:
            vals = [v.text for v in dv.findall("Values/Value")]
            entry["default"] = vals if vals else {"dataset": txt(dv, "DataSetReference/DataSetName"),
                                                  "value_field": txt(dv, "DataSetReference/ValueField")}
        if vv is not None:
            static = [{"value": txt(v, "Value"), "label": txt(v, "Label")} for v in vv.findall("ParameterValues/ParameterValue")]
            entry["valid_values"] = static if static else {"dataset": txt(vv, "DataSetReference/DataSetName"),
                                                           "value_field": txt(vv, "DataSetReference/ValueField"),
                                                           "label_field": txt(vv, "DataSetReference/LabelField")}
        params.append(entry)
    res["parameters"] = params
    page = root.find(".//Page")
    pg = {}
    if page is not None:
        for k in ("PageHeight", "PageWidth", "LeftMargin", "RightMargin", "TopMargin", "BottomMargin", "InteractiveHeight", "InteractiveWidth"):
            if txt(page, k):
                pg[k] = txt(page, k)
    else:
        for k in ("PageHeight", "PageWidth", "LeftMargin", "RightMargin", "TopMargin", "BottomMargin"):
            if txt(root, k):
                pg[k] = txt(root, k)
    res["page"] = pg
    items = []
    body = root.find(".//Body")
    walk_items(body, items, "Body")
    for part in ("PageHeader", "PageFooter"):
        el = root.find(".//" + part)
        if el is not None:
            walk_items(el, items, part)
    res["report_items"] = items
    all_text = ET.tostring(root, encoding="unicode")
    res["fields_used"] = sorted(set(FIELD_RE.findall(all_text)))
    res["parameters_used"] = sorted(set(PARAM_RE.findall(all_text)))
    code = txt(root, "Code")
    res["custom_code_chars"] = len(code) if code else 0
    if code:
        warnings.append("The report has custom VB code (%d characters). Review it before reuse." % len(code))
    if root.find("CodeModules") is not None:
        warnings.append("The report references custom assemblies (CodeModules); the Power BI service doesn't support them.")
    images = []
    for im in root.findall("EmbeddedImages/EmbeddedImage"):
        data = txt(im, "ImageData", "")
        images.append({"name": im.get("Name"), "mime": txt(im, "MIMEType"), "approx_bytes": len(data) * 3 // 4})
    res["embedded_images"] = images
    if any(i["type"] == "Subreport" for i in items):
        warnings.append("The report uses subreports; they must be published to the same workspace.")
    if any(i["type"] == "Image" and (i.get("source") or "").lower() == "external" for i in items):
        warnings.append("The report loads external images by URL; check that the URLs are reachable from the service.")
    return res


def inspect_rds(root, warnings):
    cp = root.find("ConnectionProperties")
    conn_raw = txt(cp, "ConnectString", "")
    conn, secret = rk.mask_secrets(conn_raw)
    entry = {"name": root.get("Name"), "data_provider": txt(cp, "Extension"), "connect_string": conn,
             "integrated_security": txt(cp, "IntegratedSecurity")}
    entry.update(rk.classify_connection(entry["data_provider"], conn_raw))
    if secret:
        warnings.append("The shared data source stores a password; it was masked and won't be reused.")
    return {"shared_data_source": entry}


def inspect_rsd(root, warnings):
    d = root.find("DataSet")
    q = d.find("Query") if d is not None else None
    return {"shared_dataset": {"name": d.get("Name") if d is not None else None,
                               "data_source_reference": txt(q, "DataSourceReference"),
                               "command_text": txt(q, "CommandText"),
                               "fields": [{"name": f.get("Name"), "data_field": txt(f, "DataField")} for f in (d.findall("Fields/Field") if d is not None else [])]}}


def inspect(path):
    warnings = []
    with open(path, "rb") as f:
        data = f.read()
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        rk.fail("Not a readable XML file: %s" % e)
    schema = strip_ns(root)
    if root.tag == "Report":
        result = inspect_rdl(root, schema, warnings)
        if schema and "2016/01" not in schema:
            warnings.append("Schema %s is older than 2016/01; Power BI Report Builder upgrades it when the file is opened." % schema)
    elif root.tag == "RptDataSource":
        result = inspect_rds(root, warnings)
    elif root.tag == "SharedDataSet":
        result = inspect_rsd(root, warnings)
    else:
        rk.fail("Unrecognised root element <%s>; expected a paginated report definition." % root.tag)
    result["file"] = os.path.basename(path)
    result["warnings"] = warnings
    return result


def summary_md(r):
    lines = ["# Paginated report inspection: %s" % r["file"], ""]
    if "shared_data_source" in r:
        s = r["shared_data_source"]
        lines.append("Shared data source '%s': %s, server %s, database %s." % (s["name"], s.get("kind"), s.get("server"), s.get("database")))
    if "shared_dataset" in r:
        s = r["shared_dataset"]
        lines.append("Shared dataset '%s' on %s; fields: %s" % (s["name"], s["data_source_reference"], ", ".join(f["name"] for f in s["fields"])))
    for s in r.get("data_sources", []):
        where = s.get("model_id") and ("semantic model %s" % s["model_id"]) or ("server %s, database %s" % (s.get("server"), s.get("database")))
        lines.append("- Data source **%s**: %s (%s) %s%s" % (s["name"], s.get("kind"), s.get("data_provider") or "shared", where,
                                                       " - SHARED REFERENCE " + s["shared_reference"] if s.get("shared_reference") else ""))
    for d in r.get("datasets", []):
        lines += ["", "## Dataset %s (%s on %s)" % (d["name"], d["query_language"], d["data_source"]),
                  "Fields: " + ", ".join("%s%s" % (f["name"], " (calculated)" if f["value"] else "") for f in d["fields"])]
        if d["query_parameters"]:
            lines.append("Query parameters: " + ", ".join("%s <- %s" % (p["name"], p["value"]) for p in d["query_parameters"]))
        q = (d["command_text"] or "").strip().splitlines()
        lines += ["```", *q[:25], "```" if len(q) <= 25 else "... (%d more lines)\n```" % (len(q) - 25)]
    if r.get("parameters"):
        lines += ["", "## Parameters"]
        for p in r["parameters"]:
            lines.append("- %s (%s%s): prompt '%s', default %s" % (p["name"], p["data_type"], ", multi-value" if p["multi_value"] else "",
                                                                 p["prompt"], p.get("default")))
    if r.get("page"):
        lines += ["", "Page: " + ", ".join("%s=%s" % kv for kv in r["page"].items())]
    for it in r.get("report_items", []):
        if it["type"] == "Tablix":
            lines += ["", "## Tablix %s (%s, dataset %s)" % (it["name"], it["layout"], it["dataset"]),
                      "| Header | Expression | Width | Format |", "|---|---|---|---|"]
            for c in it["columns"]:
                lines.append("| %s | %s | %s | %s |" % (c.get("header"), (c.get("expression") or "")[:60], c.get("width"), c.get("format") or ""))
            if it["row_groups"]:
                lines.append("Row groups: " + ", ".join("%s %s" % (g["group"], g.get("expressions")) for g in it["row_groups"]))
            if it["column_groups"]:
                lines.append("Column groups: " + ", ".join("%s %s" % (g["group"], g.get("expressions")) for g in it["column_groups"]))
            lines.append("Header style: %s" % it["styles"]["header"])
            lines.append("Detail style: %s" % it["styles"]["detail"])
        elif it["type"] == "Textbox" and it["in"] != "Body":
            lines.append("- %s textbox %s: %s" % (it["in"], it["name"], (it.get("value") or "")[:100]))
    if r.get("warnings"):
        lines += ["", "Warnings:"] + ["- " + w for w in r["warnings"]]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--out")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    r = inspect(a.file)
    if a.out:
        rk.dump_json(r, a.out)
    if a.summary:
        print(summary_md(r))
    elif not a.out:
        rk.dump_json(r)


if __name__ == "__main__":
    main()
