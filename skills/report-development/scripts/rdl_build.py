#!/usr/bin/env python3
"""Build a Power BI paginated report definition (.rdl, schema 2016/01) from a confirmed report spec.

Usage:
  python rdl_build.py spec.json --out Report_Name_v1.rdl

Refuses to run unless both confirmation gates in the spec are current (spec_tool.py check).
Layouts: "table" (columns, optional nested row groups with subtotals, grand total) and
"matrix" (row groups as row headers, one column group, one or more values).
All sizes are written in whole points: Microsoft recommends points to avoid rounding that
causes merged cells when the report is exported to Excel.
"""
import argparse
import math
import os
import sys
import uuid
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402
import spec_tool  # noqa: E402

NS = "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"
RD = "http://schemas.microsoft.com/SQLServer/reporting/reportdesigner"
AS_PROVIDERS = {"PBIDATASET", "SQLAS", "OLEDB-MD", "ESSBASE"}       # query parameters without '@'
TYPE_NAMES = {"String": "System.String", "Integer": "System.Int64", "Float": "System.Double",
              "Decimal": "System.Decimal", "DateTime": "System.DateTime", "Boolean": "System.Boolean"}
AGG_FUNCS = {"Sum", "Avg", "Min", "Max", "Count", "CountDistinct"}


# ----------------------------------------------------------------------------
# XML helpers
# ----------------------------------------------------------------------------

def el(tag, content="", attrs=None):
    a = "".join(' %s="%s"' % (k, escape(str(v), {'"': "&quot;"})) for k, v in (attrs or {}).items())
    return "<%s%s />" % (tag, a) if content in (None, "") else "<%s%s>%s</%s>" % (tag, a, content, tag)


def t(tag, text):
    return el(tag, escape(str(text)) if text not in (None, "") else "")


def pt(v):
    return "%dpt" % int(round(float(v)))


def border_width(v):
    v = max(0.25, min(20.0, float(v or 1)))
    return ("%.2f" % v).rstrip("0").rstrip(".") + "pt"


# ----------------------------------------------------------------------------
# Styles
# ----------------------------------------------------------------------------

class Styler:
    def __init__(self, style):
        style = style or {}
        self.base = {"font_family": style.get("font_family") or "Calibri", "font_size_pt": style.get("font_size_pt") or 10}
        self.parts = {k: v for k, v in style.items() if isinstance(v, dict)}
        self.alt = style.get("alt_row_background")

    def get(self, part):
        st = dict(self.base)
        st.update({k: v for k, v in (self.parts.get(part) or {}).items() if v is not None})
        return st


def border_xml(st):
    style = st.get("border_style") or "None"
    if style == "None":
        return "<Border><Style>None</Style></Border>"
    side = t("Color", st.get("border_color") or "#000000") + t("Style", style) + t("Width", border_width(st.get("border_width_pt")))
    sides = st.get("border_sides")
    if sides and set(sides) != {"top", "bottom", "left", "right"}:
        out = "<Border><Style>None</Style></Border>"
        for s in ("top", "bottom", "left", "right"):
            if s in sides:
                out += el(s.capitalize() + "Border", side)
        return out
    return el("Border", side)


def textbox(name, value, st, fmt=None, align=None, bg=None, hide_dup=None, pos=None, can_grow=True):
    run = ""
    if st.get("font_style") and st["font_style"] != "Normal":
        run += t("FontStyle", st["font_style"])
    run += t("FontFamily", st.get("font_family") or "Calibri") + t("FontSize", pt(st.get("font_size_pt") or 10))
    if st.get("font_weight") and st["font_weight"] != "Normal":
        run += t("FontWeight", st["font_weight"])
    if fmt:
        run += t("Format", fmt)
    if st.get("underline"):
        run += t("TextDecoration", "Underline")
    run += t("Color", st.get("color") or "#000000")
    align = align or st.get("text_align")
    para_style = t("TextAlign", align) if align and align != "General" else ""
    box = border_xml(st)
    background = bg or st.get("background")
    if background:
        box += t("BackgroundColor", background)
    if st.get("vertical_align") and st["vertical_align"] != "Top":
        box += t("VerticalAlign", st["vertical_align"])
    box += t("PaddingLeft", "2pt") + t("PaddingRight", "2pt") + t("PaddingTop", "1pt") + t("PaddingBottom", "1pt")
    parts = (t("CanGrow", "true" if can_grow else "false") + t("KeepTogether", "true")
             + el("Paragraphs", el("Paragraph", el("TextRuns", el("TextRun", t("Value", value) + el("Style", run)))
                                       + el("Style", para_style))))
    if hide_dup:
        parts += t("HideDuplicates", hide_dup)
    if pos:
        top, left, height, width = pos
        parts += t("Top", pt(top)) + t("Left", pt(left)) + t("Height", pt(height)) + t("Width", pt(width))
    return el("Textbox", parts + el("Style", box), {"Name": name})


def cell(content):
    return el("TablixCell", el("CellContents", content))


def tablix_row(height, cells):
    return el("TablixRow", t("Height", pt(height)) + el("TablixCells", "".join(cells)))


def agg_expr(col, default=None):
    a = col.get("aggregate", default)
    if not a:
        return None
    if a == "Expression":
        return col.get("total_expression")
    inner = "Fields!%s.Value" % col["field"] if col.get("field") else (col.get("expression") or "").lstrip("=").strip()
    return "=%s(%s)" % (a, inner)


def value_expr(col):
    return "=Fields!%s.Value" % col["field"] if col.get("field") else col.get("expression")


def sort_xml(field_or_expr, direction=None):
    v = field_or_expr if str(field_or_expr).startswith("=") else "=Fields!%s.Value" % field_or_expr
    return el("SortExpression", t("Value", v) + (t("Direction", "Descending") if direction == "Descending" else ""))


def group_xml(name, field, g=None):
    g = g or {}
    inner = el("GroupExpressions", t("GroupExpression", "=Fields!%s.Value" % field))
    if g.get("page_break"):
        inner += el("PageBreak", t("BreakLocation", "Between"))
    if g.get("sheet_name"):
        inner += t("PageName", g["sheet_name"])
    return el("Group", inner, {"Name": name})


# ----------------------------------------------------------------------------
# Table layout
# ----------------------------------------------------------------------------

def build_table(spec, styler, names):
    t_ = spec["layout"]["table"]
    cols = t_["columns"]
    groups = t_.get("row_groups") or []
    gt = t_.get("grand_total") or {}
    hdr_h = t_.get("header_row_height_pt", 20)
    row_h = t_.get("row_height_pt", 15)
    group_names = [names("grp_" + g["field"], "grp") for g in groups]
    field_to_group = {g["field"]: n for g, n in zip(groups, group_names)}

    rows = []
    hdr_st = styler.get("header")
    rows.append(tablix_row(hdr_h, [cell(textbox(names("hdr_" + (c.get("field") or c["header"]), "hdr"), c["header"], hdr_st,
                                                align=(hdr_st.get("text_align") or "Center"))) for c in cols]))
    det_st = styler.get("detail")
    alt_bg = None
    if styler.alt and not det_st.get("background"):
        alt_bg = '=IIf(RowNumber(Nothing) Mod 2 = 0, "%s", "Transparent")' % styler.alt
    det_cells = []
    for c in cols:
        hide = field_to_group.get(c.get("field")) if not t_.get("repeat_group_values", True) else None
        st = dict(det_st)
        for k in ("color", "font_weight", "font_style"):           # per-column overrides (colour may be an expression)
            if c.get(k):
                st[k] = c[k]
        bg = c.get("background") or alt_bg
        det_cells.append(cell(textbox(names("det_" + (c.get("field") or c["header"]), "det"), value_expr(c), st,
                                      fmt=c.get("format"), align=c.get("align"), bg=bg, hide_dup=hide)))
    rows.append(tablix_row(row_h, det_cells))

    def total_row(st_part, label, label_field, prefix):
        st = styler.get(st_part)
        label_idx = next((i for i, c in enumerate(cols) if c.get("field") == label_field), 0) if label_field else 0
        cells = []
        for i, c in enumerate(cols):
            expr = agg_expr(c)
            if i == label_idx and not expr:
                expr = label
            cells.append(cell(textbox(names(prefix + (c.get("field") or c["header"]), "tot"), expr or "", st,
                                      fmt=c.get("format") if c.get("aggregate") else None,
                                      align=c.get("align") if c.get("aggregate") else None)))
        return tablix_row(row_h, cells)

    for lvl in range(len(groups) - 1, -1, -1):      # leaf order: innermost subtotal first
        g = groups[lvl]
        if g.get("subtotal"):
            rows.append(total_row("subtotal", g.get("subtotal_label") or ("=Fields!%s.Value & \" Total\"" % g["field"]),
                                  g["field"], "sub%d_" % (lvl + 1)))
    if gt.get("show"):
        rows.append(total_row("grand_total", gt.get("label") or "Grand Total", None, "gt_"))

    details = el("TablixMember", el("Group", "", {"Name": "Details"})
                 + (el("SortExpressions", "".join(sort_xml(s["field"], s.get("direction")) for s in t_.get("detail_sort") or []))
                    if t_.get("detail_sort") else ""))
    inner = details
    for lvl in range(len(groups) - 1, -1, -1):
        g = groups[lvl]
        children = inner + (el("TablixMember", t("KeepWithGroup", "Before")) if g.get("subtotal") else "")
        inner = el("TablixMember", group_xml(group_names[lvl], g["field"], g)
                   + el("SortExpressions", sort_xml(g.get("sort_expression") or g["field"], g.get("sort")))
                   + el("TablixMembers", children))
    header_member = el("TablixMember", t("KeepWithGroup", "After")
                       + (t("RepeatOnNewPage", "true") if t_.get("repeat_header_rows", True) else ""))
    row_members = header_member + inner + (el("TablixMember", t("KeepWithGroup", "Before")) if gt.get("show") else "")
    width = sum(c["width_pt"] for c in cols)
    height = hdr_h + row_h * (len(rows) - 1)
    body = el("TablixBody", el("TablixColumns", "".join(el("TablixColumn", t("Width", pt(c["width_pt"]))) for c in cols))
              + el("TablixRows", "".join(rows)))
    return body, el("TablixMembers", "<TablixMember />" * len(cols)), el("TablixMembers", row_members), None, width, height


# ----------------------------------------------------------------------------
# Matrix layout
# ----------------------------------------------------------------------------

def build_matrix(spec, styler, names):
    t_ = spec["layout"]["table"]
    rgs = t_["row_groups"]
    cg = t_["column_group"]
    vals = t_["values"]
    gt = t_.get("grand_total") or {}
    hdr_h = t_.get("header_row_height_pt", 20)
    row_h = t_.get("row_height_pt", 15)
    hdr_st = styler.get("header")
    multi = len(vals) > 1
    depth = len(rgs)

    def value_headers(prefix):
        return "".join(el("TablixMember", el("TablixHeader", t("Size", pt(hdr_h)) + el("CellContents",
                       textbox(names(prefix + v["header"], "vh"), v["header"], hdr_st, align="Center")))) for v in vals)
    cg_header = el("TablixHeader", t("Size", pt(hdr_h)) + el("CellContents", textbox(
        names("colhdr_" + cg["field"]), cg.get("header_expression") or "=Fields!%s.Value" % cg["field"], hdr_st, align="Center")))
    col_members = el("TablixMember", group_xml(names("grp_" + cg["field"]), cg["field"])
                     + el("SortExpressions", sort_xml(cg.get("sort_expression") or cg["field"], cg.get("sort")))
                     + cg_header + (el("TablixMembers", value_headers("vh_")) if multi else ""))
    leaf_cols = list(vals)
    if cg.get("total"):
        col_members += el("TablixMember", el("TablixHeader", t("Size", pt(hdr_h)) + el("CellContents", textbox(
            names("colhdr_total"), cg.get("total_label") or "Total", hdr_st, align="Center")))
            + (el("TablixMembers", value_headers("vht_")) if multi else ""))
        leaf_cols += list(vals)

    leaf_rows = []

    def chain(level, label, st_part, kind):
        node = ""
        for lv in range(depth - 1, level - 1, -1):
            hdr = el("TablixHeader", t("Size", pt(rgs[lv]["width_pt"])) + el("CellContents", textbox(
                names("rh_%s_%d" % (kind, lv)), label if lv == level else "", styler.get(st_part))))
            node = el("TablixMember", hdr + (el("TablixMembers", node) if node else "")
                      + (t("KeepWithGroup", "Before") if lv == level else ""))
        return node

    def dynamic(level):
        g = rgs[level]
        hdr = el("TablixHeader", t("Size", pt(g["width_pt"])) + el("CellContents", textbox(
            names("rh_" + g["field"]), "=Fields!%s.Value" % g["field"], styler.get("detail"))))
        members = ""
        if level < depth - 1:
            inner = dynamic(level + 1)
            nxt = rgs[level + 1]
            if nxt.get("subtotal"):
                inner += chain(level + 1, nxt.get("subtotal_label") or "Total", "subtotal", "sub")
                leaf_rows.append("subtotal")
            members = el("TablixMembers", inner)
        else:
            leaf_rows.append("detail")
        return el("TablixMember", group_xml(names("grp_" + g["field"]), g["field"], g)
                  + el("SortExpressions", sort_xml(g.get("sort_expression") or g["field"], g.get("sort"))) + hdr + members)
    row_members = dynamic(0)
    if gt.get("show"):
        row_members += chain(0, gt.get("label") or "Grand Total", "grand_total", "gt")
        leaf_rows.append("grand_total")

    def value_cell(v, kind):
        expr = v.get("expression") or "=%s(Fields!%s.Value)" % (v.get("aggregate") or "Sum", v["field"])
        return cell(textbox(names("val_" + (v.get("field") or v["header"]), "val"), expr, styler.get(kind),
                            fmt=v.get("format"), align=v.get("align") or "Right"))
    rows = [tablix_row(row_h, [value_cell(v, kind) for v in leaf_cols]) for kind in leaf_rows]
    n_hdr_rows = 2 if multi else 1
    corner_rows = []
    for r in range(n_hdr_rows):
        cells = "".join(el("TablixCornerCell", el("CellContents", textbox(
            names("corner_%d" % i), (g.get("header") or g["field"]) if r == n_hdr_rows - 1 else "", hdr_st))) for i, g in enumerate(rgs))
        corner_rows.append(el("TablixCornerRow", cells))
    corner = el("TablixCorner", el("TablixCornerRows", "".join(corner_rows)))
    body = el("TablixBody", el("TablixColumns", "".join(el("TablixColumn", t("Width", pt(v["width_pt"]))) for v in leaf_cols))
              + el("TablixRows", "".join(rows)))
    width = sum(g["width_pt"] for g in rgs) + sum(v["width_pt"] for v in leaf_cols)
    height = hdr_h * n_hdr_rows + row_h * len(rows)
    return body, el("TablixMembers", col_members), el("TablixMembers", row_members), corner, width, height


# ----------------------------------------------------------------------------
# Report assembly
# ----------------------------------------------------------------------------

def data_sources_xml(spec):
    out = ""
    for s in spec["data_sources"]:
        cp = t("DataProvider", s["data_provider"]) + t("ConnectString", s["connect_string"])
        if s.get("integrated_security", s["data_provider"].upper() in ("SQL", "SQLAZURE", "OLEDB", "ODBC")):
            cp += t("IntegratedSecurity", "true")
        out += el("DataSource", el("ConnectionProperties", cp) + t("rd:SecurityType", "None")
                  + t("rd:DataSourceID", uuid.uuid4()), {"Name": s["name"]})
    return el("DataSources", out)


def datasets_xml(spec):
    providers = {s["name"]: s["data_provider"].upper() for s in spec["data_sources"]}
    out = ""
    for d in spec["datasets"]:
        as_style = providers.get(d["data_source"]) in AS_PROVIDERS
        qps = ""
        for q in d.get("query_parameters") or []:
            name = q["name"].lstrip("@") if as_style else ("@" + q["name"].lstrip("@"))
            qps += el("QueryParameter", t("Value", q["value"]), {"Name": name})
        query = t("DataSourceName", d["data_source"]) + (el("QueryParameters", qps) if qps else "") + t("CommandText", d["command_text"])
        fields = ""
        for f in d["fields"]:
            inner = t("Value", f["value"]) if f.get("value") else t("DataField", f.get("data_field") or f["name"])
            if f.get("type") in TYPE_NAMES and not f.get("value"):
                inner += t("rd:TypeName", TYPE_NAMES[f["type"]])
            fields += el("Field", inner, {"Name": f["name"]})
        out += el("DataSet", el("Query", query) + el("Fields", fields), {"Name": d["name"]})
    return el("DataSets", out)


def parameters_xml(spec):
    params = spec.get("parameters") or []
    if not params:
        return ""
    out = ""
    for p in params:
        inner = t("DataType", p["data_type"])
        if p.get("nullable"):
            inner += t("Nullable", "true")
        if p.get("default_from_dataset"):
            ref = p["default_from_dataset"]
            inner += el("DefaultValue", el("DataSetReference", t("DataSetName", ref["dataset"]) + t("ValueField", ref["value_field"])))
        elif p.get("default") not in (None, "", []):
            vals = p["default"] if isinstance(p["default"], list) else [p["default"]]
            inner += el("DefaultValue", el("Values", "".join(t("Value", v) for v in vals)))
        if p.get("allow_blank"):
            inner += t("AllowBlank", "true")
        inner += t("Prompt", p.get("prompt") or p["name"])
        vv = p.get("valid_values") or {}
        if vv.get("dataset"):
            inner += el("ValidValues", el("DataSetReference", t("DataSetName", vv["dataset"]) + t("ValueField", vv["value_field"])
                                          + t("LabelField", vv.get("label_field") or vv["value_field"])))
        elif vv.get("static"):
            inner += el("ValidValues", el("ParameterValues", "".join(el("ParameterValue", t("Value", x["value"]) + t("Label", x.get("label") or x["value"]))
                                                                     for x in vv["static"])))
        if p.get("hidden"):
            inner += t("Hidden", "true")
        if p.get("multi_value"):
            inner += t("MultiValue", "true")
        out += el("ReportParameter", inner, {"Name": p["name"]})
    cols = min(4, len(params))
    rows = int(math.ceil(len(params) / float(cols)))
    cells = "".join(el("CellDefinition", t("ColumnIndex", i % cols) + t("RowIndex", i // cols) + t("ParameterName", p["name"]))
                    for i, p in enumerate(params))
    layout = el("ReportParametersLayout", el("GridLayoutDefinition", t("NumberOfColumns", cols) + t("NumberOfRows", rows)
                                                                    + el("CellDefinitions", cells)))
    return el("ReportParameters", out) + layout


def title_items(spec, styler, names, width):
    lay = spec["layout"]
    items, y = [], 0
    title = (lay.get("title") or {}).get("text")
    tst = styler.get("title")
    if title:
        h = max(18, round((tst.get("font_size_pt") or 14) * 1.9))
        items.append(textbox(names("txtTitle"), title, tst, align=tst.get("text_align") if tst.get("text_align") != "General" else "Left",
                             pos=(y, 0, h, width)))
        y += h
    sst = styler.get("subtitle")
    for i, line in enumerate(lay.get("subtitle_lines") or []):
        h = max(14, round((sst.get("font_size_pt") or 10) * 1.8))
        items.append(textbox(names("txtSubtitle%d" % (i + 1)), line, sst, align="Left", pos=(y, 0, h, width)))
        y += h
    return items, y


def footer_xml(spec, styler, names, width):
    f = spec["layout"].get("footer") or {}
    st = dict(styler.get("detail"), font_size_pt=8, border_style="None", background=None)
    items = []
    half = int(width // 2)
    left = []
    if f.get("text"):
        left.append(f["text"] if f["text"].startswith("=") else '="%s"' % f["text"].replace('"', '""'))
    if f.get("execution_time"):
        left.append('="Run " & Format(Globals!ExecutionTime, "dd MMM yyyy HH:mm")')
    if left:
        expr = left[0] if len(left) == 1 else "=" + " & \"  |  \" & ".join(x.lstrip("=") for x in left)
        items.append(textbox(names("txtFooterLeft"), expr, st, align="Left", pos=(0, 0, 14, half)))
    if f.get("page_number", True):
        items.append(textbox(names("txtPageNumber"), '="Page " & Globals!PageNumber & " of " & Globals!TotalPages', st,
                             align="Right", pos=(0, half, 14, width - half)))
    if not items:
        return ""
    return el("PageFooter", t("Height", pt(16)) + t("PrintOnFirstPage", "true") + t("PrintOnLastPage", "true")
              + el("ReportItems", "".join(items)) + el("Style", "<Border><Style>None</Style></Border>"))


def build(spec):
    spec_tool.require_confirmed(spec)
    errors, warnings = spec_tool.validate(spec)
    if errors:
        rk.fail("The spec has errors: " + "; ".join(e for _, e in errors))
    if spec.get("report_type") != "paginated":
        rk.fail("rdl_build.py builds paginated reports; use pbip_build.py for Power BI reports")
    names = rk.UniqueNamer()
    names("Details")
    styler = Styler(spec.get("style"))
    lay = spec["layout"]
    mode = (lay.get("table") or {}).get("mode", "table")
    body, col_h, row_h, corner, tbl_w, tbl_h = (build_matrix if mode == "matrix" else build_table)(spec, styler, names)
    placement = (lay.get("title") or {}).get("placement", "body")
    titles, title_h = title_items(spec, styler, names, tbl_w)
    gap = 6 if titles else 0
    top = title_h + gap if placement == "body" else 0
    tablix = el("Tablix", (corner or "") + body + el("TablixColumnHierarchy", col_h) + el("TablixRowHierarchy", row_h)
                + t("RepeatColumnHeaders", "true") + (t("RepeatRowHeaders", "true") if mode == "matrix" else "")
                + t("DataSetName", lay["table"]["dataset"]) + t("NoRowsMessage", "No data for the selected parameters.")
                + t("Top", pt(top)) + t("Left", "0pt") + t("Height", pt(tbl_h)) + t("Width", pt(tbl_w))
                + el("Style", "<Border><Style>None</Style></Border>"), {"Name": names("tbl_" + lay["table"]["dataset"])})
    body_items = (titles if placement == "body" else []) + [tablix]
    body_h = top + tbl_h
    pg = lay.get("page") or {}
    m = pg.get("margins_pt") or {}
    page = ""
    if placement == "page_header" and titles:
        page += el("PageHeader", t("Height", pt(title_h + gap)) + t("PrintOnFirstPage", "true") + t("PrintOnLastPage", "true")
                   + el("ReportItems", "".join(titles)) + el("Style", "<Border><Style>None</Style></Border>"))
    page += footer_xml(spec, styler, names, tbl_w)
    page += (t("PageHeight", pt(pg.get("height_pt", 595))) + t("PageWidth", pt(pg.get("width_pt", 842)))
             + t("LeftMargin", pt(m.get("left", 36))) + t("RightMargin", pt(m.get("right", 36)))
             + t("TopMargin", pt(m.get("top", 36))) + t("BottomMargin", pt(m.get("bottom", 36))) + "<Style />")
    section = el("ReportSection", el("Body", el("ReportItems", "".join(body_items)) + t("Height", pt(body_h)) + "<Style />")
                 + t("Width", pt(tbl_w)) + el("Page", page))
    rep = spec["report"]
    conf = spec.get("confirmations") or {}
    comment = ("Generated by the report-development skill from spec '%s' version %s (data gate %s, spec gate %s). "
               "Open in Power BI Report Builder to review before publishing." % (
                   rep["name"], rep.get("version", 1), (conf.get("data") or {}).get("hash", "")[:12],
                   (conf.get("spec") or {}).get("hash", "")[:12])).replace("--", "-")
    sheet = (spec.get("excel_export") or {}).get("initial_sheet_name")
    xml = ('<?xml version="1.0" encoding="utf-8"?>\n<!-- %s -->\n<Report xmlns="%s" xmlns:rd="%s">' % (comment, NS, RD)
           + t("Description", (rep.get("description") or rep["name"]) + " (spec v%s)" % rep.get("version", 1))
           + (t("Author", rep["requested_by"]) if rep.get("requested_by") else "")
           + t("AutoRefresh", "0") + data_sources_xml(spec) + datasets_xml(spec) + el("ReportSections", section)
           + parameters_xml(spec) + (t("Language", rep["language"]) if rep.get("language") else "")
           + (t("InitialPageName", sheet) if sheet else "")
           + t("rd:ReportUnitType", "Inch") + t("rd:ReportID", uuid.uuid4()) + "</Report>\n")
    ET.fromstring(xml.encode("utf-8"))          # well-formedness check
    return xml, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    spec = rk.load_json(a.spec)
    xml, warnings = build(spec)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(xml)
    for w in warnings:
        print("WARNING: " + w)
    print("wrote %s (%d bytes)" % (a.out, len(xml.encode("utf-8"))))


if __name__ == "__main__":
    main()
