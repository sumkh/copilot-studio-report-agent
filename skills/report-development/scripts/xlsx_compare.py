#!/usr/bin/env python3
"""Compare the formatting of the user's sample workbook with a workbook exported from the new report.

Usage:
  python xlsx_compare.py SAMPLE.xlsx EXPORTED.xlsx [--sample-sheet NAME] [--exported-sheet NAME] [--json]

Compares the main table on each side: sheet name, title rows, column headers and order,
per-column number format, width and alignment, header/detail/subtotal/total fonts and
fills, alternate-row shading, subtotal/total row counts and page orientation.
Each difference is graded:
  major    the user will notice (missing column, wrong number format, wrong header text)
  minor    cosmetic (width within a few points, slightly different colour)
  expected a documented limitation of paginated Excel export (formulas, frozen panes)
Exit code 0 when there are no major differences.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402
import xlsx_profile as xp  # noqa: E402


def primary(profile, sheet=None):
    sheets = [s for s in profile["sheets"] if s.get("table")]
    if sheet:
        sheets = [s for s in sheets if s["name"] == sheet]
    if not sheets:
        rk.fail("no table found in %s%s" % (profile["file"], " sheet %s" % sheet if sheet else ""))
    return sheets[0]


def color_close(a, b, tol=24):
    if not a or not b:
        return a == b
    try:
        return all(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) <= tol for i in (1, 3, 5))
    except ValueError:
        return a == b


def compare(sample_path, exported_path, sample_sheet=None, exported_sheet=None):
    sp = xp.profile(sample_path, sample_sheet, include_samples=False)
    ep = xp.profile(exported_path, exported_sheet, include_samples=False)
    s, e = primary(sp, sample_sheet), primary(ep, exported_sheet)
    diffs = []

    def add(severity, item, sample, exported):
        diffs.append({"severity": severity, "item": item, "sample": sample, "exported": exported})
    if s["name"] != e["name"]:
        add("minor", "sheet name", s["name"], e["name"])
    st = [" ".join(c["text"] for c in r["cells"]) for r in s.get("title_block", [])]
    et = [" ".join(c["text"] for c in r["cells"]) for r in e.get("title_block", [])]
    if [x.split(":")[0] for x in st] != [x.split(":")[0] for x in et]:
        add("minor", "title rows", st, et)
    s_cols = {c["header"]: c for c in s["columns"]}
    e_cols = {c["header"]: c for c in e["columns"]}
    s_order = [c["header"] for c in s["columns"] if c["data_type"] != "empty"]
    e_order = [c["header"] for c in e["columns"] if c["data_type"] != "empty"]
    for h in s_order:
        if h not in e_cols:
            add("major", "column missing", h, None)
    for h in e_order:
        if h not in s_cols:
            add("major", "extra column", None, h)
    common = [h for h in s_order if h in e_cols]
    if [h for h in e_order if h in s_cols] != common:
        add("major", "column order", common, [h for h in e_order if h in s_cols])
    for h in common:
        a, b = s_cols[h], e_cols[h]
        fa, fb = a.get("format") or "General", b.get("format") or "General"
        if fa != fb:
            add("major", "number format of '%s'" % h, fa, fb)
        if abs((a["width_pt"] or 0) - (b["width_pt"] or 0)) > max(6, 0.15 * (a["width_pt"] or 1)):
            add("minor", "width of '%s' (pt)" % h, a["width_pt"], b["width_pt"])
        numeric = {"integer", "decimal"}
        if a["data_type"] != b["data_type"] and "empty" not in (a["data_type"], b["data_type"]) \
                and not {a["data_type"], b["data_type"]} <= numeric:
            add("major", "data type of '%s'" % h, a["data_type"], b["data_type"])
    for part in ("header", "detail", "subtotal", "grand_total"):
        a, b = s["styles"].get(part) or {}, e["styles"].get(part) or {}
        if not a or not b:
            if a and not b and part in ("subtotal", "grand_total"):
                add("major", "%s rows" % part.replace("_", " "), "present", "missing")
            continue
        for k in ("font_family", "font_size_pt", "bold"):
            if a.get(k) != b.get(k):
                add("minor", "%s %s" % (part, k.replace("_", " ")), a.get(k), b.get(k))
        for k in ("color", "background"):
            ca, cb = a.get(k) or ("#000000" if k == "color" else None), b.get(k) or ("#000000" if k == "color" else None)
            if not color_close(ca, cb):
                add("minor", "%s %s" % (part, k), ca, cb)
    if (s["styles"].get("alt_row_background") or None) != (e["styles"].get("alt_row_background") or None):
        add("minor", "alternate row shading", s["styles"].get("alt_row_background"), e["styles"].get("alt_row_background"))
    for cls in ("subtotal", "grand_total"):
        if (s.get("row_classes") or {}).get(cls, 0) != (e.get("row_classes") or {}).get(cls, 0):
            add("major", "number of %s rows" % cls.replace("_", " "), (s.get("row_classes") or {}).get(cls, 0), (e.get("row_classes") or {}).get(cls, 0))
    so = (s["features"]["page_setup"] or {}).get("orientation")
    eo = (e["features"]["page_setup"] or {}).get("orientation")
    if so and eo and so != eo:
        add("minor", "page orientation", so, eo)
    if any(c.get("formulas") for c in s["columns"]) and not any(c.get("formulas") for c in e["columns"]):
        add("expected", "formulas", "Excel formulas", "values (paginated exports don't write formulas)")
    if s["features"].get("freeze_panes") and s["features"].get("freeze_panes") != e["features"].get("freeze_panes"):
        add("expected", "frozen panes", s["features"].get("freeze_panes"), e["features"].get("freeze_panes"))
    majors = sum(1 for d in diffs if d["severity"] == "major")
    return {"sample": {"file": sp["file"], "sheet": s["name"]}, "exported": {"file": ep["file"], "sheet": e["name"]},
            "status": "PASS" if not majors else "DIFFERENCES", "counts": {k: sum(1 for d in diffs if d["severity"] == k) for k in ("major", "minor", "expected")},
            "differences": diffs}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sample")
    ap.add_argument("exported")
    ap.add_argument("--sample-sheet")
    ap.add_argument("--exported-sheet")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = compare(a.sample, a.exported, a.sample_sheet, a.exported_sheet)
    if a.json:
        print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    else:
        print("Formatting comparison: %s (major %d, minor %d, expected %d)" % (r["status"], r["counts"]["major"], r["counts"]["minor"], r["counts"]["expected"]))
        for d in r["differences"]:
            print("- [%s] %s: sample=%s exported=%s" % (d["severity"], d["item"], d["sample"], d["exported"]))
    sys.exit(0 if r["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
