#!/usr/bin/env python3
"""Create, validate and confirm report specs: the contract between the user and the build scripts.

Usage:
  python spec_tool.py new --type paginated|powerbi|semantic_model --name "Report name" --out spec.json
  python spec_tool.py validate spec.json [--gate data|spec]
  python spec_tool.py summary spec.json --gate data|spec     Markdown for the confirmation message
  python spec_tool.py confirm spec.json --gate data|spec --reply "<user's exact reply>" [--by "Name"]
  python spec_tool.py check spec.json                        exit 0 only if both gates are confirmed and unchanged
  python spec_tool.py diff old.json new.json                 what changed, and which gate must be re-confirmed
  python spec_tool.py bump spec.json                         increase report.version after a change request

Spec types: paginated (an .rdl report), powerbi (a .pbip report on a published semantic model)
and semantic_model (a TMDL semantic model built from SQL sources).
Gate "data" covers the plan, data sources, and datasets/fields/tables. Gate "spec" covers the
specification and layout (or, for a model, relationships, measures and the date table).
Confirming stores a hash of the gate's sections; any later edit to those sections makes
`check` (and therefore the build scripts) fail until the user confirms again.
Development can't start on unverified data: every data source needs access_verified, and every
query/table needs a recorded test run, before a gate can be confirmed or a file built.
"""
import argparse
import collections
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402
import tmdl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "..", "references")
GATE_SECTIONS = {
    "paginated": {"data": ["plan", "data_sources", "datasets"],
                  "spec": ["report", "parameters", "layout", "style", "excel_export", "validation"]},
    "powerbi": {"data": ["plan", "data_sources", "fields"],
                "spec": ["report", "exemplar", "pages", "style", "validation"]},
    "semantic_model": {"data": ["plan", "data_sources", "tables"],
                       "spec": ["report", "relationships", "measures", "date_table", "check_page", "exemplar", "validation"]},
}
TYPE_NAMES = {"paginated": "paginated report", "powerbi": "Power BI report", "semantic_model": "semantic model"}
APPROACHES = {"direct", "model_first"}
VOLATILE_KEYS = {"verified", "access_verified", "verified_unique", "_comment", "agent_notes"}
SM_TYPES = {"string", "int64", "double", "decimal", "dateTime", "boolean"}
SM_SUMMARIZE = {None, "none", "sum", "count", "min", "max", "average", "distinctCount"}
WRITE_SQL = re.compile(r"(?i)\b(insert|update|delete|merge|drop|alter|create|exec|execute|truncate|grant|revoke)\b")
DATA_TYPES = {"String", "Integer", "Float", "DateTime", "Boolean"}
AGGREGATES = {None, "Sum", "Avg", "Min", "Max", "Count", "CountDistinct", "Expression"}
ALIGNS = {None, "General", "Left", "Center", "Right"}
CHANGE_WORDS = re.compile(r"(?i)\b(no|not|don't|dont|change|instead|but|except|wrong|remove|add|replace|rename|missing|should)\b")


def strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: strip_volatile(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [strip_volatile(v) for v in obj]
    return obj


def section_hashes(spec, gate):
    sections = GATE_SECTIONS[spec["report_type"]][gate]
    return {s: rk.canonical_hash(strip_volatile(spec.get(s))) for s in sections}


def gate_hash(spec, gate):
    return rk.canonical_hash(section_hashes(spec, gate))


def gate_status(spec, gate):
    conf = (spec.get("confirmations") or {}).get(gate)
    if not conf:
        return "not confirmed", []
    if conf.get("hash") == gate_hash(spec, gate):
        return "confirmed", []
    now = section_hashes(spec, gate)
    changed = [s for s, h in now.items() if (conf.get("section_hashes") or {}).get(s) != h]
    return "changed since confirmation", changed


def require_confirmed(spec):
    """Used by build scripts. Exits with a clear message unless both gates are current."""
    problems = []
    for gate in ("data", "spec"):
        status, changed = gate_status(spec, gate)
        if status != "confirmed":
            problems.append("gate '%s' is %s%s" % (gate, status, (" (changed: %s)" % ", ".join(changed)) if changed else ""))
    if problems:
        rk.fail("The spec is not confirmed by the user: %s. Show the summary for that gate, get the user's explicit "
                "confirmation, and record it with spec_tool.py confirm." % "; ".join(problems), code=3)


# ----------------------------------------------------------------------------
# Validation. Errors are (section, message) so each gate checks only its own sections.
# ----------------------------------------------------------------------------

def _ident(name):
    return bool(name) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) is not None


def validate(spec):
    errors, warnings = [], []
    rt = spec.get("report_type")
    if rt not in GATE_SECTIONS:
        return [("report", "report_type must be 'paginated', 'powerbi' or 'semantic_model'")], warnings
    plan = spec.get("plan") or {}
    if plan and plan.get("approach") not in APPROACHES:
        errors.append(("plan", "plan.approach must be 'direct' or 'model_first'"))
    if rt == "semantic_model" and plan.get("approach") != "model_first":
        errors.append(("plan", "a semantic model spec needs plan.approach 'model_first' (and plan.next: the report type to build on it)"))
    rep = spec.get("report") or {}
    if not rep.get("name"):
        errors.append(("report", "report.name is required"))
    if not rep.get("file_name") or not re.match(r"^[A-Za-z0-9 _.\-()]+$", rep.get("file_name", "")):
        errors.append(("report", "report.file_name is required (letters, digits, space, _ . - ( ) only)"))
    srcs = spec.get("data_sources") or []
    if not srcs:
        errors.append(("data_sources", "at least one data source is required"))
    for s in srcs:
        conn = s.get("connect_string") or s.get("pbir_connection_string") or ""
        if rk.mask_secrets(conn)[1] or re.search(r"(?i)\b(user id|uid)\s*=", conn):
            errors.append(("data_sources", "data source '%s' contains credentials; remove them (credentials are bound "
                                           "in the Power BI service after publishing)" % s.get("name")))
        if s.get("access_verified") is not True:
            errors.append(("data_sources", "access to data source '%s' hasn't been verified with the user's sign-in "
                                           "(step 3); development can't start on unverified data" % s.get("name")))
    if rt == "paginated":
        _validate_paginated(spec, errors, warnings)
    elif rt == "powerbi":
        _validate_powerbi(spec, errors, warnings)
    else:
        _validate_semantic_model(spec, errors, warnings)
    for q in spec.get("open_questions") or []:
        warnings.append("open question: %s" % q)
    return errors, warnings


def _validate_paginated(spec, errors, warnings):
    src_names = {s.get("name") for s in spec.get("data_sources") or []}
    for s in spec.get("data_sources") or []:
        if not _ident(s.get("name")):
            errors.append(("data_sources", "data source name '%s' must be an identifier" % s.get("name")))
        if not s.get("data_provider") or not s.get("connect_string"):
            errors.append(("data_sources", "data source '%s' needs data_provider and connect_string" % s.get("name")))
    fields_by_ds = {}
    if not spec.get("datasets"):
        errors.append(("datasets", "at least one dataset is required"))
    for d in spec.get("datasets") or []:
        if not _ident(d.get("name")):
            errors.append(("datasets", "dataset name '%s' must be an identifier" % d.get("name")))
        if d.get("data_source") not in src_names:
            errors.append(("datasets", "dataset '%s' refers to unknown data source '%s'" % (d.get("name"), d.get("data_source"))))
        if not (d.get("command_text") or "").strip():
            errors.append(("datasets", "dataset '%s' has no query (command_text)" % d.get("name")))
        names = [f.get("name") for f in d.get("fields") or []]
        if not names:
            errors.append(("datasets", "dataset '%s' has no fields" % d.get("name")))
        for n in names:
            if not _ident(n):
                errors.append(("datasets", "field name '%s' in dataset '%s' must be an identifier" % (n, d.get("name"))))
        if len(set(names)) != len(names):
            errors.append(("datasets", "dataset '%s' has duplicate field names" % d.get("name")))
        fields_by_ds[d.get("name")] = set(names)
        if not (d.get("verified") or {}).get("executed"):
            errors.append(("datasets", "dataset '%s' query hasn't been test-run against the source "
                                       "(datasets[].verified.executed)" % d.get("name")))
        if WRITE_SQL.search(re.sub(r"'[^']*'", "", d.get("command_text") or "")) and (d.get("query_language") or "").upper() == "SQL":
            errors.append(("datasets", "dataset '%s' query contains a statement that changes data; only SELECT is allowed" % d.get("name")))
    params = {p.get("name") for p in spec.get("parameters") or []}
    for p in spec.get("parameters") or []:
        if not _ident(p.get("name")):
            errors.append(("parameters", "parameter name '%s' must be an identifier" % p.get("name")))
        if p.get("data_type") not in DATA_TYPES:
            errors.append(("parameters", "parameter '%s' data_type must be one of %s" % (p.get("name"), sorted(DATA_TYPES))))
        for key in ("valid_values", "default_from_dataset"):
            ref = (p.get(key) or {}).get("dataset")
            if ref and ref not in fields_by_ds:
                errors.append(("parameters", "parameter '%s' %s uses unknown dataset '%s'" % (p.get("name"), key, ref)))
    for d in spec.get("datasets") or []:
        for qp in d.get("query_parameters") or []:
            for ref in re.findall(r"Parameters!(\w+)\.", qp.get("value") or ""):
                if ref not in params:
                    errors.append(("parameters", "query parameter '%s' uses undefined report parameter '%s'" % (qp.get("name"), ref)))
    lay = spec.get("layout") or {}
    t = lay.get("table") or {}
    ds = t.get("dataset")
    if ds not in fields_by_ds:
        errors.append(("layout", "layout.table.dataset '%s' is not a dataset" % ds))
    fields = fields_by_ds.get(ds, set())

    def check_expr(expr, where):
        for ref in re.findall(r"Fields!(\w+)\.", expr or ""):
            if ref not in fields:
                errors.append(("layout", "%s uses unknown field '%s'" % (where, ref)))
        for ref in re.findall(r"Parameters!(\w+)\.", expr or ""):
            if ref not in params:
                errors.append(("layout", "%s uses unknown parameter '%s'" % (where, ref)))
    mode = t.get("mode", "table")
    width = 0
    if mode == "table":
        cols = t.get("columns") or []
        if not cols:
            errors.append(("layout", "layout.table.columns is empty"))
        for i, c in enumerate(cols):
            where = "column %d '%s'" % (i + 1, c.get("header"))
            if not c.get("field") and not c.get("expression"):
                errors.append(("layout", where + " needs a field or an expression"))
            if c.get("field") and c["field"] not in fields:
                errors.append(("layout", where + " uses unknown field '%s'" % c["field"]))
            check_expr(c.get("expression"), where)
            check_expr(c.get("total_expression"), where + " total")
            if c.get("aggregate") not in AGGREGATES:
                errors.append(("layout", where + " aggregate must be one of Sum/Avg/Min/Max/Count/CountDistinct/Expression or null"))
            if c.get("aggregate") == "Expression" and not c.get("total_expression"):
                errors.append(("layout", where + " uses aggregate 'Expression' but has no total_expression"))
            if c.get("align") not in ALIGNS:
                errors.append(("layout", where + " align must be Left/Center/Right/General"))
            for k in ("color", "background"):
                if c.get(k) and not rk.is_valid_color(c[k]):
                    errors.append(("layout", where + " %s '%s' is not a colour or expression" % (k, c[k])))
                if c.get(k) and str(c[k]).startswith("="):
                    check_expr(c[k], where + " " + k)
            if not isinstance(c.get("width_pt"), (int, float)) or c["width_pt"] <= 0:
                errors.append(("layout", where + " width_pt must be a positive number"))
        for g in t.get("row_groups") or []:
            if g.get("field") not in fields:
                errors.append(("layout", "row group uses unknown field '%s'" % g.get("field")))
            check_expr(g.get("subtotal_label"), "row group '%s' subtotal label" % g.get("field"))
            check_expr(g.get("sheet_name"), "row group '%s' sheet name" % g.get("field"))
        for s in t.get("detail_sort") or []:
            if s.get("field") not in fields:
                errors.append(("layout", "detail sort uses unknown field '%s'" % s.get("field")))
        width = sum(c.get("width_pt") or 0 for c in cols)
    else:
        rgs = t.get("row_groups") or []
        cg = t.get("column_group") or {}
        vals = t.get("values") or []
        if not rgs or not cg or not vals:
            errors.append(("layout", "matrix layout needs row_groups, column_group and values"))
        for g in rgs:
            if g.get("field") not in fields:
                errors.append(("layout", "matrix row group uses unknown field '%s'" % g.get("field")))
        if cg and cg.get("field") not in fields:
            errors.append(("layout", "matrix column group uses unknown field '%s'" % cg.get("field")))
        check_expr(cg.get("sort_expression"), "column group sort")
        check_expr(cg.get("header_expression"), "column group header")
        for v in vals:
            if not v.get("field") and not v.get("expression"):
                errors.append(("layout", "matrix value '%s' needs a field or an expression" % v.get("header")))
            if v.get("field") and v["field"] not in fields:
                errors.append(("layout", "matrix value '%s' uses unknown field '%s'" % (v.get("header"), v["field"])))
            check_expr(v.get("expression"), "matrix value '%s'" % v.get("header"))
        warnings.append("matrix width depends on the number of column-group values; check the page width in a preview")
    for s in (lay.get("subtitle_lines") or []):
        check_expr(s, "subtitle")
    pg = lay.get("page") or {}
    m = pg.get("margins_pt") or {}
    usable = (pg.get("width_pt") or 0) - m.get("left", 0) - m.get("right", 0)
    if mode == "table" and usable and width > usable + 0.5:
        warnings.append("table width %dpt exceeds the printable page width %dpt: PDF exports will spill onto extra pages" % (width, usable))
    for part, s in (spec.get("style") or {}).items():
        if isinstance(s, dict):
            for k in ("color", "background", "border_color"):
                if s.get(k) and not rk.is_valid_color(s[k]):
                    errors.append(("style", "style.%s.%s '%s' is not a colour" % (part, k, s[k])))
    sheet = (spec.get("excel_export") or {}).get("initial_sheet_name") or ""
    if len(sheet) > 31 or re.search(r"[\[\]:*?/\\]", sheet):
        errors.append(("excel_export", "excel_export.initial_sheet_name must be <= 31 characters without [ ] : * ? / \\"))


def _validate_powerbi(spec, errors, warnings):
    src = (spec.get("data_sources") or [{}])[0]
    if src.get("kind") != "powerbi_semantic_model":
        errors.append(("data_sources", "Power BI reports must connect to a published semantic model (data_sources[0].kind = powerbi_semantic_model)"))
    if not src.get("pbir_connection_string") and not (src.get("workspace") and src.get("model_name")):
        errors.append(("data_sources", "data source needs pbir_connection_string or workspace + model_name (+ model_id)"))
    ids = [f.get("id") for f in spec.get("fields") or []]
    if not ids:
        errors.append(("fields", "list the semantic-model fields the report uses"))
    if len(set(ids)) != len(ids):
        errors.append(("fields", "field ids must be unique"))
    for f in spec.get("fields") or []:
        if f.get("kind") not in ("column", "measure"):
            errors.append(("fields", "field '%s' kind must be column or measure" % f.get("id")))
        if not f.get("table") or not f.get("name"):
            errors.append(("fields", "field '%s' needs table and name" % f.get("id")))
    if not (spec.get("exemplar") or {}).get("file"):
        warnings.append("no exemplar report given; the build will use the starter template from config/org-config.json")
    pages = spec.get("pages") or []
    if not pages:
        errors.append(("pages", "at least one page is required"))
    for p in pages:
        w, h = p.get("width", 1280), p.get("height", 720)
        for v in p.get("visuals") or []:
            where = "page '%s' visual '%s'" % (p.get("name"), v.get("title") or v.get("type"))
            if not v.get("type"):
                errors.append(("pages", where + " needs a type"))
            for role, refs in (v.get("roles") or {}).items():
                for r in refs:
                    if r not in ids:
                        errors.append(("pages", "%s role %s uses unknown field id '%s'" % (where, role, r)))
            pos = v.get("position") or {}
            if any(k not in pos for k in ("x", "y", "width", "height")):
                errors.append(("pages", where + " needs position x, y, width, height"))
            elif pos["x"] + pos["width"] > w + 1 or pos["y"] + pos["height"] > h + 1:
                warnings.append(where + " extends past the page edge")


def _validate_semantic_model(spec, errors, warnings):
    srcs = {s.get("name"): s for s in spec.get("data_sources") or []}
    for s in srcs.values():
        if s.get("kind") != "sql":
            errors.append(("data_sources", "data source '%s': models can be built from SQL sources only" % s.get("name")))
        if not s.get("server") or not s.get("database"):
            errors.append(("data_sources", "data source '%s' needs server and database" % s.get("name")))
    tables = spec.get("tables") or []
    if not tables:
        errors.append(("tables", "list the tables to load"))
    counts = collections.Counter((t.get("name") or "").lower() for t in tables)
    for n, k in counts.items():
        if k > 1:
            errors.append(("tables", "table '%s' is listed twice" % n))
    cols_by_table = {}
    for t in tables:
        where = "table '%s'" % t.get("name")
        if not t.get("name"):
            errors.append(("tables", "every table needs a name"))
        if t.get("data_source") not in srcs:
            errors.append(("tables", where + " uses unknown data source '%s'" % t.get("data_source")))
        src = t.get("source") or {}
        if not (src.get("object") or src.get("query")):
            errors.append(("tables", where + " needs source.object (table or view) or source.query"))
        if src.get("query"):
            if not re.match(r"(?is)^\s*(select|with)\b", src["query"]) or WRITE_SQL.search(re.sub(r"'[^']*'", "", src["query"])):
                errors.append(("tables", where + " source.query must be a read-only SELECT"))
        if t.get("mode", "import") not in ("import", "directQuery"):
            errors.append(("tables", where + " mode must be import or directQuery"))
        cols = t.get("columns") or []
        if not cols:
            errors.append(("tables", where + " has no columns"))
        names = collections.Counter((c.get("name") or "").lower() for c in cols)
        for n, k in names.items():
            if k > 1:
                errors.append(("tables", where + " has duplicate column '%s'" % n))
        for c in cols:
            cw = "%s column '%s'" % (where, c.get("name"))
            if c.get("data_type") not in SM_TYPES:
                errors.append(("tables", cw + " data_type must be one of %s" % sorted(SM_TYPES)))
            if not c.get("expression") and not c.get("source_column"):
                errors.append(("tables", cw + " needs source_column (or a DAX expression)"))
            if c.get("summarize_by") not in SM_SUMMARIZE:
                errors.append(("tables", cw + " summarize_by must be one of none/sum/count/min/max/average/distinctCount"))
            if c.get("sort_by") and c["sort_by"].lower() not in names:
                errors.append(("tables", cw + " sorts by unknown column '%s'" % c["sort_by"]))
        if not (t.get("verified") or {}).get("executed"):
            errors.append(("tables", where + " hasn't been test-queried against the source (tables[].verified.executed)"))
        cols_by_table[t.get("name")] = {c.get("name"): c for c in cols}
    dt = spec.get("date_table") or {}
    if dt.get("create"):
        dname = dt.get("name", "Date")
        if dname.lower() in counts:
            errors.append(("date_table", "date table name '%s' clashes with a loaded table" % dname))
        try:
            if datetime.date.fromisoformat(dt["start"]) >= datetime.date.fromisoformat(dt["end"]):
                errors.append(("date_table", "date_table.start must be before date_table.end"))
        except (KeyError, ValueError):
            errors.append(("date_table", "date_table needs start and end as YYYY-MM-DD"))
        cols_by_table[dname] = {c[0]: {"name": c[0], "data_type": c[1]} for c in tmdl.DATE_COLUMNS}
        for r in dt.get("relationships") or []:
            col = (cols_by_table.get(r.get("table")) or {}).get(r.get("column"))
            if not col:
                errors.append(("date_table", "date relationship uses unknown column '%s'[%s]" % (r.get("table"), r.get("column"))))
            elif col.get("data_type") != "dateTime":
                errors.append(("date_table", "date relationship column '%s'[%s] must be dateTime" % (r.get("table"), r.get("column"))))
    lower_tables = {(k or "").lower(): k for k in cols_by_table}

    def column(tname, cname):
        t = cols_by_table.get(lower_tables.get((tname or "").lower()))
        if t is None:
            return None
        return next((c for n, c in t.items() if (n or "").lower() == (cname or "").lower()), None)
    active = collections.Counter()
    seen = set()
    for r in spec.get("relationships") or []:
        a, b = column(r.get("from_table"), r.get("from_column")), column(r.get("to_table"), r.get("to_column"))
        rw = "relationship %s[%s] -> %s[%s]" % (r.get("from_table"), r.get("from_column"), r.get("to_table"), r.get("to_column"))
        if not a or not b:
            errors.append(("relationships", rw + " uses an unknown table or column"))
            continue
        if a.get("data_type") != b.get("data_type"):
            errors.append(("relationships", rw + " joins different data types (%s vs %s)" % (a.get("data_type"), b.get("data_type"))))
        if (r.get("from_table") or "").lower() == (r.get("to_table") or "").lower():
            errors.append(("relationships", rw + " joins a table to itself"))
        key = tuple((x or "").lower() for x in (r.get("from_table"), r.get("from_column"), r.get("to_table"), r.get("to_column")))
        if key in seen:
            errors.append(("relationships", rw + " is listed twice"))
        seen.add(key)
        if r.get("active", True):
            active[frozenset((key[0], key[2]))] += 1
        if r.get("cross_filter") not in (None, "single", "both"):
            errors.append(("relationships", rw + " cross_filter must be single or both"))
        if not r.get("verified_unique"):
            errors.append(("relationships", rw + ": check with SQL that %s[%s] is unique (relationships[].verified_unique)"
                           % (r.get("to_table"), r.get("to_column"))))
    for pair, n in active.items():
        if n > 1:
            errors.append(("relationships", "more than one active relationship between %s" % " and ".join(sorted(pair))))
    measure_names = collections.Counter((m.get("name") or "").lower() for m in spec.get("measures") or [])
    for n, k in measure_names.items():
        if k > 1:
            errors.append(("measures", "measure '%s' is defined twice" % n))
    for m in spec.get("measures") or []:
        mw = "measure [%s]" % m.get("name")
        if m.get("table") not in cols_by_table:
            errors.append(("measures", mw + " belongs to unknown table '%s'" % m.get("table")))
            continue
        if column(m.get("table"), m.get("name")):
            errors.append(("measures", mw + " has the same name as a column of '%s'" % m.get("table")))
        prob = tmdl.dax_syntax_problem(m.get("expression") or "")
        if prob or not (m.get("expression") or "").strip():
            errors.append(("measures", mw + " DAX has %s" % (prob or "no expression")))
        qualified, bare, _ = tmdl.dax_references(m.get("expression") or "")
        for t, cname in qualified:
            if not column(t, cname) and cname.lower() not in measure_names:
                errors.append(("measures", mw + " uses unknown '%s'[%s]" % (t, cname)))
        for b in bare:
            if b.lower() not in measure_names:
                errors.append(("measures", mw + " uses [%s], which isn't a measure" % b))
    cp = spec.get("check_page") or {}
    for r in cp.get("rows") or []:
        if not column(r.get("table"), r.get("column")):
            errors.append(("check_page", "check page uses unknown column '%s'[%s]" % (r.get("table"), r.get("column"))))
    for name in cp.get("measures") or []:
        if name.lower() not in measure_names:
            errors.append(("check_page", "check page uses unknown measure [%s]" % name))
    if not (spec.get("exemplar") or {}).get("file"):
        warnings.append("no exemplar given; the model-check report needs the starter template from config/org-config.json")


def errors_for_gate(spec, errors, gate):
    if gate is None:
        return errors
    sections = set(GATE_SECTIONS[spec["report_type"]][gate])
    return [e for e in errors if e[0] in sections]


# ----------------------------------------------------------------------------
# Summaries for the confirmation gates
# ----------------------------------------------------------------------------

def _row(*cells):
    return "| " + " | ".join("" if c is None else str(c).replace("|", "\\|").replace("\n", " ") for c in cells) + " |"


def phase_note(spec):
    plan = spec.get("plan") or {}
    if plan.get("approach") != "model_first":
        return ""
    if spec["report_type"] == "semantic_model":
        return " (phase 1 of 2: semantic model)"
    return " (phase 2 of 2: report on the new semantic model)"


def plan_lines(spec):
    plan = spec.get("plan") or {}
    if not plan:
        return []
    if plan.get("approach") == "model_first":
        text = ("build a semantic model from the SQL source first (phase 1); you publish it; then build the %s on it (phase 2)"
                % TYPE_NAMES.get(plan.get("next"), "report"))
    else:
        text = "build the %s directly on the data source" % TYPE_NAMES.get(spec["report_type"], "report")
    out = ["**Plan:** %s." % text]
    if plan.get("reason"):
        out.append("Why: %s" % plan["reason"])
    return out + [""]


def _data_sources_table(spec):
    out = ["**Data sources**", "", _row("Name", "Type", "Where", "Identified from", "Access checked with your sign-in"),
           _row("---", "---", "---", "---", "---")]
    for s in spec.get("data_sources") or []:
        where = s.get("display") or " / ".join(x for x in (s.get("workspace"), s.get("model_name")) if x) or \
            " / ".join(x for x in (s.get("server"), s.get("database")) if x) or \
            rk.classify_connection(s.get("data_provider"), s.get("connect_string")).get("server")
        out.append(_row(s.get("name"), s.get("kind"), where, s.get("identified_from"), "yes" if s.get("access_verified") else "NO"))
    return out


def summary(spec, gate):
    rt = spec["report_type"]
    v = (spec.get("report") or {}).get("version", 1)
    note = phase_note(spec)
    out = []
    if gate == "data":
        out += ["### Step 4 of 8: Confirm the data%s (spec v%s)" % (note, v), ""] + plan_lines(spec) + _data_sources_table(spec)
        if rt == "paginated":
            for d in spec.get("datasets") or []:
                ver = d.get("verified") or {}
                status = ("test run OK: %s rows" % ver.get("rows")) if ver.get("executed") else "NOT test-run yet"
                out += ["", "**Dataset `%s`**: %s query on `%s` (%s)" % (d["name"], d.get("query_language", ""), d.get("data_source"), status), "",
                        "```" + ("sql" if (d.get("query_language") or "").upper() == "SQL" else ""),
                        (d.get("command_text") or "").strip(), "```", "",
                        _row("Report field", "Source column", "Type", "Notes"), _row("---", "---", "---", "---")]
                for f in d.get("fields") or []:
                    out.append(_row(f.get("name"), f.get("data_field"), f.get("type"), f.get("description")))
                if d.get("query_parameters"):
                    out += ["", "Filters passed to the query: " + ", ".join("`%s` <- %s" % (q["name"], q["value"]) for q in d["query_parameters"])]
        elif rt == "powerbi":
            out += ["", "**Fields from the semantic model**", "", _row("Id", "Table", "Field", "Kind", "Notes"), _row("---", "---", "---", "---", "---")]
            for f in spec.get("fields") or []:
                out.append(_row(f.get("id"), f.get("table"), f.get("name"), f.get("kind"), f.get("description")))
        else:
            for t in spec.get("tables") or []:
                src = t.get("source") or {}
                origin = ("%s.%s" % (src.get("schema", "dbo"), src["object"])) if src.get("object") else "SQL query"
                ver = t.get("verified") or {}
                out += ["", "**Table `%s`** (%s) from `%s` on `%s`, %s mode; %s" % (
                    t.get("name"), t.get("role", "table"), origin, t.get("data_source"), t.get("mode", "import"),
                    ("test query OK: %s rows" % ver.get("rows")) if ver.get("executed") else "NOT test-queried yet")]
                if src.get("query"):
                    out += ["", "```sql", src["query"].strip(), "```"]
                out += ["", _row("Column", "Source column", "Type", "Visible", "Summarise"), _row("---", "---", "---", "---", "---")]
                for c in t.get("columns") or []:
                    out.append(_row(c.get("name"), c.get("source_column") or ("= " + (c.get("expression") or "")), c.get("data_type"),
                                    "no" if c.get("hidden") else "yes", c.get("summarize_by") or "none"))
        ask = "Reply **CONFIRM DATA** to approve the plan, data sources and fields, or tell me what to change."
    else:
        title = "the model design" if rt == "semantic_model" else "the report specification and layout"
        out += ["### Step 5 of 8: Confirm %s%s (spec v%s)" % (title, note, v), ""]
        rep = spec.get("report") or {}
        if rt == "paginated":
            lay = spec.get("layout") or {}
            pg = lay.get("page") or {}
            t = lay.get("table") or {}
            out += ["- **Output:** paginated report `%s.rdl`. You publish it and export it to Excel or PDF (primary export: %s)." % (rep.get("file_name"), rep.get("primary_export", "excel")),
                    "- **Page:** %s, %s x %s pt, margins %s pt." % (pg.get("orientation"), pg.get("width_pt"), pg.get("height_pt"), pg.get("margins_pt")),
                    "- **Title:** %s (%s); subtitle lines: %s" % ((lay.get("title") or {}).get("text"), (lay.get("title") or {}).get("placement", "body"),
                                                                   "; ".join(lay.get("subtitle_lines") or []) or "none"),
                    "- **Excel sheet name:** %s" % (spec.get("excel_export") or {}).get("initial_sheet_name")]
            if spec.get("parameters"):
                out += ["", "**Parameters**", "", _row("Name", "Type", "Prompt", "Default", "Multi-value", "List of values"), _row("---", "---", "---", "---", "---", "---")]
                for p in spec["parameters"]:
                    vv = p.get("valid_values") or {}
                    out.append(_row(p["name"], p.get("data_type"), p.get("prompt"), p.get("default"), "yes" if p.get("multi_value") else "no",
                                    vv.get("dataset") or ("static list" if vv.get("static") else "free entry")))
            if t.get("mode", "table") == "table":
                out += ["", "**Columns (left to right)**", "", _row("#", "Header", "Value", "Format", "Width pt", "Align", "Total"), _row("---", "---", "---", "---", "---", "---", "---")]
                for i, c in enumerate(t.get("columns") or [], 1):
                    out.append(_row(i, c.get("header"), c.get("field") or c.get("expression"), c.get("format"), c.get("width_pt"), c.get("align"),
                                    c.get("total_expression") if c.get("aggregate") == "Expression" else c.get("aggregate")))
                groups = t.get("row_groups") or []
                out += ["", "- **Grouping:** " + ("; ".join("by %s%s%s" % (g["field"], ", subtotal '%s'" % g.get("subtotal_label") if g.get("subtotal") else "",
                                                                         ", new sheet per value" if g.get("page_break") else "") for g in groups) or "none"),
                        "- **Detail sort:** " + (", ".join("%s %s" % (s["field"], s.get("direction", "Ascending")) for s in t.get("detail_sort") or []) or "query order"),
                        "- **Grand total:** " + ("yes, '%s'" % (t.get("grand_total") or {}).get("label") if (t.get("grand_total") or {}).get("show") else "no")]
            else:
                cg = t.get("column_group") or {}
                out += ["", "**Matrix (crosstab)**", "",
                        "- Rows: " + ", ".join("%s%s" % (g["field"], " (subtotal)" if g.get("subtotal") else "") for g in t.get("row_groups") or []),
                        "- Columns: one per %s%s" % (cg.get("field"), ", plus a total column" if cg.get("total") else ""),
                        "- Values: " + ", ".join("%s = %s(%s) [%s]" % (v_.get("header"), v_.get("aggregate", "Sum"), v_.get("field") or v_.get("expression"), v_.get("format")) for v_ in t.get("values") or [])]
            st = spec.get("style") or {}
            out += ["", "**Formatting (taken from your sample)**", "",
                    "- Font: %s %spt" % (st.get("font_family"), st.get("font_size_pt"))]
            for part in ("title", "header", "detail", "subtotal", "grand_total"):
                s = st.get(part) or {}
                if s:
                    out.append("- %s: %s" % (part.replace("_", " ").capitalize(), ", ".join("%s %s" % (k.replace("_", " "), val) for k, val in s.items() if val not in (None, ""))))
            if st.get("alt_row_background"):
                out.append("- Alternate row shading: %s" % st["alt_row_background"])
            notes = (spec.get("excel_export") or {}).get("notes") or []
            if notes:
                out += ["", "**Differences you should expect in the Excel export**", ""] + ["- " + n for n in notes]
        elif rt == "powerbi":
            ex = spec.get("exemplar") or {}
            out += ["- **Output:** Power BI project `%s` (zip). You open it in Power BI Desktop and publish it yourself." % (rep.get("file_name") + "_pbip.zip"),
                    "- **Look and feel:** copied from `%s` (theme%s)." % (ex.get("file") or "the starter template", ", page background" if ex.get("keep_page_background", True) else "")]
            fields = {f["id"]: "%s[%s]" % (f["table"], f["name"]) for f in spec.get("fields") or []}
            for p in spec.get("pages") or []:
                out += ["", "**Page '%s'** (%sx%s)" % (p.get("name"), p.get("width", 1280), p.get("height", 720)), "",
                        _row("Visual", "Title", "Fields", "Position (x,y,w,h)"), _row("---", "---", "---", "---")]
                for v_ in p.get("visuals") or []:
                    pos = v_.get("position") or {}
                    out.append(_row(v_.get("type"), v_.get("title"),
                                    "; ".join("%s: %s" % (r, ", ".join(fields.get(x, x) for x in xs)) for r, xs in (v_.get("roles") or {}).items()),
                                    "%s,%s,%s,%s" % (pos.get("x"), pos.get("y"), pos.get("width"), pos.get("height"))))
        else:
            out += ["- **Output:** Power BI project `%s_v%s_pbip.zip` with the semantic model and a 'Model check' page. "
                    "You open it in Power BI Desktop, refresh it (signing in to the database), check it and publish it." % (rep.get("file_name"), v), ""]
            out += ["**Relationships**", "", _row("From (many)", "To (one)", "Active", "Filter direction", "Key checked unique"),
                    _row("---", "---", "---", "---", "---")]
            for r in spec.get("relationships") or []:
                out.append(_row("%s[%s]" % (r.get("from_table"), r.get("from_column")), "%s[%s]" % (r.get("to_table"), r.get("to_column")),
                                "yes" if r.get("active", True) else "no", "both" if r.get("cross_filter") == "both" else "single",
                                "yes" if r.get("verified_unique") else "NO"))
            out += ["", "**Measures**", "", _row("Table", "Measure", "Definition (DAX)", "Format", "Description"), _row("---", "---", "---", "---", "---")]
            for m in spec.get("measures") or []:
                out.append(_row(m.get("table"), m.get("name"), " ".join((m.get("expression") or "").split()), m.get("format"), m.get("description")))
            dt = spec.get("date_table") or {}
            if dt.get("create"):
                out += ["", "**Date table** '%s' from %s to %s (Year, Quarter, Month, Month Year), linked to %s." % (
                    dt.get("name", "Date"), dt.get("start"), dt.get("end"),
                    ", ".join("%s[%s]%s" % (r["table"], r["column"], "" if r.get("active", True) else " (inactive)") for r in dt.get("relationships") or []) or "nothing")]
            cp = spec.get("check_page") or {}
            out += ["", "**Model check page:** %s by %s." % (", ".join(cp.get("measures") or []) or "all measures",
                                                            ", ".join("%s[%s]" % (r["table"], r["column"]) for r in cp.get("rows") or []) or "total")]
        val = spec.get("validation") or {}
        if val.get("sample_file"):
            out += ["", "**How I'll check the numbers:** compare with `%s`%s using %s; match rows on %s; compare %s; tolerance %s." % (
                val.get("sample_file"), " (sheet %s)" % val["sample_sheet"] if val.get("sample_sheet") else "",
                ", ".join("%s=%s" % kv for kv in (val.get("sample_parameters") or {}).items()) or "the same filters as the sample",
                ", ".join(val.get("key_columns") or []) or "row order", ", ".join(val.get("measure_columns") or []) or "all numeric columns",
                val.get("tolerance_abs", 0.01))]
        ask = "Reply **CONFIRM SPEC** to approve this %s, or tell me what to change." % ("model design" if rt == "semantic_model" else "specification and layout")
    qs = spec.get("open_questions") or []
    if qs:
        out += ["", "**Open questions**", ""] + ["%d. %s" % (i, q) for i, q in enumerate(qs, 1)]
    out += ["", ask]
    return "\n".join(out)


# ----------------------------------------------------------------------------
# Diff
# ----------------------------------------------------------------------------

def flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in VOLATILE_KEYS or k == "confirmations":
                continue
            out.update(flatten(v, "%s.%s" % (prefix, k) if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, "%s[%d]" % (prefix, i)))
    else:
        out[prefix] = obj
    return out


def diff(a, b):
    fa, fb = flatten(a), flatten(b)
    changes = []
    for k in sorted(set(fa) | set(fb)):
        if fa.get(k, "<missing>") != fb.get(k, "<missing>"):
            changes.append((k, fa.get(k, "<missing>"), fb.get(k, "<missing>")))
    rt = b.get("report_type") or a.get("report_type")
    gates = set()
    for k, _, _ in changes:
        top = re.split(r"[.\[]", k)[0]
        for g, secs in GATE_SECTIONS.get(rt, {}).items():
            if top in secs:
                gates.add(g)
    return changes, sorted(gates)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new")
    p.add_argument("--type", required=True, choices=["paginated", "powerbi", "semantic_model"])
    p.add_argument("--name", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("validate")
    p.add_argument("spec")
    p.add_argument("--gate", choices=["data", "spec"])
    for name in ("check", "bump"):
        sub.add_parser(name).add_argument("spec")
    p = sub.add_parser("summary")
    p.add_argument("spec")
    p.add_argument("--gate", required=True, choices=["data", "spec"])
    p = sub.add_parser("confirm")
    p.add_argument("spec")
    p.add_argument("--gate", required=True, choices=["data", "spec"])
    p.add_argument("--reply", required=True, help="the user's exact approval message")
    p.add_argument("--by", default=None)
    p.add_argument("--reply-is-approval", action="store_true",
                   help="use only after checking that a reply containing words like 'no' or 'change' is still an approval")
    p = sub.add_parser("diff")
    p.add_argument("old")
    p.add_argument("new")
    a = ap.parse_args()

    if a.cmd == "new":
        tpl = rk.load_json(os.path.join(TEMPLATES, "spec-template-%s.json" % a.type.replace("_", "-")))
        tpl["report"]["name"] = a.name
        tpl["report"]["file_name"] = re.sub(r"[^A-Za-z0-9 _.\-()]", "", a.name).strip().replace(" ", "_")
        rk.dump_json(tpl, a.out)
        print("created", a.out)
        return
    if a.cmd == "diff":
        changes, gates = diff(rk.load_json(a.old), rk.load_json(a.new))
        for k, old, new in changes:
            print("%s: %r -> %r" % (k, old, new))
        print("gates to re-confirm: %s" % (", ".join(gates) or "none"))
        return
    spec = rk.load_json(a.spec)
    if a.cmd == "validate":
        errors, warnings = validate(spec)
        errors = errors_for_gate(spec, errors, a.gate)
        for w in warnings:
            print("WARNING: " + w)
        for sec, e in errors:
            print("ERROR [%s]: %s" % (sec, e))
        print("valid" if not errors else "%d error(s)" % len(errors))
        sys.exit(1 if errors else 0)
    if a.cmd == "summary":
        print(summary(spec, a.gate))
        return
    if a.cmd == "check":
        ok = True
        for gate in ("data", "spec"):
            status, changed = gate_status(spec, gate)
            print("%s gate: %s%s" % (gate, status, (" - changed sections: " + ", ".join(changed)) if changed else ""))
            ok = ok and status == "confirmed"
        sys.exit(0 if ok else 3)
    if a.cmd == "bump":
        spec["report"]["version"] = int(spec["report"].get("version", 1)) + 1
        rk.dump_json(spec, a.spec)
        print("spec is now version %d; gates affected by your edits must be confirmed again" % spec["report"]["version"])
        return
    if a.cmd == "confirm":
        reply = (a.reply or "").strip()
        if not reply:
            rk.fail("--reply must contain the user's exact message")
        if CHANGE_WORDS.search(reply) and not a.reply_is_approval:
            rk.fail("The reply may contain a change request: %r. Apply the changes and ask again, or re-run with "
                    "--reply-is-approval if it is clearly an approval." % reply, code=4)
        errors, _ = validate(spec)
        relevant = errors_for_gate(spec, errors, a.gate)
        if relevant:
            rk.fail("Fix these before asking for confirmation: " + "; ".join(e for _, e in relevant))
        if a.gate == "spec" and gate_status(spec, "data")[0] != "confirmed":
            rk.fail("Confirm the data gate first (or again, if the data sections changed).")
        spec.setdefault("confirmations", {})[a.gate] = {
            "hash": gate_hash(spec, a.gate), "section_hashes": section_hashes(spec, a.gate),
            "sections": GATE_SECTIONS[spec["report_type"]][a.gate], "reply": reply, "confirmed_by": a.by,
            "spec_version": spec["report"].get("version", 1),
            "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        rk.dump_json(spec, a.spec)
        print("%s gate confirmed for spec version %s" % (a.gate, spec["report"].get("version", 1)))


if __name__ == "__main__":
    main()
