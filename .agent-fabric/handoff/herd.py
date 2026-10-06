#!/usr/bin/env python3
"""herd.py — trial: one herdr tab per agent account, each entering its own
login with `moveto <account>` (moveto does the sudo from the operator's
login). Fills a running herdr server's `fabric` workspace and never
touches another workspace. The accounts are `moveto --list`'s, but the
operator's own login; an account that already has a tab is left alone, so
it runs again safely.

    herd.py [--dry-run]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERDR = os.path.expanduser("~/.local/bin/herdr")
WORKSPACE = "fabric"
OPERATOR = "user"
PROJECTS = os.path.expanduser("~/projects")


def herdr(*args: str) -> dict:
    r = subprocess.run([HERDR, *args], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise SystemExit(f"herd: herdr {' '.join(args)}: exit {r.returncode}: {(r.stderr or r.stdout).strip()[:200]}")
    return json.loads(r.stdout).get("result", {}) if r.stdout.strip() else {}


def accounts() -> list[str]:
    r = subprocess.run(["moveto", "--list"], capture_output=True, text=True, timeout=60, check=True)
    return [f[0] for f in (line.split() for line in r.stdout.splitlines()) if f and f[0] != OPERATOR]


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    ws = next((w for w in herdr("workspace", "list")["workspaces"] if w["label"] == WORKSPACE), None)
    tabs = herdr("tab", "list", "--workspace", ws["workspace_id"]).get("tabs", []) if ws else []
    have = {t["label"] for t in tabs}
    todo = [u for u in accounts() if u not in have]
    # The tab a new workspace starts with still carries its number as label.
    spare = [t["tab_id"] for t in tabs if t["label"].isdigit()]
    if dry:
        print(f"workspace {WORKSPACE}: {ws['workspace_id'] if ws else 'to create'}; new tabs: {' '.join(todo) or 'none'}; "
              f"spare tabs to close: {' '.join(spare) or 'none'}")
        return 0
    if ws is None:
        made = herdr("workspace", "create", "--label", WORKSPACE, "--cwd", PROJECTS, "--no-focus")
        ws = made["workspace"]
        spare.append(made["tab"]["tab_id"])
    for u in todo:
        made = herdr("tab", "create", "--workspace", ws["workspace_id"], "--cwd", PROJECTS, "--label", u, "--no-focus")
        tab_id, pane_id = made["tab"]["tab_id"], made["root_pane"]["pane_id"]
        herdr("pane", "run", pane_id, f"moveto {u}")
        print(f"{u}: tab {tab_id}, pane {pane_id}")
    if todo:
        for t in spare:
            herdr("tab", "close", t)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
