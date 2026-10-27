#!/usr/bin/env python3
"""Copy the skill and the instructions into an agent workspace cloned by the Copilot Studio VS Code extension.

Usage:
  python dev/sync_to_agent.py [--agent agent] [--settings org/org-settings.json] [--dry-run | --check]

The agent must be on the GitHub Copilot harness. A clone of such an agent contains
agent.sync.yaml, settings.mcs.yml and a behaviors/ folder with one folder per skill. This script:
  1. renders the skill and instructions with org/org-settings.json (source files stay unchanged);
  2. mirrors skills/report-development/ into <agent>/behaviors/report-development/: it adds and updates
     files and removes files that no longer exist in the source. It never touches the extension's
     metadata files (*.mcs.yml);
  3. writes the rendered instructions into settings.mcs.yml
     (configuration > agentSettings > instructions > segments > StaticSegment value).
Then use the extension's Agent Changes view: Preview changes, then Apply changes. The extension
creates the skill's metadata the first time.

--dry-run  report what would change, write nothing
--check    exit 1 if the agent copy differs from the rendered source (drift check, writes nothing)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render  # noqa: E402

SKILL_NAME = "report-development"
SIDECAR = ".mcs.yml"
INSTRUCTIONS_LIMIT = 8000


def fail(msg):
    sys.stderr.write("ERROR: %s\n" % msg)
    sys.exit(1)


AGENT_MARKERS = ("agent.sync.yaml", "agent.mcs.yml", "agent.mcs.yaml")


def find_agent_folder(path):
    """The cloned agent folder: `path` itself, or its only subfolder that holds a clone
    (the extension may create a folder named after the agent inside the folder you pick)."""
    if not os.path.isdir(path) or any(os.path.exists(os.path.join(path, m)) for m in AGENT_MARKERS):
        return path
    subs = [os.path.join(path, d) for d in sorted(os.listdir(path))
            if os.path.isdir(os.path.join(path, d)) and any(os.path.exists(os.path.join(path, d, m)) for m in AGENT_MARKERS)]
    return subs[0] if len(subs) == 1 else path


def check_workspace(agent):
    if not os.path.isdir(agent):
        fail("agent folder '%s' not found. Clone the agent with the Copilot Studio extension into this folder first "
             "(see HANDOVER.md)." % agent)
    if os.path.exists(os.path.join(agent, "agent.mcs.yml")) or os.path.exists(os.path.join(agent, "agent.mcs.yaml")):
        fail("'%s' is a standard-harness agent (agent.mcs.yml). Skills need an agent on the GitHub Copilot harness: "
             "create the agent with that harness in Copilot Studio and clone it again." % agent)
    if not os.path.exists(os.path.join(agent, "agent.sync.yaml")):
        fail("'%s' doesn't look like a cloned GitHub Copilot harness agent (no agent.sync.yaml)." % agent)
    if not os.path.exists(os.path.join(agent, "settings.mcs.yml")):
        fail("'%s' has no settings.mcs.yml; use Get changes in the extension to restore it." % agent)


# ----------------------------------------------------------------------------
# Skill files
# ----------------------------------------------------------------------------

def same_content(a, b):
    """Equal bytes, or the same UTF-8 text apart from line endings and a byte-order mark
    (the extension may write files back with CRLF on Windows)."""
    if a == b:
        return True
    try:
        na, nb = (x.decode("utf-8").lstrip("\ufeff").replace("\r\n", "\n") for x in (a, b))
    except UnicodeDecodeError:
        return False
    return na == nb


def plan_skill_sync(rendered, target):
    """Return (adds, updates, removes); removes include the matching sidecars."""
    existing = {}
    if os.path.isdir(target):
        for base, dirs, names in os.walk(target):
            dirs[:] = [d for d in dirs if d not in render.SKIP_DIRS]
            for n in names:
                rel = os.path.relpath(os.path.join(base, n), target).replace(os.sep, "/")
                existing[rel] = os.path.join(base, n)
    adds, updates, removes = [], [], []
    for rel, data in sorted(rendered.items()):
        if rel not in existing:
            adds.append(rel)
        else:
            with open(existing[rel], "rb") as f:
                if not same_content(f.read(), data):
                    updates.append(rel)
    for rel in sorted(existing):
        if rel.endswith(SIDECAR) or rel in rendered or rel.startswith("."):
            continue
        removes.append(rel)
        if rel + SIDECAR in existing:
            removes.append(rel + SIDECAR)
    return adds, updates, removes


def apply_skill_sync(rendered, target, adds, updates, removes):
    for rel in adds + updates:
        p = os.path.join(target, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(rendered[rel])
    for rel in removes:
        p = os.path.join(target, *rel.split("/"))
        if os.path.exists(p):
            os.remove(p)
    for base, dirs, names in os.walk(target, topdown=False):      # tidy folders left empty
        if base != target and not os.listdir(base):
            os.rmdir(base)


# ----------------------------------------------------------------------------
# Instructions in settings.mcs.yml
# ----------------------------------------------------------------------------

def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _instructions_span(lines):
    """(agentSettings line, child indent, instructions line or None, line after the instructions block)."""
    a = next((i for i, l in enumerate(lines) if l.strip() == "agentSettings:"), None)
    if a is None:
        raise ValueError("settings.mcs.yml has no 'agentSettings:' section. Set any instruction text once in "
                         "Copilot Studio, use Get changes, then run this again.")
    a_ind = _indent(lines[a])
    end = next((j for j in range(a + 1, len(lines)) if lines[j].strip() and _indent(lines[j]) <= a_ind), len(lines))
    child_ind = next((_indent(lines[j]) for j in range(a + 1, end) if lines[j].strip()), a_ind + 2)
    i = next((j for j in range(a + 1, end) if lines[j].strip() == "instructions:" and _indent(lines[j]) == child_ind), None)
    if i is None:
        return a, child_ind, None, None
    k = next((j for j in range(i + 1, len(lines)) if lines[j].strip() and _indent(lines[j]) <= child_ind), len(lines))
    return a, child_ind, i, k


def set_instructions(settings_text, instructions):
    """Return settings.mcs.yml text with the instructions replaced (or added) under agentSettings."""
    bom = settings_text.startswith("\ufeff")
    text = settings_text.lstrip("\ufeff")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    a, child_ind, i, k = _instructions_span(lines)
    pad = " " * child_ind
    block = [pad + "instructions:", pad + "  segments:", pad + "    - kind: StaticSegment", pad + "      value: |-"]
    block += [(pad + "        " + l) if l.strip() else "" for l in instructions.rstrip("\n").split("\n")]
    if i is None:
        new_lines = lines[:a + 1] + block + [""] + lines[a + 1:]
    else:
        trailing_blank = k > i + 1 and not lines[k - 1].strip()
        new_lines = lines[:i] + block + ([""] if trailing_blank else []) + lines[k:]
    return ("\ufeff" if bom else "") + newline.join(new_lines)


def current_instructions(settings_text):
    """The instructions text in settings.mcs.yml when it is a single StaticSegment, else None.
    Uses PyYAML when installed (reads any YAML style the extension writes), otherwise reads the
    block-scalar form that set_instructions writes."""
    text = settings_text.lstrip("\ufeff")
    try:
        import yaml
    except ImportError:
        return instructions_from_block(text)
    try:
        segments = yaml.safe_load(text)["configuration"]["agentSettings"]["instructions"]["segments"]
    except (yaml.YAMLError, KeyError, TypeError):
        return None
    if isinstance(segments, list) and len(segments) == 1 and isinstance(segments[0], dict) \
            and segments[0].get("kind") == "StaticSegment" and isinstance(segments[0].get("value"), str):
        return segments[0]["value"]
    return None


def instructions_from_block(settings_text):
    """Standard-library reader for the StaticSegment `value: |-` block written by set_instructions."""
    lines = settings_text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    _, _, i, k = _instructions_span(lines)
    if i is None:
        return None
    values = [j for j in range(i + 1, k) if lines[j].strip() in ("value: |-", "value: |")]
    if len(values) != 1:
        return None
    v = values[0]
    body = [l for l in lines[v + 1:k] if l.strip()]
    ind = min((_indent(l) for l in body), default=0)
    if ind <= _indent(lines[v]):
        return None
    out = [l[ind:] if l.strip() else "" for l in lines[v + 1:k]]
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


def _norm(text):
    return None if text is None else "\n".join(l.rstrip() for l in text.strip("\n").split("\n"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", help="cloned agent folder (default: agent_folder from the settings, else 'agent')")
    ap.add_argument("--settings", default=render.DEFAULT_SETTINGS)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    a = ap.parse_args()
    try:
        settings = render.load_settings(a.settings)
        rendered = render.rendered_skill(settings)
        instructions = render.render_instructions(settings)
    except render.SettingsError as e:
        fail(str(e))
    agent = find_agent_folder(a.agent or os.path.join(render.ROOT, settings.get("agent_folder") or "agent"))
    check_workspace(agent)
    target = os.path.join(agent, "behaviors", SKILL_NAME)
    if os.path.exists(os.path.join(target, ".skill.json")):
        fail("the skill folder in the agent uses the older packaged layout. Use Get changes in the extension first "
             "(it converts the layout), then run this again.")
    adds, updates, removes = plan_skill_sync(rendered, target)
    settings_path = os.path.join(agent, "settings.mcs.yml")
    with open(settings_path, encoding="utf-8", newline="") as f:      # keep CRLF if the extension wrote it
        settings_text = f.read()
    try:
        instr_changed = _norm(current_instructions(settings_text)) != _norm(instructions)
        new_settings = set_instructions(settings_text, instructions) if instr_changed else settings_text
    except ValueError as e:
        fail(str(e))
    print("Agent folder: %s" % agent)
    print("Skill files:  %d to add, %d to update, %d to remove" % (len(adds), len(updates), len(removes)))
    for label, items in (("add", adds), ("update", updates), ("remove", removes)):
        for rel in items:
            print("  %-6s behaviors/%s/%s" % (label, SKILL_NAME, rel))
    print("Instructions: %s (%d characters)" % ("changed" if instr_changed else "unchanged", len(instructions)))
    if len(instructions) > INSTRUCTIONS_LIMIT:
        print("WARNING: Copilot Studio instructions are limited to %d characters; shorten instructions.md." % INSTRUCTIONS_LIMIT)
    if a.check:
        drift = bool(adds or updates or removes or instr_changed)
        print("DRIFT: the agent copy differs from the source; run without --check, then apply." if drift else "In sync.")
        sys.exit(1 if drift else 0)
    if a.dry_run:
        print("Dry run: nothing written.")
        return
    apply_skill_sync(rendered, target, adds, updates, removes)
    if instr_changed:
        with open(settings_path, "w", encoding="utf-8", newline="") as f:
            f.write(new_settings)
    print("Done. Next: in VS Code open the Copilot Studio 'Agent Changes' view, select Preview changes, review, then Apply changes.")
    print("Afterwards use Get changes so the extension writes the skill's metadata files, and commit everything.")


if __name__ == "__main__":
    main()
