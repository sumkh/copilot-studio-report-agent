#!/usr/bin/env python3
"""Check a zipped Power BI Project (PBIR report) before handing it to the user.

Usage:
  python pbip_validate.py REPORT_pbip.zip [--model-schema model.json] [--json]

Checks:
  - a .pbip file points to an existing <name>.Report folder
  - definition.pbir has a datasetReference (byConnection connection string or an existing byPath)
  - report.json, version.json, pages.json parse; theme resources exist
  - pages.json pageOrder matches the page folders; page/visual names match their folders and are unique
  - visuals sit inside the page; each has a visualType and well-formed field projections
  - every Entity/Property used exists in the semantic model, when --model-schema is given:
      {"tables": {"Sales": {"columns": ["Region"], "measures": ["Total Sales"]}}}
Exit code 1 if any error is found.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402
from pbi_inspect import Container, field_ref  # noqa: E402


def walk_fields(node, found):
    if isinstance(node, dict):
        for kind in ("Column", "Measure"):
            if kind in node and isinstance(node[kind], dict) and "Property" in node[kind]:
                ent = ((node[kind].get("Expression") or {}).get("SourceRef") or {}).get("Entity")
                if ent:
                    found.add((ent, node[kind]["Property"], kind.lower()))
        for v in node.values():
            walk_fields(v, found)
    elif isinstance(node, list):
        for v in node:
            walk_fields(v, found)


def validate(path, model_schema=None):
    errors, warnings, stats = [], [], {}
    c = Container(path)
    names = set(c.names)
    pbips = [n for n in names if n.endswith(".pbip")]
    if not pbips:
        errors.append("no .pbip file found")
        return errors, warnings, stats

    def load(n):
        try:
            return json.loads(rk.decode_text(c.read(n)))
        except Exception as e:
            errors.append("%s is not valid JSON: %s" % (n, e))
            return None
    pbip = load(pbips[0]) or {}
    base = os.path.dirname(pbips[0])
    base = base + "/" if base else ""
    reports = [a.get("report", {}).get("path") for a in pbip.get("artifacts", [])]
    if not reports or not reports[0]:
        errors.append("the .pbip file lists no report artifact")
        return errors, warnings, stats
    root = base + reports[0].rstrip("/") + "/"
    if not any(n.startswith(root) for n in names):
        errors.append("the .pbip points to '%s' but that folder isn't in the package" % reports[0])
        return errors, warnings, stats
    dp = load(root + "definition.pbir") if root + "definition.pbir" in names else None
    if dp is None:
        errors.append("definition.pbir is missing")
    else:
        ref = dp.get("datasetReference") or {}
        if ref.get("byConnection"):
            cs = ref["byConnection"].get("connectionString") or ""
            if not cs:
                errors.append("definition.pbir byConnection has an empty connection string")
            if rk.mask_secrets(cs)[1]:
                errors.append("definition.pbir connection string contains a secret")
            stats["connection"] = cs
        elif ref.get("byPath"):
            target = os.path.normpath(os.path.join(root, ref["byPath"].get("path", ""))).replace(os.sep, "/")
            if not any(n.startswith(target + "/") for n in names):
                errors.append("definition.pbir byPath points to '%s', which isn't in the package" % ref["byPath"].get("path"))
        else:
            errors.append("definition.pbir has no datasetReference")
    for req in ("definition/report.json", "definition/version.json", "definition/pages/pages.json"):
        if root + req not in names:
            errors.append("%s is missing" % req)
    report = load(root + "definition/report.json") if root + "definition/report.json" in names else {}
    custom = ((report or {}).get("themeCollection") or {}).get("customTheme")
    if custom and not any(n.startswith(root + "StaticResources/RegisteredResources/") and n.endswith(custom["name"]) for n in names):
        warnings.append("custom theme '%s' is referenced but its file isn't under StaticResources/RegisteredResources" % custom["name"])
    pages_meta = load(root + "definition/pages/pages.json") if root + "definition/pages/pages.json" in names else {}
    page_dirs = sorted({n[len(root + "definition/pages/"):].split("/")[0] for n in names
                        if n.startswith(root + "definition/pages/") and n.endswith("/page.json")})
    order = (pages_meta or {}).get("pageOrder") or []
    if sorted(order) != page_dirs:
        errors.append("pages.json pageOrder %s doesn't match page folders %s" % (order, page_dirs))
    if (pages_meta or {}).get("activePageName") and pages_meta["activePageName"] not in page_dirs:
        errors.append("activePageName '%s' is not a page" % pages_meta["activePageName"])
    used = set()
    stats["pages"] = []
    for pdir in page_dirs:
        page = load(root + "definition/pages/%s/page.json" % pdir) or {}
        if page.get("name") != pdir:
            errors.append("page folder '%s' contains page name '%s'" % (pdir, page.get("name")))
        if not page.get("displayName"):
            errors.append("page '%s' has no displayName" % pdir)
        pw, ph = page.get("width", 1280), page.get("height", 720)
        vprefix = root + "definition/pages/%s/visuals/" % pdir
        vdirs = sorted({n[len(vprefix):].split("/")[0] for n in names if n.startswith(vprefix) and n.endswith("/visual.json")})
        for vdir in vdirs:
            v = load(vprefix + vdir + "/visual.json") or {}
            if v.get("name") != vdir:
                errors.append("visual folder '%s' contains name '%s'" % (vdir, v.get("name")))
            pos = v.get("position") or {}
            for k in ("x", "y", "width", "height"):
                if not isinstance(pos.get(k), (int, float)):
                    errors.append("visual '%s' position.%s is missing" % (vdir, k))
            if all(isinstance(pos.get(k), (int, float)) for k in ("x", "y", "width", "height")):
                if pos["x"] < 0 or pos["y"] < 0 or pos["x"] + pos["width"] > pw + 1 or pos["y"] + pos["height"] > ph + 1:
                    warnings.append("visual '%s' on page '%s' extends past the page (%sx%s)" % (vdir, page.get("displayName"), pw, ph))
            vis = v.get("visual")
            if not vis and not v.get("visualGroup"):
                errors.append("visual '%s' has neither a visual nor a visualGroup" % vdir)
                continue
            if vis:
                if not vis.get("visualType"):
                    errors.append("visual '%s' has no visualType" % vdir)
                qrefs = []
                for role, state in ((vis.get("query") or {}).get("queryState") or {}).items():
                    for pj in state.get("projections", []):
                        if "field" not in pj or "queryRef" not in pj:
                            errors.append("visual '%s' role %s has a projection without field/queryRef" % (vdir, role))
                            continue
                        ref = field_ref(pj["field"])
                        if not ref or not ref.get("table") or not ref.get("name"):
                            errors.append("visual '%s' role %s has an unreadable field reference" % (vdir, role))
                        qrefs.append(pj["queryRef"])
                dups = {q for q in qrefs if qrefs.count(q) > 1}
                if dups:
                    warnings.append("visual '%s' uses the same field twice: %s" % (vdir, ", ".join(sorted(dups))))
            walk_fields(v, used)
        stats["pages"].append({"name": page.get("displayName"), "visuals": len(vdirs)})
    walk_fields(report, used)
    stats["fields_used"] = sorted("%s[%s]" % (e, p) for e, p, _ in used)
    if model_schema:
        tables = (model_schema.get("tables") or {})
        for ent, prop, kind in sorted(used):
            t = tables.get(ent)
            if t is None:
                errors.append("table '%s' is not in the semantic model" % ent)
                continue
            pool = set(t.get("columns", [])) | set(t.get("measures", []))
            if prop not in pool:
                errors.append("'%s'[%s] (%s) is not in the semantic model" % (ent, prop, kind))
            elif kind == "measure" and prop not in set(t.get("measures", [])):
                warnings.append("'%s'[%s] is used as a measure but the model lists it as a column" % (ent, prop))
    return errors, warnings, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--model-schema")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    model = rk.load_json(a.model_schema) if a.model_schema else None
    errors, warnings, stats = validate(a.package, model)
    if a.json:
        print(json.dumps({"errors": errors, "warnings": warnings, "stats": stats}, indent=2))
    else:
        for e in errors:
            print("ERROR: " + e)
        for w in warnings:
            print("WARNING: " + w)
        print("%s: %d error(s), %d warning(s); pages %s" % (os.path.basename(a.package), len(errors), len(warnings), stats.get("pages")))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
