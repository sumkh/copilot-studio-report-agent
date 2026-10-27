#!/usr/bin/env python3
"""Inspect a Power BI sample: .pbix, .pbit, a zipped Power BI Project (PBIP) folder, or a PBIP folder.

Usage:
  python pbi_inspect.py SAMPLE.pbix|SAMPLE.pbit|SAMPLE_pbip.zip|FOLDER [--out inspect.json] [--summary]

Reports, where available:
  - report pages and visuals (type, position, title, fields per role) from PBIR or the legacy Layout
  - theme (custom/base theme colours and fonts) for style matching
  - the semantic model: live connection (dataset/semantic model id) or an embedded
    model (tables, columns, measures, Power Query sources) from DataModelSchema
    (.pbit), model.bim or TMDL (PBIP)
  - whether the file can serve as a PBIR exemplar for pbip_build.py
A .pbix with an import model keeps its model in a binary file that can't be read
here; ask for a .pbit (File > Export > Power BI template) or a PBIP instead.
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402
import tmdl  # noqa: E402


class Container:
    def __init__(self, path):
        self.path = path
        if os.path.isdir(path):
            self.kind = "folder"
            self.names = []
            for base, _, files in os.walk(path):
                for f in files:
                    self.names.append(os.path.relpath(os.path.join(base, f), path).replace(os.sep, "/"))
            self._zip = None
        else:
            self._zip = zipfile.ZipFile(path)
            self.names = self._zip.namelist()
            ext = os.path.splitext(path)[1].lower()
            self.kind = {".pbix": "pbix", ".pbit": "pbit"}.get(ext, "pbip-zip")

    def read(self, name):
        if self._zip is not None:
            return self._zip.read(name)
        with open(os.path.join(self.path, *name.split("/")), "rb") as f:
            return f.read()

    def json(self, name):
        return json.loads(rk.decode_text(self.read(name)))


# ----------------------------------------------------------------------------
# Field references
# ----------------------------------------------------------------------------

def field_ref(field, aliases=None):
    """Turn a semantic-query expression into {'kind','table','name'}."""
    aliases = aliases or {}

    def entity(expr):
        sr = (expr or {}).get("SourceRef", {})
        return sr.get("Entity") or aliases.get(sr.get("Source"))
    if not isinstance(field, dict):
        return None
    for kind in ("Column", "Measure"):
        if kind in field:
            return {"kind": kind.lower(), "table": entity(field[kind].get("Expression")), "name": field[kind].get("Property")}
    if "Aggregation" in field:
        inner = field_ref(field["Aggregation"].get("Expression"), aliases) or {}
        return {"kind": "aggregation", "function": field["Aggregation"].get("Function"),
                "table": inner.get("table"), "name": inner.get("name")}
    if "HierarchyLevel" in field:
        h = field["HierarchyLevel"].get("Expression", {}).get("Hierarchy", {})
        return {"kind": "hierarchy_level", "table": entity(h.get("Expression")), "name": "%s.%s" % (h.get("Hierarchy"), field["HierarchyLevel"].get("Level"))}
    return {"kind": "other", "table": None, "name": json.dumps(field)[:80]}


def literal(prop):
    try:
        v = prop["expr"]["Literal"]["Value"]
        return v[1:-1].replace("''", "'") if v.startswith("'") and v.endswith("'") else v
    except (KeyError, TypeError, AttributeError):
        return None


# ----------------------------------------------------------------------------
# PBIR
# ----------------------------------------------------------------------------

def pbir_roots(names):
    return sorted({n[: -len("definition/report.json")] for n in names if n.endswith("definition/report.json")})


def read_pbir(c, root, warnings):
    out = {"format": "PBIR", "root": root, "pages": []}
    names = [n for n in c.names if n.startswith(root)]
    try:
        report = c.json(root + "definition/report.json")
    except Exception as e:
        warnings.append("report.json unreadable: %s" % e)
        report = {}
    out["schemas"] = {"report": report.get("$schema")}
    tc = report.get("themeCollection", {})
    out["theme_names"] = {k: v.get("name") for k, v in tc.items() if isinstance(v, dict)}
    out["report_filters"] = len((report.get("filterConfig") or {}).get("filters", []))
    if root + "definition.pbir" in c.names:
        try:
            out["dataset_reference"] = c.json(root + "definition.pbir").get("datasetReference")
        except Exception:
            pass
    order = []
    if root + "definition/pages/pages.json" in c.names:
        meta = c.json(root + "definition/pages/pages.json")
        order = meta.get("pageOrder", [])
        out["active_page"] = meta.get("activePageName")
    page_files = sorted(n for n in names if re.search(r"definition/pages/[^/]+/page\.json$", n))
    by_name = {}
    for pf in page_files:
        p = c.json(pf)
        page = {"name": p.get("name"), "display_name": p.get("displayName"), "width": p.get("width"),
                "height": p.get("height"), "display_option": p.get("displayOption"), "visuals": [],
                "has_background": bool((p.get("objects") or {}).get("background")), "schema": p.get("$schema")}
        folder = pf[: -len("page.json")]
        for vf in sorted(n for n in names if n.startswith(folder + "visuals/") and n.endswith("/visual.json")):
            v = c.json(vf)
            vis = v.get("visual") or {}
            roles = {}
            for role, state in ((vis.get("query") or {}).get("queryState") or {}).items():
                roles[role] = [field_ref(p_.get("field")) for p_ in state.get("projections", [])]
            title = None
            vco = vis.get("visualContainerObjects") or vis.get("vcObjects") or {}
            for entry in vco.get("title", []):
                title = literal((entry.get("properties") or {}).get("text")) or title
            page["visuals"].append({"name": v.get("name"), "type": vis.get("visualType") or ("group" if v.get("visualGroup") else None),
                                    "position": v.get("position"), "title": title, "roles": roles,
                                    "schema": v.get("$schema"), "path": vf})
        by_name[page["name"]] = page
    for n in order:
        if n in by_name:
            out["pages"].append(by_name.pop(n))
    out["pages"].extend(by_name.values())
    return out


# ----------------------------------------------------------------------------
# Legacy report layout (Report/Layout, UTF-16 JSON)
# ----------------------------------------------------------------------------

def read_legacy(c, warnings):
    try:
        layout = json.loads(rk.decode_text(c.read("Report/Layout")))
    except Exception as e:
        warnings.append("Report/Layout unreadable: %s" % e)
        return None
    out = {"format": "legacy", "pages": []}
    try:
        cfg = json.loads(layout.get("config") or "{}")
        out["theme_names"] = {k: v.get("name") for k, v in (cfg.get("themeCollection") or {}).items()}
    except ValueError:
        out["theme_names"] = {}
    for s in layout.get("sections", []):
        page = {"name": s.get("name"), "display_name": s.get("displayName"), "width": s.get("width"),
                "height": s.get("height"), "visuals": []}
        for vc in s.get("visualContainers", []):
            try:
                cfg = json.loads(vc.get("config") or "{}")
            except ValueError:
                continue
            sv = cfg.get("singleVisual") or {}
            pq = sv.get("prototypeQuery") or {}
            aliases = {f.get("Name"): f.get("Entity") for f in pq.get("From", [])}
            by_name = {sel.get("Name"): field_ref(sel, aliases) for sel in pq.get("Select", [])}
            roles = {role: [by_name.get(p.get("queryRef")) or {"kind": "unknown", "name": p.get("queryRef")} for p in projs]
                     for role, projs in (sv.get("projections") or {}).items()}
            title = None
            for entry in (sv.get("vcObjects") or {}).get("title", []):
                title = literal((entry.get("properties") or {}).get("text")) or title
            page["visuals"].append({"name": cfg.get("name"), "type": sv.get("visualType"), "title": title,
                                    "position": {k: vc.get(k) for k in ("x", "y", "z", "width", "height")}, "roles": roles})
        out["pages"].append(page)
    return out


# ----------------------------------------------------------------------------
# Themes
# ----------------------------------------------------------------------------

def read_themes(c):
    themes = []
    for n in c.names:
        if "StaticResources/" in n and n.lower().endswith(".json"):
            try:
                t = c.json(n)
            except Exception:
                continue
            if not isinstance(t, dict) or not ({"dataColors", "name"} & set(t)):
                continue
            text_classes = {k: {kk: v.get(kk) for kk in ("fontFace", "fontSize", "color") if kk in v}
                            for k, v in (t.get("textClasses") or {}).items() if isinstance(v, dict)}
            themes.append({"file": n, "type": "custom" if "RegisteredResources" in n else "base", "name": t.get("name"),
                           "data_colors": (t.get("dataColors") or [])[:12], "background": t.get("background"),
                           "foreground": t.get("foreground"), "table_accent": t.get("tableAccent"),
                           "text_classes": text_classes})
    return themes


# ----------------------------------------------------------------------------
# Semantic model: DataModelSchema / model.bim (TMSL JSON) / TMDL
# ----------------------------------------------------------------------------

def _m_text(expr):
    return "\n".join(expr) if isinstance(expr, list) else (expr or "")


def model_from_tmsl(doc, source):
    m = doc.get("model", doc)
    tables = []
    for t in m.get("tables", []):
        parts = []
        for p in t.get("partitions", []):
            src = p.get("source", {})
            code = _m_text(src.get("expression"))
            parts.append({"mode": p.get("mode"), "type": src.get("type"), "sources": rk.m_sources(code),
                          "m_preview": code[:300]})
        tables.append({"name": t.get("name"), "hidden": bool(t.get("isHidden")),
                       "columns": [{"name": col.get("name"), "data_type": col.get("dataType"), "hidden": bool(col.get("isHidden")),
                                    "calculated": col.get("type") == "calculated" or "expression" in col}
                                   for col in t.get("columns", []) if not col.get("name", "").startswith("RowNumber")],
                       "measures": [{"name": me.get("name"), "expression": _m_text(me.get("expression"))[:300],
                                     "format": me.get("formatString")} for me in t.get("measures", [])],
                       "partitions": parts})
    exprs = [{"name": e.get("name"), "sources": rk.m_sources(_m_text(e.get("expression"))),
              "value": _m_text(e.get("expression"))[:200]} for e in m.get("expressions", [])]
    return {"source": source, "tables": tables, "relationships": len(m.get("relationships", [])), "expressions": exprs}


def model_from_tmdl(files):
    """Tables, columns, measures, partition sources and shared expressions from TMDL documents."""
    m = tmdl.parse(files)
    tables = []
    for tname, t in m["tables"].items():
        parts = [{"mode": p["properties"].get("mode"), "type": p.get("type"), "sources": rk.m_sources(p.get("source") or ""),
                  "m_preview": (p.get("source") or "")[:300]} for p in t["partitions"]]
        tables.append({"name": tname, "hidden": t["properties"].get("isHidden") == "true",
                       "columns": [{"name": cn, "data_type": c["properties"].get("dataType"),
                                    "hidden": c["properties"].get("isHidden") == "true", "calculated": c.get("expression") is not None}
                                   for cn, c in t["columns"].items()],
                       "measures": [{"name": mn, "expression": (me.get("expression") or "")[:300],
                                     "format": me["properties"].get("formatString")} for mn, me in t["measures"].items()],
                       "partitions": parts})
    exprs = [{"name": en, "sources": rk.m_sources(e.get("expression") or ""), "value": (e.get("expression") or "")[:200]}
             for en, e in m["expressions"].items()]
    return {"source": "TMDL", "tables": tables, "relationships": len(m["relationships"]), "expressions": exprs}


def read_model(c, warnings):
    names = c.names
    if "DataModelSchema" in names:
        return model_from_tmsl(json.loads(rk.decode_text(c.read("DataModelSchema"))), "DataModelSchema (.pbit)")
    bim = [n for n in names if n.endswith(".SemanticModel/model.bim") or n == "model.bim"]
    if bim:
        return model_from_tmsl(c.json(bim[0]), "model.bim")
    tmdl = [n for n in names if n.endswith(".tmdl")]
    if tmdl:
        return model_from_tmdl({n: rk.decode_text(c.read(n)) for n in tmdl})
    if "DataModel" in names:
        warnings.append("This .pbix contains an import model in binary form, which can't be read here. "
                        "Ask for a Power BI template (.pbit) or a Power BI Project (PBIP) to see tables and data sources.")
    return None


def read_live_connection(c, report):
    if "Connections" in c.names:
        try:
            doc = json.loads(rk.decode_text(c.read("Connections")))
            conns = doc.get("Connections") or []
            info = {"source": "Connections"}
            if conns:
                cs = conns[0].get("ConnectionString", "")
                info.update(rk.classify_connection("PBIDATASET" if "pbiazure" in cs.lower() else None, cs))
                info["connection_type"] = conns[0].get("ConnectionType")
                info["model_database"] = conns[0].get("PbiModelDatabaseName")
            arts = doc.get("RemoteArtifacts") or []
            if arts:
                info["dataset_id"] = arts[0].get("DatasetId")
                info["report_id"] = arts[0].get("ReportId")
            return info
        except Exception:
            return None
    ref = (report or {}).get("dataset_reference") or {}
    if ref.get("byConnection"):
        cs = ref["byConnection"].get("connectionString", "")
        info = {"source": "definition.pbir"}
        info.update(rk.classify_connection(None, cs))
        props = rk.parse_conn_string(cs)
        info["workspace"] = (props.get("data source", "").rstrip("/").split("/")[-1]) or None
        info["model_name"] = props.get("initial catalog")
        m = re.search(r"semanticmodelid=([0-9a-fA-F-]{36})", cs, re.I)
        info["model_id"] = m.group(1) if m else info.get("model_id")
        info["connection_string"] = cs
        return info
    if ref.get("byPath"):
        return {"source": "definition.pbir", "kind": "local_model", "path": ref["byPath"].get("path")}
    return None


def read_datamashup(c, warnings):
    if "DataMashup" not in c.names:
        return []
    try:
        raw = c.read("DataMashup")
        n = int.from_bytes(raw[4:8], "little")
        with zipfile.ZipFile(io.BytesIO(raw[8:8 + n])) as pz:
            section = rk.decode_text(pz.read("Formulas/Section1.m"))
        return [{"query": q, "sources": rk.m_sources(code)} for q, code in rk.m_shared_queries(section).items()]
    except Exception as e:
        warnings.append("DataMashup present but unreadable: %s" % e)
        return []


def inspect(path):
    warnings = []
    c = Container(path)
    roots = pbir_roots(c.names)
    report = read_pbir(c, roots[0], warnings) if roots else (read_legacy(c, warnings) if "Report/Layout" in c.names else None)
    if len(roots) > 1:
        warnings.append("Several reports found; inspected %s" % roots[0])
    model = read_model(c, warnings)
    live = read_live_connection(c, report)
    fields = {}
    for p in (report or {}).get("pages", []):
        for v in p["visuals"]:
            for refs in v.get("roles", {}).values():
                for r in refs:
                    if r and r.get("name"):
                        fields[(r.get("table"), r.get("name"), r.get("kind"))] = r
    # Resolve Power Query parameters (e.g. ServerName = "sql01" meta [IsParameterQuery=true]) used as arguments
    params = {}
    for e in (model or {}).get("expressions", []):
        lit = re.match(r'^\s*"((?:[^"]|"")*)"', e.get("value") or "")
        if lit:
            params[e["name"]] = lit.group(1).replace('""', '"')

    def param_name(arg):
        key = arg[7:-1].strip() if arg.startswith("<expr: ") else None
        if key and key.startswith('#"') and key.endswith('"'):
            key = key[2:-1].replace('""', '"')
        return key

    def resolve(src):
        src["args"] = [("%s (=%s)" % (params[param_name(a)], param_name(a)) if param_name(a) in params else a)
                       for a in src.get("args", [])]
        return src
    for t in (model or {}).get("tables", []):
        for part in t.get("partitions", []):
            part["sources"] = [resolve(s) for s in part.get("sources", [])]
    sources = []
    if live and live.get("kind") != "local_model":
        sources.append({"type": "semantic_model", **{k: live.get(k) for k in ("workspace", "model_name", "model_id", "dataset_id", "server", "kind") if live.get(k)}})
    for t in (model or {}).get("tables", []):
        for part in t.get("partitions", []):
            for s in part.get("sources", []):
                sources.append({"type": "power_query", "table": t["name"], "mode": part.get("mode"), **s})
    for e in (model or {}).get("expressions", []):
        for s in e.get("sources", []):
            sources.append({"type": "power_query_expression", "expression": e["name"], **s})
    for q in read_datamashup(c, warnings):
        for s in q["sources"]:
            sources.append({"type": "power_query", "query": q["query"], **s})
    exemplar = {"usable": bool(roots), "visual_types": sorted({v["type"] for p in (report or {}).get("pages", []) for v in p["visuals"] if v.get("type")})}
    if not roots:
        exemplar["reason"] = ("Legacy report format: re-save the report in Power BI Desktop with the PBIR format "
                              "(File > Save as > Power BI Project) or use the starter template." if report else "No report definition found.")
    return {"file": os.path.basename(path), "container": c.kind, "report": report, "themes": read_themes(c),
            "fields_used": list(fields.values()), "semantic_model": model, "live_connection": live,
            "data_sources": sources, "exemplar": exemplar, "warnings": warnings}


def summary_md(r):
    lines = ["# Power BI sample inspection: %s (%s)" % (r["file"], r["container"]), ""]
    rep = r.get("report")
    if rep:
        lines.append("Report format: %s; pages: %d." % (rep["format"], len(rep["pages"])))
        for p in rep["pages"]:
            lines.append("- Page '%s' (%sx%s): %s" % (p["display_name"], p.get("width"), p.get("height"),
                         "; ".join("%s%s" % (v["type"], " '%s'" % v["title"] if v.get("title") else "") for v in p["visuals"])))
    if r.get("fields_used"):
        lines.append("")
        lines.append("Fields used: " + ", ".join("%s[%s] (%s)" % (f.get("table"), f.get("name"), f.get("kind")) for f in r["fields_used"]))
    lc = r.get("live_connection")
    if lc and lc.get("kind") == "local_model":
        lines.append("")
        lines.append("The report uses the semantic model inside this project (%s)." % lc.get("path"))
    elif lc:
        lines.append("")
        lines.append("Live connection: workspace %s, semantic model %s (id %s)." % (lc.get("workspace"), lc.get("model_name"), lc.get("model_id") or lc.get("dataset_id")))
    m = r.get("semantic_model")
    if m:
        lines += ["", "Embedded model (%s): %d tables." % (m["source"], len(m["tables"]))]
        for t in m["tables"]:
            lines.append("- %s: %d columns, measures: %s" % (t["name"], len(t["columns"]), ", ".join(x["name"] for x in t["measures"]) or "none"))
    if r.get("data_sources"):
        lines += ["", "Data sources:"]
        for s in r["data_sources"]:
            if s["type"] == "semantic_model":
                lines.append("- Semantic model %s / %s" % (s.get("workspace"), s.get("model_name") or s.get("model_id")))
            else:
                lines.append("- %s %s(%s)" % (s.get("table") or s.get("query") or s.get("expression"), s.get("function"), ", ".join(map(str, s.get("args", [])[:3]))))
    for t in r.get("themes", []):
        lines.append("Theme (%s) '%s': colours %s; background %s; fonts %s" % (t["type"], t["name"], ", ".join(t["data_colors"][:6]),
                     t.get("background"), {k: v.get("fontFace") for k, v in t.get("text_classes", {}).items()}))
    ex = r["exemplar"]
    lines.append("")
    lines.append("Usable as PBIR exemplar: %s%s" % (ex["usable"], "" if ex["usable"] else " - " + ex.get("reason", "")))
    if ex.get("visual_types"):
        lines.append("Visual types available to clone: " + ", ".join(ex["visual_types"]))
    if r.get("warnings"):
        lines += ["", "Warnings:"] + ["- " + w for w in r["warnings"]]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--out")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    r = inspect(a.path)
    if a.out:
        rk.dump_json(r, a.out)
    if a.summary:
        print(summary_md(r))
    elif not a.out:
        rk.dump_json(r)


if __name__ == "__main__":
    main()
