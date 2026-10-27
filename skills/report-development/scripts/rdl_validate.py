#!/usr/bin/env python3
"""Check a paginated report definition (.rdl) for problems that stop it opening, publishing or rendering.

Usage:
  python rdl_validate.py REPORT.rdl [--xsd ReportDefinition.xsd] [--json]

Checks (no network needed):
  - well-formed XML and the 2016/01 report namespace
  - tablix structure: column/row member counts match TablixColumns/TablixRows, cells per row,
    corner size, uniform header depth
  - unique report item and group names
  - Fields!/Parameters!/ReportItems! references resolve (fields checked against the tablix dataset)
  - data sources: no embedded credentials, no shared data source references (unsupported in the
    Power BI service), query parameters used in the query text
  - expression syntax: balanced parentheses and quotes
  - page fit: body width + margins vs page width
  - optional XML Schema validation when lxml and an XSD file are available
Exit code 1 if any error is found.
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402
from rdl_inspect import strip_ns, txt  # noqa: E402

ITEM_TAGS = {"Tablix", "Textbox", "Image", "Chart", "Subreport", "Rectangle", "Map", "GaugePanel", "Line",
             "CustomReportItem", "List"}
FIELD_RE = re.compile(r"Fields!([A-Za-z_]\w*)\.Value")
PARAM_RE = re.compile(r"Parameters!([A-Za-z_]\w*)\.")
ITEM_RE = re.compile(r"ReportItems!([A-Za-z_]\w*)\.")
AS_PROVIDERS = {"PBIDATASET", "SQLAS", "OLEDB-MD", "ESSBASE"}
UNIT_TO_PT = {"pt": 1.0, "in": 72.0, "cm": 72 / 2.54, "mm": 72 / 25.4, "pc": 12.0}


def to_pt(size):
    m = re.match(r"^\s*([0-9.]+)\s*(pt|in|cm|mm|pc)\s*$", size or "")
    return float(m.group(1)) * UNIT_TO_PT[m.group(2)] if m else None


def leaves(members_parent):
    """Return a list of leaf member paths (lists of TablixMember elements)."""
    out = []
    tm = members_parent.find("TablixMembers") if members_parent is not None else None
    if tm is None:
        return out
    for m in tm.findall("TablixMember"):
        kids = leaves(m)
        if kids:
            out.extend([[m] + k for k in kids])
        else:
            out.append([m])
    return out


def header_depth(path):
    return sum(1 for m in path if m.find("TablixHeader") is not None)


def expression_problems(expr):
    if not expr or not expr.startswith("="):
        return None
    s = re.sub(r'"(?:[^"]|"")*"', '""', expr)          # drop string literals
    if s.count('"') % 2:
        return "unbalanced quotes"
    depth = 0
    for ch in s:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            return "closing parenthesis without opening one"
    return "unbalanced parentheses" if depth else None


def validate(path, xsd=None):
    errors, warnings, stats = [], [], {}
    with open(path, "rb") as f:
        raw = f.read()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return ["not well-formed XML: %s" % e], warnings, stats
    schema = strip_ns(root)
    if root.tag != "Report":
        return ["root element is <%s>, expected <Report>" % root.tag], warnings, stats
    if not schema or "2016/01" not in schema:
        warnings.append("report namespace is %s; Power BI Report Builder saves 2016/01" % schema)

    # Data sources and datasets
    providers = {}
    for ds in root.findall("DataSources/DataSource"):
        name = ds.get("Name")
        if txt(ds, "DataSourceReference"):
            errors.append("data source '%s' references a shared data source; the Power BI service needs an embedded data source" % name)
            continue
        prov = (txt(ds, "ConnectionProperties/DataProvider") or "").upper()
        conn = txt(ds, "ConnectionProperties/ConnectString") or ""
        providers[name] = prov
        if rk.mask_secrets(conn)[1] or re.search(r"(?i)\b(user id|uid)\s*=", conn):
            errors.append("data source '%s' has credentials in its connection string" % name)
    fields = {}
    for d in root.findall("DataSets/DataSet"):
        dname = d.get("Name")
        src = txt(d, "Query/DataSourceName")
        if src not in providers:
            errors.append("dataset '%s' uses unknown data source '%s'" % (dname, src))
        names = [f.get("Name") for f in d.findall("Fields/Field")]
        if len(set(names)) != len(names):
            errors.append("dataset '%s' has duplicate field names" % dname)
        fields[dname] = set(names)
        cmd = txt(d, "Query/CommandText") or ""
        for qp in d.findall("Query/QueryParameters/QueryParameter"):
            qn = qp.get("Name") or ""
            if providers.get(src) in AS_PROVIDERS:
                if qn.startswith("@"):
                    errors.append("dataset '%s': DAX/MDX query parameter names must not start with '@' (%s)" % (dname, qn))
                if "@" + qn not in cmd:
                    warnings.append("dataset '%s': query parameter '%s' is not used as @%s in the query" % (dname, qn, qn))
            else:
                if not qn.startswith("@"):
                    warnings.append("dataset '%s': SQL query parameter '%s' usually starts with '@'" % (dname, qn))
                elif qn not in cmd and qn.lower() not in cmd.lower():
                    warnings.append("dataset '%s': query parameter '%s' is not used in the query" % (dname, qn))
    params = {p.get("Name") for p in root.findall("ReportParameters/ReportParameter")}
    for p in root.findall("ReportParameters/ReportParameter"):
        for ref in p.findall(".//DataSetReference"):
            ds_name = txt(ref, "DataSetName")
            if ds_name not in fields:
                errors.append("parameter '%s' uses unknown dataset '%s'" % (p.get("Name"), ds_name))
            else:
                for k in ("ValueField", "LabelField"):
                    if txt(ref, k) and txt(ref, k) not in fields[ds_name]:
                        errors.append("parameter '%s' %s '%s' is not a field of '%s'" % (p.get("Name"), k, txt(ref, k), ds_name))

    # Names
    item_names, group_names = [], []
    for el in root.iter():
        if el.tag in ITEM_TAGS and el.get("Name"):
            item_names.append(el.get("Name"))
        if el.tag == "Group" and el.get("Name"):
            group_names.append(el.get("Name"))
    dup = sorted({n for n in item_names if item_names.count(n) > 1})
    if dup:
        errors.append("duplicate report item names: %s" % ", ".join(dup))
    dupg = sorted({n for n in group_names if group_names.count(n) > 1})
    if dupg:
        errors.append("duplicate group names: %s" % ", ".join(dupg))
    all_items = set(item_names)

    # Tablix structure and field scope
    in_tablix = set()
    for tx in root.iter("Tablix"):
        name = tx.get("Name")
        ncols = len(tx.findall("TablixBody/TablixColumns/TablixColumn"))
        rows = tx.findall("TablixBody/TablixRows/TablixRow")
        col_leaves = leaves(tx.find("TablixColumnHierarchy"))
        row_leaves = leaves(tx.find("TablixRowHierarchy"))
        if len(col_leaves) != ncols:
            errors.append("tablix '%s': %d columns but %d leaf column members" % (name, ncols, len(col_leaves)))
        if len(row_leaves) != len(rows):
            errors.append("tablix '%s': %d rows but %d leaf row members" % (name, len(rows), len(row_leaves)))
        for i, r in enumerate(rows):
            n = 0
            for c in r.findall("TablixCells/TablixCell"):
                n += int(txt(c, "CellContents/ColSpan") or 1)
            if n != ncols:
                errors.append("tablix '%s' row %d has %d cells for %d columns" % (name, i + 1, n, ncols))
        rdepths = {header_depth(p) for p in row_leaves}
        cdepths = {header_depth(p) for p in col_leaves}
        if len(rdepths) > 1:
            errors.append("tablix '%s': row header depth differs between rows %s" % (name, sorted(rdepths)))
        if len(cdepths) > 1:
            errors.append("tablix '%s': column header depth differs between columns %s" % (name, sorted(cdepths)))
        corner = tx.find("TablixCorner")
        rd_, cd_ = (max(rdepths) if rdepths else 0), (max(cdepths) if cdepths else 0)
        if rd_ and cd_:
            if corner is None:
                errors.append("tablix '%s' has row and column headers but no TablixCorner" % name)
            else:
                crow = corner.findall("TablixCornerRows/TablixCornerRow")
                if len(crow) != cd_:
                    errors.append("tablix '%s': corner has %d rows, expected %d" % (name, len(crow), cd_))
                for i, cr in enumerate(crow):
                    n = sum(int(txt(c, "CellContents/ColSpan") or 1) for c in cr.findall("TablixCornerCell"))
                    if n != rd_:
                        errors.append("tablix '%s': corner row %d has %d cells, expected %d" % (name, i + 1, n, rd_))
        ds = txt(tx, "DataSetName")
        if ds not in fields:
            errors.append("tablix '%s' uses unknown dataset '%s'" % (name, ds))
        for tb in tx.iter("Textbox"):
            in_tablix.add(id(tb))
            for v in tb.iter("Value"):
                for f in FIELD_RE.findall(v.text or ""):
                    if ds in fields and f not in fields[ds]:
                        errors.append("textbox '%s' in tablix '%s' uses field '%s', not in dataset '%s'" % (tb.get("Name"), name, f, ds))
        for ge in tx.iter("GroupExpression"):
            for f in FIELD_RE.findall(ge.text or ""):
                if ds in fields and f not in fields[ds]:
                    errors.append("group in tablix '%s' uses unknown field '%s'" % (name, f))
        stats.setdefault("tablixes", []).append({"name": name, "columns": ncols, "rows": len(rows), "dataset": ds})

    # Expressions, references outside data regions
    for el in root.iter():
        text = el.text or ""
        if not text.startswith("="):
            continue
        prob = expression_problems(text)
        if prob:
            errors.append("expression in <%s> has %s: %s" % (el.tag, prob, text[:120]))
        for p in PARAM_RE.findall(text):
            if p not in params:
                errors.append("expression uses undefined parameter '%s': %s" % (p, text[:80]))
        for it in ITEM_RE.findall(text):
            if it not in all_items:
                errors.append("expression uses unknown report item '%s'" % it)
    for part in ("PageHeader", "PageFooter"):
        for el in root.iter(part):
            for v in el.iter("Value"):
                if FIELD_RE.search(v.text or ""):
                    errors.append("%s textbox uses Fields! directly; page headers/footers can only use ReportItems!, Parameters! and Globals!" % part)
    body = root.find(".//Body")
    if body is not None:
        for tb in body.iter("Textbox"):
            if id(tb) in in_tablix:
                continue
            for v in tb.iter("Value"):
                t = v.text or ""
                if FIELD_RE.search(t) and not re.search(r"\b(First|Last|Sum|Max|Min|Count)\s*\(.*,\s*\"", t):
                    warnings.append("textbox '%s' outside a data region uses Fields! without a dataset scope" % tb.get("Name"))

    # Page fit
    page = root.find(".//Page")
    width = to_pt(txt(root.find(".//ReportSection"), "Width") or txt(root, "Width"))
    if page is not None and width:
        pw = to_pt(txt(page, "PageWidth"))
        lm, rm = to_pt(txt(page, "LeftMargin") or "0pt") or 0, to_pt(txt(page, "RightMargin") or "0pt") or 0
        if pw and width + lm + rm > pw + 0.5:
            warnings.append("body width %.0fpt + margins %.0fpt exceeds page width %.0fpt: PDF output gets extra blank pages"
                            % (width, lm + rm, pw))
        stats["page"] = {"width_pt": pw, "body_width_pt": width}
    ipn = txt(root, "InitialPageName")
    if ipn and not ipn.startswith("=") and (len(ipn) > 31 or re.search(r"[\[\]:*?/\\]", ipn)):
        warnings.append("InitialPageName '%s' is not a valid Excel sheet name (max 31 chars, no []:*?/\\)" % ipn)
    if root.find("CodeModules") is not None:
        errors.append("custom assemblies (CodeModules) are not supported in the Power BI service")
    if txt(root, "Code"):
        warnings.append("report contains custom code; review it")

    # Optional XSD validation
    if xsd and os.path.exists(xsd):
        try:
            from lxml import etree
            sch = etree.XMLSchema(etree.parse(xsd))
            doc = etree.fromstring(raw)
            if not sch.validate(doc):
                for e in list(sch.error_log)[:15]:
                    errors.append("schema: line %s: %s" % (e.line, e.message))
            stats["xsd"] = "validated"
        except ImportError:
            stats["xsd"] = "skipped (lxml not available)"
        except Exception as e:
            warnings.append("XSD validation could not run: %s" % e)
    stats["items"] = len(item_names)
    return errors, warnings, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rdl")
    ap.add_argument("--xsd", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "ReportDefinition.xsd"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    errors, warnings, stats = validate(a.rdl, a.xsd)
    if a.json:
        print(json.dumps({"errors": errors, "warnings": warnings, "stats": stats}, indent=2))
    else:
        for e in errors:
            print("ERROR: " + e)
        for w in warnings:
            print("WARNING: " + w)
        print("%s: %d error(s), %d warning(s); %s" % (os.path.basename(a.rdl), len(errors), len(warnings), json.dumps(stats)))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
