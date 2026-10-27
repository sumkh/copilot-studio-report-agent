#!/usr/bin/env python3
"""Tests for the handover tooling: render.py, sync_to_agent.py, set_repo.py and package_skill.py.

Usage:
  python test_handover.py            # standard library only; PyYAML, when installed, adds a YAML parse check

run_tests.py runs these too. The fake agent workspace is modelled on the Copilot Studio VS Code
extension's clone of a GitHub Copilot harness ("cli") agent: agent.sync.yaml, settings.mcs.yml,
behaviors/<skill>/ with skill.mcs.yml and per-file .mcs.yml sidecars, and a hidden .mcs/ folder.
"""
import json
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEV = os.path.normpath(os.path.join(HERE, ".."))
ROOT = os.path.normpath(os.path.join(DEV, ".."))
SYNC = os.path.join(DEV, "sync_to_agent.py")
PACKAGE = os.path.join(DEV, "package_skill.py")
SET_REPO = os.path.join(DEV, "set_repo.py")
EXAMPLE_SETTINGS = os.path.join(ROOT, "org", "org-settings.example.json")
sys.path.insert(0, DEV)
import render  # noqa: E402
import set_repo  # noqa: E402
import sync_to_agent  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

AGENT_SYNC = ("﻿# Workspace layout marker (Sync overlay; generic YAML, never MCS-parsed).\n"
              "# Declares the on-disk layout version only; identity lives in settings.mcs.yml.\n"
              "layoutVersion: 1\n")

SETTINGS_FIXTURE = """displayName: Report Development Assistant
schemaName: cr0a1_ReportDevelopmentAssistant
accessControlPolicy: GroupMembership
authenticationMode: Integrated
authenticationTrigger: Always
configuration:
  channels:
    - id: MsTeams
      channelId: MsTeams

  publishOnCreate: false
  isLightweightBot: false
  recognizer:
    kind: CLICopilotRecognizer

  agentSettings:
    model:
      series: GPT56Reasoning

    instructions:
      segments:
        - kind: StaticSegment

    web:
      enableWebSearch: false

  deferredProvisioning: false

template: cliagent-1.0.0
language: 1033
"""

SKILL_META = """mcs.metadata:
  componentName: report-development
  schemaName: cr0a1_ReportDevelopmentAssistant.skill.report-development
kind: InlineAgentSkill
"""

OTHER_SKILL = "---\nname: other-skill\ndescription: a skill made in the portal\n---\nLeave me alone.\n"


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def write(folder, rel, text):
    p = os.path.join(folder, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return p


def read(folder, rel):
    with open(os.path.join(folder, *rel.split("/")), encoding="utf-8", newline="") as f:
        return f.read()


def make_agent(parent, name="Report Dev Agent", crlf=True):
    """A cloned GitHub Copilot harness agent with an older copy of the skill in it."""
    agent = os.path.join(parent, name)
    write(agent, "agent.sync.yaml", AGENT_SYNC)
    write(agent, "settings.mcs.yml", SETTINGS_FIXTURE.replace("\n", "\r\n") if crlf else SETTINGS_FIXTURE)
    write(agent, ".mcs/conn.json", '{"AgentId": "00000000-0000-0000-0000-000000000001"}')
    skill = "behaviors/report-development/"
    write(agent, skill + "skill.mcs.yml", SKILL_META)
    write(agent, skill + "SKILL.md", "---\nname: report-development\ndescription: old\n---\nold\n")
    write(agent, skill + "SKILL.md.mcs.yml", "mcs.metadata:\n  componentName: SKILL.md\n")
    write(agent, skill + "references/obsolete.md", "old\n")
    write(agent, skill + "references/obsolete.md.mcs.yml", "mcs.metadata:\n  componentName: references/obsolete.md\n")
    write(agent, skill + "scripts/reportkit.py", read(render.SKILL_SRC, "scripts/reportkit.py").replace("\n", "\r\n"))
    write(agent, "behaviors/other-skill/SKILL.md", OTHER_SKILL)
    return agent


def add_checks(work, check, py=sys.executable):
    os.makedirs(work, exist_ok=True)

    def sync(*args, expect=0):
        p = subprocess.run([py, SYNC, "--settings", EXAMPLE_SETTINGS] + list(args), capture_output=True, text=True)
        out = p.stdout + p.stderr
        assert p.returncode == expect, "sync_to_agent %s exited %d (expected %d)\n%s" % (" ".join(args), p.returncode, expect, out[-2000:])
        return out

    def t_render():
        s = render.load_settings(EXAMPLE_SETTINGS)
        instr = render.render_instructions(s)
        assert not render.PLACEHOLDER.search(instr), render.PLACEHOLDER.findall(instr)
        assert "Contoso" in instr and "the user's own OneDrive folder '/Report Development Assistant'" in instr
        files = render.rendered_skill(s)
        cfg = json.loads(files["config/org-config.json"].decode("utf-8"))
        assert cfg["tools"] == s["tools"] and cfg["tenant_id"] == s["tenant_id"]
        assert cfg["sensitivity"]["restricted_labels"] == ["Highly Confidential"]
        left = [rel for rel, data in files.items() if render.PLACEHOLDER.search(data.decode("utf-8", "replace"))]
        assert not left, left
        assert "{{TENANT_ID}}" in read(render.SKILL_SRC, "config/org-config.json")      # the source keeps placeholders
        bad_p = os.path.join(work, "bad-settings.json")
        for change, msg in ((lambda d: d.pop("tenant_id"), "missing: tenant_id"),
                            (lambda d: d.update(org_name="{{ORG_NAME}}"), "placeholders"),
                            (lambda d: d["tools"].pop("sql_query"), "tools.sql_query")):
            bad = load(EXAMPLE_SETTINGS)
            change(bad)
            save(bad_p, bad)
            try:
                render.load_settings(bad_p)
            except render.SettingsError as e:
                assert msg in str(e), (msg, str(e))
            else:
                raise AssertionError("bad settings accepted (%s)" % msg)
        try:
            render.rendered_skill(dict(s, pbir_starter_template="templates/missing.zip"))
        except render.SettingsError as e:
            assert "isn't in the skill folder" in str(e)
        else:
            raise AssertionError("missing starter template accepted")
    check("render fills organisation settings into copies and rejects incomplete settings", t_render)

    def t_set_instructions():
        text = ("﻿configuration:\n    agentSettings:\n        instructions:\n            segments:\n"
                "                - kind: StaticSegment\n                  value: old text\n        web: {}\n")
        out = sync_to_agent.set_instructions(text, "First line.\n\n- a bullet: with colon\n")
        assert out.startswith("﻿") and "old text" not in out and out.endswith("        web: {}\n"), out
        assert sync_to_agent.instructions_from_block(out) == "First line.\n\n- a bullet: with colon\n"
        if yaml:
            seg = yaml.safe_load(out.lstrip("﻿"))["configuration"]["agentSettings"]["instructions"]["segments"]
            assert seg == [{"kind": "StaticSegment", "value": "First line.\n\n- a bullet: with colon"}], seg
        added = sync_to_agent.set_instructions("configuration:\n  agentSettings:\n    model:\n      series: X\n", "Hi\n")
        assert sync_to_agent.instructions_from_block(added) == "Hi\n" and "    model:\n      series: X" in added, added
    check("set_instructions replaces or adds the instructions block and keeps the rest", t_set_instructions)

    def t_sync():
        root = os.path.join(work, "agentroot")
        shutil.rmtree(root, ignore_errors=True)
        agent = make_agent(root)        # inside a subfolder named after the agent: found automatically
        skill = os.path.join(agent, "behaviors", "report-development")
        settings_p = os.path.join(agent, "settings.mcs.yml")
        n = len(render.skill_files())
        out = sync("--agent", root, "--dry-run")
        assert "%d to add, 1 to update, 2 to remove" % (n - 2) in out, out
        assert "Instructions: changed" in out and "Dry run" in out
        assert "description: old" in read(skill, "SKILL.md")
        assert "DRIFT" in sync("--agent", root, "--check", expect=1)

        sync("--agent", root)
        assert read(skill, "SKILL.md") == read(render.SKILL_SRC, "SKILL.md")
        cfg = json.loads(read(skill, "config/org-config.json"))
        assert cfg["org_name"] == "Contoso" and not render.PLACEHOLDER.search(json.dumps(cfg))
        for gone in ("references/obsolete.md", "references/obsolete.md.mcs.yml"):
            assert not os.path.exists(os.path.join(skill, gone)), gone
        for kept in ("skill.mcs.yml", "SKILL.md.mcs.yml"):
            assert os.path.exists(os.path.join(skill, kept)), kept
        assert read(agent, "behaviors/other-skill/SKILL.md") == OTHER_SKILL
        assert os.path.exists(os.path.join(agent, ".mcs", "conn.json"))
        assert "\r\n" in read(skill, "scripts/reportkit.py")      # same text with CRLF: left alone

        st = read(agent, "settings.mcs.yml")
        assert "\n" not in st.replace("\r\n", ""), "line endings of settings.mcs.yml changed"
        for needle in ("series: GPT56Reasoning", "enableWebSearch: false", "deferredProvisioning: false",
                       "kind: CLICopilotRecognizer", "template: cliagent-1.0.0"):
            assert needle in st, needle
        instr = render.render_instructions(render.load_settings(EXAMPLE_SETTINGS))
        assert sync_to_agent.instructions_from_block(st) == instr
        if yaml:
            doc = yaml.safe_load(st)
            ags = doc["configuration"]["agentSettings"]
            assert ags["instructions"]["segments"] == [{"kind": "StaticSegment", "value": instr.rstrip("\n")}]
            assert ags["web"] == {"enableWebSearch": False} and ags["model"] == {"series": "GPT56Reasoning"}

        out = sync("--agent", root, "--check")
        assert "In sync." in out and "0 to add, 0 to update, 0 to remove" in out, out
        with open(settings_p, "rb") as f:
            before = f.read()
        out = sync("--agent", root)
        assert "Instructions: unchanged" in out
        with open(settings_p, "rb") as f:
            assert f.read() == before, "a second sync changed settings.mcs.yml"

        write(skill, "SKILL.md", read(skill, "SKILL.md").replace("\n", "\r\n"))       # written back with CRLF
        sync("--agent", root, "--check")
        write(agent, "settings.mcs.yml", st.replace("Contoso", "Fabrikam"))           # edited in the portal
        assert "Instructions: changed" in sync("--agent", root, "--check", expect=1)
    check("sync_to_agent mirrors the skill, keeps extension metadata and writes the instructions", t_sync)

    def t_sync_refuses():
        std = os.path.join(work, "standard-agent")
        write(std, "agent.mcs.yml", "kind: GptComponentMetadata\n")
        assert "standard-harness" in sync("--agent", std, expect=1)
        empty = os.path.join(work, "empty-agent")
        os.makedirs(empty, exist_ok=True)
        assert "no agent.sync.yaml" in sync("--agent", empty, expect=1)
        legacy = make_agent(os.path.join(work, "legacy"), crlf=False)
        write(legacy, "behaviors/report-development/.skill.json", "{}")
        assert "older packaged layout" in sync("--agent", legacy, expect=1)
        nosettings = make_agent(os.path.join(work, "no-agent-settings"), crlf=False)
        write(nosettings, "settings.mcs.yml", "displayName: x\nconfiguration:\n  recognizer:\n    kind: CLICopilotRecognizer\n")
        assert "agentSettings" in sync("--agent", nosettings, expect=1)
    check("sync_to_agent refuses standard-harness, unknown and old-layout folders", t_sync_refuses)

    def t_set_repo():
        proj = os.path.join(work, "proj")
        shutil.rmtree(proj, ignore_errors=True)
        os.makedirs(os.path.join(proj, "dev"))
        script = shutil.copy(SET_REPO, os.path.join(proj, "dev", "set_repo.py"))
        save(os.path.join(proj, "project.json"), {"name": "x", "repository": {"url": "", "role": "", "history": []}})
        write(proj, "README.md", "# X\n")

        def sr(*args, expect=0):
            p = subprocess.run([py, script] + list(args), capture_output=True, text=True)
            assert p.returncode == expect, "set_repo %s exited %d\n%s%s" % (" ".join(args), p.returncode, p.stdout, p.stderr)
            return p.stdout

        personal, enterprise = "https://github.com/someone/report-agent.git", "https://github.com/acme-corp/report-agent.git"
        sr("--url", personal, "--no-git")
        repo = load(os.path.join(proj, "project.json"))["repository"]
        assert repo == {"url": personal, "role": "personal", "history": []}, repo
        sr("--url", "not a url", expect=1)
        if shutil.which("git"):
            def g(*a):
                return subprocess.run(["git", *a], cwd=proj, capture_output=True, text=True).stdout.strip()
            g("init", "-q")
            g("remote", "add", "origin", personal)
            sr("--url", enterprise, "--keep-previous-as", "personal")
            assert g("remote", "get-url", "origin") == enterprise
            assert g("remote", "get-url", "personal") == personal
            assert g("remote", "get-url", "--push", "personal") == set_repo.NO_PUSH
        else:
            sr("--url", enterprise, "--no-git")
        repo = load(os.path.join(proj, "project.json"))["repository"]
        assert repo["url"] == enterprise and repo["role"] == "enterprise" and repo["history"][0]["url"] == personal, repo
        readme = read(proj, "README.md")
        assert readme.count("<!-- repo:start -->") == 1 and "Repository (enterprise): " + enterprise in readme, readme
    check("set_repo moves the project to the enterprise repo and keeps the old remote fetch-only", t_set_repo)

    def t_package():
        out = os.path.join(work, "pkg.zip")
        p = subprocess.run([py, PACKAGE, "--settings", EXAMPLE_SETTINGS, "--strict", "--layout", "folder", "--out", out],
                           capture_output=True, text=True)
        assert p.returncode == 0, p.stdout + p.stderr
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            assert "report-development/SKILL.md" in names and all(n.startswith("report-development/") for n in names)
            assert len(names) == len(render.skill_files())
            assert json.loads(z.read("report-development/config/org-config.json"))["org_name"] == "Contoso"
    check("package_skill builds a zip with organisation settings filled in", t_package)


def main():
    import tempfile
    from run_tests import check, results
    work = tempfile.mkdtemp(prefix="handover_")
    print("PyYAML: %s" % ("installed, YAML parse checks on" if yaml else "not installed, YAML parse checks skipped"))
    add_checks(work, check)
    failed = [r for r in results if not r[1]]
    print("\n%d passed, %d failed. Work folder: %s" % (len(results) - len(failed), len(failed), work))
    if not failed:
        shutil.rmtree(work, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
