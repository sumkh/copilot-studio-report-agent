#!/usr/bin/env python3
"""Point this project at a new Git repository, e.g. after moving it from the personal to the enterprise GitHub.

Usage:
  python dev/set_repo.py --url https://github.com/<enterprise-org>/<repo>.git [--keep-previous-as personal] [--no-git]
  python dev/set_repo.py --show

Updates project.json (the single place the repository URL is recorded), the repository line in
README.md, and, unless --no-git, the 'origin' remote of the local Git clone. With
--keep-previous-as NAME the old origin stays available under NAME for fetching later
preliminary work from the personal repo; when the new repo is the enterprise one, pushing to
NAME is disabled. Never pushes anything.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PROJECT = os.path.join(ROOT, "project.json")
README = os.path.join(ROOT, "README.md")
URL_RE = re.compile(r"^(https://[^\s/]+/[^\s]+?(\.git)?|git@[^\s:]+:[^\s]+?(\.git)?|ssh://[^\s]+)$")
README_START, README_END = "<!-- repo:start -->", "<!-- repo:end -->"
NO_PUSH = "no-push--fetch-only"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def load_project():
    with open(PROJECT, encoding="utf-8") as f:
        return json.load(f)


def save_project(p):
    with open(PROJECT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)
        f.write("\n")


def update_readme(url, role):
    with open(README, encoding="utf-8") as f:
        text = f.read()
    line = "%s\nRepository (%s): %s\n%s" % (README_START, role, url or "not set yet: run `python dev/set_repo.py --url ...`", README_END)
    if README_START in text and README_END in text:
        text = re.sub(re.escape(README_START) + r".*?" + re.escape(README_END), lambda _: line, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + line + "\n"
    with open(README, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url")
    ap.add_argument("--role", choices=["personal", "enterprise"], help="default: 'personal' for the first URL recorded, 'enterprise' after that")
    ap.add_argument("--keep-previous-as", metavar="REMOTE")
    ap.add_argument("--no-git", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    p = load_project()
    repo = p.setdefault("repository", {"url": "", "role": "", "history": []})
    if a.show or not a.url:
        print(json.dumps(repo, indent=2))
        if shutil.which("git") and os.path.isdir(os.path.join(ROOT, ".git")):
            print(git("remote", "-v").stdout.strip() or "(no git remotes)")
        return
    url = a.url.strip()
    if not URL_RE.match(url):
        sys.stderr.write("ERROR: '%s' doesn't look like a Git repository URL\n" % url)
        sys.exit(1)
    role = a.role or ("personal" if not repo.get("url") else "enterprise")
    if repo.get("url") and repo["url"] != url:
        repo.setdefault("history", []).append({"url": repo["url"], "role": repo.get("role"),
                                               "until": datetime.date.today().isoformat()})
    repo["url"], repo["role"] = url, role
    save_project(p)
    update_readme(url, role)
    print("project.json and README.md now point to %s (%s)" % (url, role))
    if a.no_git:
        return
    if not shutil.which("git") or not os.path.isdir(os.path.join(ROOT, ".git")):
        print("No Git clone here (or git not installed): remotes not changed. Run 'git init' first if needed.")
        return
    remotes = git("remote").stdout.split()
    if "origin" in remotes:
        if a.keep_previous_as:
            if a.keep_previous_as in remotes:
                sys.stderr.write("ERROR: remote '%s' already exists\n" % a.keep_previous_as)
                sys.exit(1)
            git("remote", "rename", "origin", a.keep_previous_as)
            git("remote", "add", "origin", url)
            if role == "enterprise":
                git("remote", "set-url", "--push", a.keep_previous_as, NO_PUSH)
                print("Remote '%s' is fetch-only, so enterprise content can't be pushed back to it." % a.keep_previous_as)
        else:
            git("remote", "set-url", "origin", url)
    else:
        git("remote", "add", "origin", url)
    print(git("remote", "-v").stdout.strip())
    print("Nothing was pushed. Commit the project.json/README.md change, then push with: git push -u origin --all && git push origin --tags")


if __name__ == "__main__":
    main()
