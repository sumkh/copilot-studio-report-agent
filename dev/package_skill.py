#!/usr/bin/env python3
"""Check and package the report-development skill as a zip (for uploading through the Copilot Studio web portal).

Usage:
  python dev/package_skill.py [--settings org/org-settings.json] [--layout root|folder] [--strict] [--out dist/report-development.zip]

The preferred route is the VS Code extension (dev/sync_to_agent.py, see HANDOVER.md). This zip is the
alternative for uploading the skill in the web portal (Build > Skills > Upload a skill).

Checks the rules Copilot Studio applies when it loads a skill: valid YAML front matter with a
non-empty name (lowercase letters, digits, hyphens) and a one-line description, SKILL.md encoded
as UTF-8 without a byte-order mark. If org/org-settings.json exists (or --settings is given), the
packaged copy has the organisation's values filled in; otherwise it keeps the {{placeholders}}
(a warning, or an error with --strict).

--layout root    SKILL.md at the root of the zip (default)
--layout folder  everything inside a report-development/ folder (try this if an upload is rejected)
"""
import argparse
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render  # noqa: E402


def front_matter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"')
    return fm


def check_skill_md(raw):
    problems, warnings = [], []
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("SKILL.md has a UTF-8 byte-order mark; save it as UTF-8 without BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ["SKILL.md is not UTF-8"], warnings
    fm = front_matter(text.lstrip("\ufeff"))
    if not fm:
        return problems + ["SKILL.md has no YAML front matter"], warnings
    name, desc = fm.get("name", ""), fm.get("description", "")
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
        problems.append("name '%s' must use lowercase letters, digits and single hyphens" % name)
    if not desc:
        problems.append("description is empty")
    elif len(desc) > 1024:
        problems.append("description is %d characters; keep it to one line (< 1024)" % len(desc))
    elif len(desc) > 400:
        warnings.append("description is %d characters; shorter descriptions are safer" % len(desc))
    return problems, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--settings", help="organisation settings (default: org/org-settings.json if it exists)")
    ap.add_argument("--layout", choices=["root", "folder"], default="root")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--out", default=os.path.join(render.ROOT, "dist", "report-development.zip"))
    a = ap.parse_args()
    settings_path = a.settings or (render.DEFAULT_SETTINGS if os.path.exists(render.DEFAULT_SETTINGS) else None)
    try:
        settings = render.load_settings(settings_path) if settings_path else None
        files = render.rendered_skill(settings)
    except render.SettingsError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        sys.exit(1)
    problems, warnings = check_skill_md(files["SKILL.md"])
    left = sorted(set(render.PLACEHOLDER.findall(files["config/org-config.json"].decode("utf-8"))))
    if left:
        (problems if a.strict else warnings).append("placeholders still in config/org-config.json (no org settings used): %s" % ", ".join(left))
    for w in warnings:
        print("WARNING: " + w)
    if problems:
        for p in problems:
            print("ERROR: " + p)
        sys.exit(1)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    prefix = "report-development/" if a.layout == "folder" else ""
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(files):
            z.writestr(prefix + rel, files[rel])
    print("packaged %d files into %s (%d KB, layout=%s, settings=%s)" % (
        len(files), a.out, os.path.getsize(a.out) // 1024, a.layout, settings_path or "none"))


if __name__ == "__main__":
    main()
