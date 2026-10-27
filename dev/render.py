#!/usr/bin/env python3
"""Fill organisation settings into the skill and the agent instructions (shared by packaging and syncing).

The tracked source files keep {{PLACEHOLDERS}} so the repository can move between the personal
and enterprise GitHub accounts without carrying organisation values. Real values live in
org/org-settings.json (enterprise repo only; see org/org-settings.example.json) and are applied
to a rendered copy at packaging or sync time. Source files are never modified.

Usage (mostly called by package_skill.py and sync_to_agent.py):
  python dev/render.py --settings org/org-settings.json --out build/rendered-skill   # render the skill folder
  python dev/render.py --settings org/org-settings.json --instructions              # print rendered instructions
"""
import argparse
import json
import os
import re
import shutil
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKILL_SRC = os.path.join(ROOT, "skills", "report-development")
INSTRUCTIONS_SRC = os.path.join(ROOT, "instructions.md")
DEFAULT_SETTINGS = os.path.join(ROOT, "org", "org-settings.json")
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_EXT = {".pyc", ".pyo"}
PLACEHOLDER = re.compile(r"\{\{[A-Z0-9_]+\}\}")
REQUIRED = ["agent_name", "org_name", "tenant_id", "bi_team_contact", "publishing_guide_url", "output_root",
            "max_chat_rows", "tools", "restricted_labels"]


class SettingsError(Exception):
    pass


def load_settings(path):
    if not path or not os.path.exists(path):
        raise SettingsError("organisation settings not found: %s (copy org/org-settings.example.json to "
                            "org/org-settings.json in the enterprise repo and fill it in)" % path)
    with open(path, encoding="utf-8-sig") as f:
        s = json.load(f)
    missing = [k for k in REQUIRED if s.get(k) in (None, "", [])]
    if missing:
        raise SettingsError("org settings are missing: %s" % ", ".join(missing))
    for k in ("fabric_iq", "sql_query", "save_file"):
        if not (s.get("tools") or {}).get(k):
            raise SettingsError("org settings: tools.%s is required (the tool's name in your agent)" % k)
    text = json.dumps(s)
    if PLACEHOLDER.search(text):
        raise SettingsError("org settings still contain {{placeholders}}: %s" % ", ".join(sorted(set(PLACEHOLDER.findall(text)))))
    return s


def instruction_values(s):
    return {
        "AGENT_NAME": s["agent_name"],
        "ORG_NAME": s["org_name"],
        "BI_TEAM_CONTACT": s["bi_team_contact"],
        "MAX_CHAT_ROWS": str(s["max_chat_rows"]),
        "OUTPUT_LOCATION": "the user's own OneDrive folder '%s'" % s["output_root"],
        "RESTRICTED_LABELS": ", ".join(s["restricted_labels"]),
    }


def fill(text, values, where):
    out = PLACEHOLDER.sub(lambda m: values.get(m.group(0)[2:-2], m.group(0)), text)
    left = sorted(set(PLACEHOLDER.findall(out)))
    if left:
        raise SettingsError("%s still has placeholders after rendering: %s" % (where, ", ".join(left)))
    return out


def instructions_body(path=INSTRUCTIONS_SRC):
    """The text to paste into the agent: everything after the first line that is exactly '---'."""
    with open(path, encoding="utf-8-sig") as f:
        text = f.read().replace("\r\n", "\n")
    parts = re.split(r"(?m)^---\s*$\n", text, maxsplit=1)
    return (parts[1] if len(parts) == 2 else text).strip() + "\n"


def render_instructions(settings, path=INSTRUCTIONS_SRC):
    return fill(instructions_body(path), instruction_values(settings), "instructions.md")


def render_org_config(settings, template_path):
    with open(template_path, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    cfg["_comment"] = "Rendered from org/org-settings.json by dev/render.py. Edit the settings file, not this copy."
    for k in ("org_name", "agent_name", "tenant_id", "bi_team_contact", "publishing_guide_url", "output_root", "max_chat_rows"):
        cfg[k] = settings[k]
    cfg["tools"] = {"fabric_iq": settings["tools"]["fabric_iq"], "sql_query": settings["tools"]["sql_query"],
                    "save_file": settings["tools"]["save_file"]}
    cfg.setdefault("sensitivity", {})["restricted_labels"] = list(settings["restricted_labels"])
    cfg["sensitivity"]["allow_unprotected_copies"] = bool(settings.get("allow_unprotected_copies", False))
    cfg["pbir_starter_template"] = settings.get("pbir_starter_template")
    for k in ("sql_data_providers", "default_style", "default_page", "semantic_model_defaults", "validation"):
        if settings.get(k):
            cfg[k] = settings[k]
    text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    if PLACEHOLDER.search(text):
        raise SettingsError("config/org-config.json still has placeholders after rendering: %s"
                            % ", ".join(sorted(set(PLACEHOLDER.findall(text)))))
    return text


def skill_files(src=SKILL_SRC):
    """Relative paths (forward slashes) of the files that make up the skill."""
    out = []
    for base, dirs, names in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for n in sorted(names):
            if os.path.splitext(n)[1] in SKIP_EXT:
                continue
            out.append(os.path.relpath(os.path.join(base, n), src).replace(os.sep, "/"))
    return out


def rendered_skill(settings, src=SKILL_SRC):
    """{relative path: bytes} of the skill with organisation settings applied."""
    files = {}
    for rel in skill_files(src):
        with open(os.path.join(src, *rel.split("/")), "rb") as f:
            files[rel] = f.read()
    if settings is not None:
        files["config/org-config.json"] = render_org_config(settings, os.path.join(src, "config", "org-config.json")).encode("utf-8")
        starter = settings.get("pbir_starter_template")
        if starter and starter not in files:
            raise SettingsError("pbir_starter_template '%s' isn't in the skill folder; add the file first "
                                "(see skills/report-development/templates/README.md)" % starter)
    return files


def write_tree(files, out_dir):
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    for rel, data in files.items():
        p = os.path.join(out_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--settings", default=DEFAULT_SETTINGS)
    ap.add_argument("--out", help="folder to write the rendered skill to")
    ap.add_argument("--instructions", action="store_true", help="print the rendered instructions")
    a = ap.parse_args()
    try:
        s = load_settings(a.settings)
        if a.instructions:
            sys.stdout.write(render_instructions(s))
        if a.out:
            write_tree(rendered_skill(s), a.out)
            print("rendered skill written to", a.out)
    except SettingsError as e:
        sys.stderr.write("ERROR: %s\n" % e)
        sys.exit(1)


if __name__ == "__main__":
    main()
