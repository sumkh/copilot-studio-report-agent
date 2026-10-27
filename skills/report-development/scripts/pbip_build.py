#!/usr/bin/env python3
"""Build a thin Power BI report as a zipped Power BI Project (PBIP, PBIR format) from a confirmed spec.

Usage:
  python pbip_build.py spec.json --exemplar SAMPLE(.pbix|.zip|folder) --out Report_Name_v1_pbip.zip

The report is cloned from an exemplar in PBIR format (the user's sample report, or the
starter template named in config/org-config.json): its theme, page settings and visual
formatting are kept; pages and visuals are rebuilt from the spec and bound to the confirmed
semantic-model fields through a live connection (definition.pbir byConnection). Nothing is
published: the user opens the .pbip in Power BI Desktop, reviews it and publishes it.
Refuses to run unless both confirmation gates are current.
"""
import argparse
import copy
import io
import json
import os
import sys
import uuid
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402
import spec_tool  # noqa: E402
from pbi_inspect import Container, pbir_roots  # noqa: E402

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/"
DEFAULT_VISUAL_SCHEMA = SCHEMA + "item/report/definition/visualContainer/2.0.0/schema.json"
DEFINITION_PBIR_SCHEMA = SCHEMA + "item/report/definitionProperties/2.0.0/schema.json"
PBIP_SCHEMA = SCHEMA + "pbip/pbipProperties/1.0.0/schema.json"
BUILTIN_ROLES = {   # used only when the exemplar has no visual of the requested type
    "card": ["Values"], "multiRowCard": ["Values"], "tableEx": ["Values"], "pivotTable": ["Rows", "Columns", "Values"],
    "clusteredColumnChart": ["Category", "Y", "Series"], "clusteredBarChart": ["Category", "Y", "Series"],
    "lineChart": ["Category", "Y", "Series"], "pieChart": ["Category", "Y"], "donutChart": ["Category", "Y"],
    "slicer": ["Values"],
}


def new_id():
    return uuid.uuid4().hex[:20]


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def projection(f):
    kind = "Measure" if f["kind"] == "measure" else "Column"
    return {"field": {kind: {"Expression": {"SourceRef": {"Entity": f["table"]}}, "Property": f["name"]}},
            "queryRef": "%s.%s" % (f["table"], f["name"]), "nativeQueryRef": f["name"]}


def quote_cs(v):
    return '"%s"' % v if any(ch in v for ch in ' ;="') else v


def connection_string(src):
    if src.get("pbir_connection_string"):
        return src["pbir_connection_string"]
    cs = "Data Source=%s;initial catalog=%s;access mode=readonly;integrated security=ClaimsToken" % (
        quote_cs("powerbi://api.powerbi.com/v1.0/myorg/" + src["workspace"]), quote_cs(src["model_name"]))
    if src.get("model_id"):
        cs += ";semanticmodelid=" + src["model_id"]
    return cs


def clean_objects(objects):
    """Keep formatting that isn't tied to the exemplar's data (entries without selectors)."""
    out = {}
    for name, entries in (objects or {}).items():
        kept = [e for e in entries if isinstance(e, dict) and "selector" not in e]
        if kept:
            out[name] = kept
    return out


def load_exemplar(path):
    c = Container(path)
    roots = pbir_roots(c.names)
    if not roots:
        rk.fail("The exemplar has no PBIR report definition. Ask the user to save the sample with the PBIR format "
                "(Power BI Desktop: File > Save as > Power BI Project, then zip the folder) or use the starter template.")
    root = roots[0]
    files = {}
    for n in c.names:
        if n.startswith(root) and not n.endswith("/"):
            files[n[len(root):]] = c.read(n)
    return files


def make_report_files(ex, folder, pages, fields, dataset_reference, opts, warnings):
    """Clone the exemplar into <folder>/ with new pages and visuals.

    ex: {relative path: bytes} from load_exemplar(); pages: spec-style pages; fields: {id: field};
    dataset_reference: the definition.pbir datasetReference ({"byConnection": ...} or {"byPath": ...}).
    """
    def ex_json(rel):
        return json.loads(rk.decode_text(ex[rel])) if rel in ex else None
    report = ex_json("definition/report.json") or rk.fail("exemplar has no definition/report.json")
    version = ex_json("definition/version.json") or {"$schema": SCHEMA + "item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}
    pages_meta = ex_json("definition/pages/pages.json") or {}
    page_files = sorted(k for k in ex if k.startswith("definition/pages/") and k.endswith("/page.json"))
    if not page_files:
        rk.fail("exemplar has no pages")
    first_page = pages_meta.get("pageOrder", [None])[0]
    tpl_page_path = next((p for p in page_files if p.split("/")[2] == first_page), page_files[0])
    tpl_page = ex_json(tpl_page_path)
    visual_templates, any_visual_schema = {}, None
    for k in sorted(ex):
        if k.endswith("/visual.json"):
            v = ex_json(k)
            vt = (v.get("visual") or {}).get("visualType")
            any_visual_schema = any_visual_schema or v.get("$schema")
            if vt and vt not in visual_templates:
                visual_templates[vt] = v

    rroot = folder.rstrip("/") + "/"
    out = {}
    out[rroot + "definition.pbir"] = {"$schema": DEFINITION_PBIR_SCHEMA, "version": "4.0", "datasetReference": dataset_reference}
    out[rroot + "definition/version.json"] = version
    report = copy.deepcopy(report)
    if not opts.get("keep_report_filters"):
        report.pop("filterConfig", None)
    if not opts.get("keep_theme", True):
        report.get("themeCollection", {}).pop("customTheme", None)
    out[rroot + "definition/report.json"] = report
    for k, data in ex.items():
        if k.startswith("StaticResources/"):
            out[rroot + k] = data            # themes and images, copied byte for byte

    order = []
    for pi, p in enumerate(pages):
        pid = new_id()
        order.append(pid)
        page = copy.deepcopy(tpl_page)
        page.update({"name": pid, "displayName": p["name"], "width": p.get("width", tpl_page.get("width", 1280)),
                     "height": p.get("height", tpl_page.get("height", 720))})
        for k in ("filterConfig", "visualInteractions", "pageBinding", "type", "visibility", "autoPageGenerationConfig", "annotations", "howCreated"):
            page.pop(k, None)
        if not opts.get("keep_page_background", True) and page.get("objects"):
            page["objects"].pop("background", None)
        out[rroot + "definition/pages/%s/page.json" % pid] = page
        for vi, vs in enumerate(p.get("visuals") or []):
            vtype = vs["type"]
            tpl = visual_templates.get(vtype)
            if tpl is None:
                if vtype not in BUILTIN_ROLES:
                    rk.fail("No exemplar visual of type '%s' and no built-in template. Available: %s" % (vtype, ", ".join(sorted(visual_templates))))
                warnings.append("no '%s' visual in the exemplar; a plain built-in visual was used (default formatting)" % vtype)
                tpl = {"$schema": any_visual_schema or DEFAULT_VISUAL_SCHEMA, "name": "", "position": {},
                       "visual": {"visualType": vtype, "query": {"queryState": {}}, "drillFilterOtherVisuals": True}}
            v = copy.deepcopy(tpl)
            for k in ("filterConfig", "parentGroupName", "isHidden", "annotations", "howCreated", "visualGroup"):
                v.pop(k, None)
            vid = new_id()
            pos = vs["position"]
            v["name"] = vid
            v["position"] = {"x": pos["x"], "y": pos["y"], "z": vi * 1000, "height": pos["height"], "width": pos["width"], "tabOrder": vi * 1000}
            vis = v.setdefault("visual", {})
            vis["visualType"] = vtype
            for k in ("expansionStates", "syncGroup", "autoSelectVisualType"):
                vis.pop(k, None)
            query = {"queryState": {role: {"projections": [projection(fields[fid]) for fid in ids]}
                                    for role, ids in (vs.get("roles") or {}).items() if ids}}
            if vs.get("sort"):
                f = fields[vs["sort"]["field"]]
                query["sortDefinition"] = {"sort": [{"field": projection(f)["field"], "direction": vs["sort"].get("direction", "Descending")}],
                                           "isDefaultSort": True}
            vis["query"] = query
            objs = clean_objects(vis.get("objects"))
            if objs:
                vis["objects"] = objs
            else:
                vis.pop("objects", None)
            key = "visualContainerObjects" if "visualContainerObjects" in vis or "vcObjects" not in vis else "vcObjects"
            vco = vis.setdefault(key, {})
            titles = vco.get("title") or [{"properties": {}}]
            props = titles[0].setdefault("properties", {})
            if vs.get("title"):
                props["show"] = lit("true")
                props["text"] = lit("'%s'" % vs["title"].replace("'", "''"))
            else:
                props.pop("text", None)
            vco["title"] = [titles[0]]
            out[rroot + "definition/pages/%s/visuals/%s/visual.json" % (pid, vid)] = v
    out[rroot + "definition/pages/pages.json"] = {"$schema": pages_meta.get("$schema", SCHEMA + "item/report/definition/pagesMetadata/1.0.0/schema.json"),
                                                  "pageOrder": order, "activePageName": order[0]}
    return out


def pbip_file(name, report_folder):
    return {"$schema": PBIP_SCHEMA, "version": "1.0", "artifacts": [{"report": {"path": report_folder}}],
            "settings": {"enableAutoRecovery": True}}


def build(spec, exemplar_path):
    spec_tool.require_confirmed(spec)
    errors, warnings = spec_tool.validate(spec)
    if errors:
        rk.fail("The spec has errors: " + "; ".join(e for _, e in errors))
    if spec["report_type"] != "powerbi":
        rk.fail("pbip_build.py builds Power BI reports; use rdl_build.py for paginated reports and model_build.py for semantic models")
    ex = load_exemplar(exemplar_path)
    name = spec["report"]["file_name"]
    fields = {f["id"]: f for f in spec["fields"]}
    ref = {"byConnection": {"connectionString": connection_string(spec["data_sources"][0])}}
    out = make_report_files(ex, name + ".Report", spec["pages"], fields, ref, spec.get("exemplar") or {}, warnings)
    out[name + ".pbip"] = pbip_file(name, name + ".Report")
    out["HOW_TO_OPEN.txt"] = (
        "1. Unzip this file to a local folder (keep the folder structure).\n"
        "2. Open %s.pbip in Power BI Desktop (current version; PBIR format).\n"
        "3. Sign in when prompted: the report connects live to the semantic model '%s'.\n"
        "4. Review every page; export data from visuals if you want to compare numbers.\n"
        "5. When you are happy, use Publish in Power BI Desktop to your chosen workspace.\n"
        "Generated by the report-development skill from spec '%s' version %s.\n" % (
            name, spec["data_sources"][0].get("model_name") or spec["data_sources"][0].get("model_id"),
            spec["report"]["name"], spec["report"].get("version", 1)))
    return out, warnings


def write_zip(files, path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in sorted(files):
            data = files[n]
            if isinstance(data, (dict, list)):
                data = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            elif isinstance(data, str):
                data = data.encode("utf-8")
            z.writestr(n, data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--exemplar", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    files, warnings = build(rk.load_json(a.spec), a.exemplar)
    write_zip(files, a.out)
    for w in warnings:
        print("WARNING: " + w)
    print("wrote %s (%d files)" % (a.out, len(files)))


if __name__ == "__main__":
    main()
