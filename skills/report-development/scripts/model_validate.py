#!/usr/bin/env python3
"""Check a Power BI semantic model package (TMDL in a zipped Power BI Project) before handover.

Usage:
  python model_validate.py MODEL_pbip.zip [--schema-out analysis/model.json] [--json]

Checks:
  - definition.pbism present with version 4.0+ and a TMDL definition folder (database, model, tables)
  - every table has a partition; data columns have dataType and sourceColumn; names unique
    (case-insensitive) within a table; measure names unique across the model and not equal to a
    column name in the same table; sortByColumn targets exist
  - relationships point to existing columns of the same data type; no duplicate or ambiguous active
    relationships between the same tables; warns on both-direction filtering
  - a table marked as a date table (dataCategory Time) has exactly one dateTime key column
  - DAX in measures and calculated columns: balanced syntax, and every 'Table'[Column], [Measure]
    reference exists
  - Power Query: referenced #"parameters" exist; no credentials in M code
  - the bundled report (if any) binds to this model and only uses fields that exist in it
Exit code 1 if any error is found. --schema-out writes {"tables": {...}} for pbip_validate.py.
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402
import tmdl  # noqa: E402
from pbi_inspect import Container  # noqa: E402
import pbip_validate  # noqa: E402

LOWER = str.lower


def validate(path):
    errors, warnings, stats = [], [], {}
    c = Container(path)
    pbism = [n for n in c.names if n.endswith(".SemanticModel/definition.pbism") or n == "definition.pbism"]
    if not pbism:
        return ["no <name>.SemanticModel/definition.pbism found"], warnings, stats, None
    root = pbism[0][: -len("definition.pbism")]
    try:
        meta = json.loads(rk.decode_text(c.read(pbism[0])))
        ver = float(str(meta.get("version", "0")).split(".")[0] + "." + (str(meta.get("version", "0")).split(".") + ["0"])[1])
        if ver < 4.0:
            errors.append("definition.pbism version %s doesn't support TMDL (needs 4.0 or above)" % meta.get("version"))
    except Exception as e:
        errors.append("definition.pbism unreadable: %s" % e)
    files = {n[len(root):]: rk.decode_text(c.read(n)) for n in c.names
             if n.startswith(root + "definition/") and n.endswith(".tmdl")}
    if not files:
        return errors + ["no TMDL files under %sdefinition/" % root], warnings, stats, None
    for req in ("definition/database.tmdl", "definition/model.tmdl"):
        if req not in files:
            errors.append("%s is missing" % req)
    m = tmdl.parse(files)
    level = m["database"]["properties"].get("compatibilityLevel")
    if level and int(level) < 1500:
        warnings.append("compatibility level %s is old; 1567 or later is recommended" % level)
    if m["model"]["properties"].get("defaultPowerBIDataSourceVersion", "").lower() != "powerbi_v3":
        warnings.append("model.tmdl doesn't set defaultPowerBIDataSourceVersion: powerBI_V3")
    tables = m["tables"]
    if not tables:
        errors.append("the model has no tables")
    t_lower = {LOWER(t): t for t in tables}
    all_measures = {}
    for tname, t in tables.items():
        if not t["partitions"]:
            errors.append("table '%s' has no partition (no data source)" % tname)
        for p in t["partitions"]:
            if (p.get("type") or "").lower() == "m" and not (p.get("source") or "").strip():
                errors.append("table '%s' partition '%s' has no Power Query source" % (tname, p["name"]))
        cols = collections.Counter(LOWER(c) for c in t["columns"])
        for cname, n in cols.items():
            if n > 1:
                errors.append("table '%s' has duplicate column '%s'" % (tname, cname))
        for cname, col in t["columns"].items():
            props = col["properties"]
            if col.get("expression") is None and not props.get("sourceColumn") and not props.get("isNameInferred"):
                errors.append("column '%s'[%s] has neither a sourceColumn nor an expression" % (tname, cname))
            if not props.get("dataType") and col.get("expression") is None:
                errors.append("column '%s'[%s] has no dataType" % (tname, cname))
            sb = props.get("sortByColumn")
            if sb:
                target = tmdl.split_name(sb)[0]
                if LOWER(target) not in cols:
                    errors.append("column '%s'[%s] sorts by missing column '%s'" % (tname, cname, target))
                elif LOWER(target) == LOWER(cname):
                    errors.append("column '%s'[%s] can't sort by itself" % (tname, cname))
        for mname in t["measures"]:
            if LOWER(mname) in all_measures:
                errors.append("measure '%s' is defined twice (tables '%s' and '%s')" % (mname, all_measures[LOWER(mname)], tname))
            all_measures[LOWER(mname)] = tname
            if LOWER(mname) in cols:
                errors.append("measure '%s' has the same name as a column in table '%s'" % (mname, tname))
        if t["properties"].get("dataCategory", "").lower() == "time":
            keys = [cn for cn, col in t["columns"].items() if col["properties"].get("isKey")]
            if len(keys) != 1:
                errors.append("date table '%s' needs exactly one key column (found %d)" % (tname, len(keys)))
            elif t["columns"][keys[0]]["properties"].get("dataType", "").lower() != "datetime":
                errors.append("date table '%s' key column '%s' must be dateTime" % (tname, keys[0]))

    def col_type(tname, cname):
        t = tables.get(t_lower.get(LOWER(tname)))
        if not t:
            return None
        for cn, col in t["columns"].items():
            if LOWER(cn) == LOWER(cname):
                return (col["properties"].get("dataType") or "").lower() or None
        return None
    pairs = collections.Counter()
    seen = set()
    for r in m["relationships"]:
        p = r["properties"]
        ft, fc = tmdl.split_qualified(p.get("fromColumn", ""))
        tt, tc = tmdl.split_qualified(p.get("toColumn", ""))
        if not ft or not tt:
            errors.append("relationship %s has an unreadable fromColumn/toColumn" % r["name"])
            continue
        a, b = col_type(ft, fc), col_type(tt, tc)
        if a is None:
            errors.append("relationship %s: column '%s'[%s] doesn't exist" % (r["name"], ft, fc))
        if b is None:
            errors.append("relationship %s: column '%s'[%s] doesn't exist" % (r["name"], tt, tc))
        if a and b and a != b:
            errors.append("relationship '%s'[%s] -> '%s'[%s] joins different data types (%s vs %s)" % (ft, fc, tt, tc, a, b))
        if LOWER(ft) == LOWER(tt):
            errors.append("relationship %s joins table '%s' to itself" % (r["name"], ft))
        key = (LOWER(ft), LOWER(fc), LOWER(tt), LOWER(tc))
        if key in seen:
            errors.append("duplicate relationship '%s'[%s] -> '%s'[%s]" % (ft, fc, tt, tc))
        seen.add(key)
        if p.get("isActive", "true").lower() != "false":
            pairs[frozenset((LOWER(ft), LOWER(tt)))] += 1
        if p.get("crossFilteringBehavior", "").lower() == "bothdirections":
            warnings.append("relationship '%s' -> '%s' filters in both directions; check for ambiguity" % (ft, tt))
    for pair, n in pairs.items():
        if n > 1:
            errors.append("more than one active relationship between %s; make all but one inactive" % " and ".join(sorted(pair)))

    def check_dax(expr, where, own_table=None):
        prob = tmdl.dax_syntax_problem(expr)
        if prob:
            errors.append("%s: DAX has %s" % (where, prob))
        qualified, bare, quoted_tables = tmdl.dax_references(expr)
        for t, cname in qualified:
            real = t_lower.get(LOWER(t))
            if not real:
                errors.append("%s: table '%s' doesn't exist" % (where, t))
                continue
            names = {LOWER(x) for x in tables[real]["columns"]} | {LOWER(x) for x in tables[real]["measures"]}
            if LOWER(cname) not in names:
                errors.append("%s: '%s'[%s] doesn't exist" % (where, t, cname))
        for b in bare:
            ok = LOWER(b) in all_measures or (own_table and LOWER(b) in {LOWER(x) for x in tables[own_table]["columns"]})
            if not ok:
                errors.append("%s: [%s] isn't a measure%s" % (where, b, " or a column of this table" if own_table else ""))
        for t in quoted_tables:
            if not t_lower.get(LOWER(t)):
                errors.append("%s: table '%s' doesn't exist" % (where, t))
    for tname, t in tables.items():
        for mname, me in t["measures"].items():
            check_dax(me.get("expression") or "", "measure [%s]" % mname)
        for cname, col in t["columns"].items():
            if col.get("expression"):
                check_dax(col["expression"], "calculated column '%s'[%s]" % (tname, cname), tname)
    params = {LOWER(e) for e in m["expressions"]}
    for tname, t in tables.items():
        for p in t["partitions"]:
            src = p.get("source") or ""
            for ref in set(re.findall(r'#"((?:[^"]|"")+)"', src)):
                is_step = re.search(r'#"%s"\s*=(?!=)' % re.escape(ref), src)     # a step defined in this query
                if LOWER(ref.replace('""', '"')) not in params and not is_step:
                    errors.append("table '%s' Power Query uses #\"%s\", which is neither a parameter nor a step" % (tname, ref))
            if rk.mask_secrets(src)[1] or re.search(r"(?i)\b(user id|uid)\s*=", src):
                errors.append("table '%s' Power Query contains credentials" % tname)
    stats.update({"tables": len(tables), "columns": sum(len(t["columns"]) for t in tables.values()),
                  "measures": len(all_measures), "relationships": len(m["relationships"]),
                  "parameters": sorted(m["expressions"])})
    schema = {"tables": {tn: {"columns": list(t["columns"]), "measures": list(t["measures"])} for tn, t in tables.items()}}
    # Bundled report
    reports = [n for n in c.names if n.endswith(".Report/definition.pbir")]
    if reports:
        pbir = json.loads(rk.decode_text(c.read(reports[0])))
        ref = (pbir.get("datasetReference") or {}).get("byPath")
        if not ref:
            warnings.append("the bundled report isn't bound to the local model (byPath)")
        r_errors, r_warnings, r_stats = pbip_validate.validate(path, schema)
        errors += ["report: " + e for e in r_errors]
        warnings += ["report: " + w for w in r_warnings]
        stats["report_pages"] = r_stats.get("pages")
    return errors, warnings, stats, schema


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--schema-out")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    errors, warnings, stats, schema = validate(a.package)
    if a.schema_out and schema:
        rk.dump_json(schema, a.schema_out)
    if a.json:
        print(json.dumps({"errors": errors, "warnings": warnings, "stats": stats}, indent=2))
    else:
        for e in errors:
            print("ERROR: " + e)
        for w in warnings:
            print("WARNING: " + w)
        print("%s: %d error(s), %d warning(s); %s" % (os.path.basename(a.package), len(errors), len(warnings), json.dumps(stats)))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
