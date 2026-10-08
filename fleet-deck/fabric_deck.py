"""Fleet Deck: the operator's console over the fleet, on herdr.

One herdr tab per agent account, each entered with `moveto <account>`. The
deck's first duty is recovery: after a herdr server restart every account tab
comes back as a bare operator shell (the agent and its moveto session died
with the server), and the deck re-enters each one.

The deck owns no session ids. The control plane owns which session belongs to
which account; herdr keeps only the layout; the deck compares the two and acts
on the tabs (agent-fabric plan, decisions 1 to 5, 2026-10-07).

The planning core is pure: it takes what herdr, moveto and the control plane
report and returns actions, so it is tested without a server. The adapters at
the bottom run the real commands.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Iterable

# The workspace an account goes to when the catalogue names no group for it,
# or when its group's workspace no longer exists (the operator removed it).
NEW_WORKSPACE = "New"


@dataclass(frozen=True)
class Account:
    login: str
    role: str


@dataclass(frozen=True)
class AccountTab:
    """A herdr tab whose label is an account login, with its root pane."""

    login: str
    tab_id: str
    workspace_id: str
    pane_id: str
    # A split account tab is the operator's arrangement; the deck cannot tell
    # which pane is the account's, so it does not type into any of them.
    pane_count: int = 1


@dataclass(frozen=True)
class PaneProcess:
    """herdr's `pane.process_info` for one pane."""

    shell_pid: int | None
    foreground_process_group_id: int | None
    foreground_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreateTab:
    login: str
    workspace_label: str


@dataclass(frozen=True)
class Reenter:
    login: str
    pane_id: str


@dataclass(frozen=True)
class Leave:
    """The tab is occupied (its moveto session runs): nothing to do."""

    login: str
    pane_id: str


@dataclass(frozen=True)
class Undetermined:
    """herdr could not say what runs in the pane; the deck does not guess."""

    login: str
    pane_id: str


Action = CreateTab | Reenter | Leave | Undetermined


def parse_moveto_list(text: str, exclude: Iterable[str]) -> list[Account]:
    """Accounts from `moveto --list` ("account role clones..." per line)."""
    excluded = set(exclude)
    accounts = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] not in excluded:
            accounts.append(Account(login=fields[0], role=fields[1]))
    return accounts


def is_bare_shell(process: PaneProcess) -> bool | None:
    """Whether the pane is only its shell, waiting at a prompt.

    A bare shell is its own foreground process group; a moveto session puts
    sudo, and then the account's shell, in the foreground instead. Measured
    on herdr 0.9.3 (fork 99d4887a). None when herdr could not tell.
    """
    if process.shell_pid is None or process.foreground_process_group_id is None:
        return None
    return process.foreground_process_group_id == process.shell_pid


def seed_workspace(role: str, catalog: dict | None) -> str:
    """The workspace the role catalogue seeds for a role, or NEW_WORKSPACE."""
    if not catalog:
        return NEW_WORKSPACE
    groups = set(catalog.get("groups") or [])
    for entry in catalog.get("roles") or []:
        if entry.get("id") == role and entry.get("group") in groups:
            return entry["group"]
    return NEW_WORKSPACE


def plan(
    accounts: list[Account],
    tabs: list[AccountTab],
    processes: dict[str, PaneProcess],
    workspace_labels: set[str],
    catalog: dict | None,
) -> list[Action]:
    """What the deck does for each account, in `accounts` order.

    - No tab for the account: create one. The catalogue's group is used only
      when the deck sets up a host for the first time (no account has a tab
      yet). After that, a new account goes to its group's workspace if the
      operator kept one, else to NEW_WORKSPACE: the operator's layout is the
      truth and is never re-seeded.
    - A tab that is a bare shell: re-enter it with moveto.
    - A tab whose foreground is something else: leave it.
    The first tab carrying a login wins; a duplicate is the operator's to sort
    out, not the deck's to close.
    """
    by_login: dict[str, AccountTab] = {}
    for tab in tabs:
        by_login.setdefault(tab.login, tab)
    first_setup = not any(account.login in by_login for account in accounts)

    actions: list[Action] = []
    for account in accounts:
        tab = by_login.get(account.login)
        if tab is not None and tab.pane_count != 1:
            actions.append(Undetermined(account.login, tab.pane_id))
            continue
        if tab is None:
            seeded = seed_workspace(account.role, catalog)
            workspace = (
                seeded if first_setup or seeded in workspace_labels else NEW_WORKSPACE
            )
            actions.append(CreateTab(account.login, workspace))
            continue
        bare = is_bare_shell(processes.get(tab.pane_id, PaneProcess(None, None)))
        if bare is None:
            actions.append(Undetermined(account.login, tab.pane_id))
        elif bare:
            actions.append(Reenter(account.login, tab.pane_id))
        else:
            actions.append(Leave(account.login, tab.pane_id))
    return actions


def reenter_command(login: str, moveto_has_resume: bool) -> str:
    """The command typed into a bare account tab.

    `moveto <account> --resume` lets the account's own launcher resume its
    last session; until moveto has that flag, plain `moveto <account>` brings
    the tab back into its account, and the session is resumed by hand.
    """
    return f"moveto {login} --resume" if moveto_has_resume else f"moveto {login}"


# ----------------------------------------------------------------- statuses

# How long an account may stay restoring before the deck calls it failed: the
# daemon upgrade's stop budget (90 s) plus a launcher's start (architect-cto,
# 2026-10-08). The owner may change it; the deck prints it beside the status.
RESTORE_WAIT_S = 120

LIVE_STATES = frozenset({"working", "idle"})

# The stream posts on every change and every ten minutes; a record older than
# two heartbeats means the account's agent stopped answering (agent-fabric
# docs/fleet-deck/session-recovery.md, decision 5).
STALE_AFTER_S = 2 * 600


# A bare pane this soon after the deck typed into it is the shell not yet
# having started moveto, not moveto having exited.
ENTRY_GRACE_S = 5

ONE_SECOND = datetime.timedelta(seconds=1)


@dataclass(frozen=True)
class Session:
    session: str
    state: str
    since: str


@dataclass(frozen=True)
class StateRecord:
    """One account's row of `fabric-ctl all states --json`."""

    login: str
    state: str
    sessions: tuple[Session, ...]
    ts: str
    # The host part of the stream's address: fabric-ctl all states reports
    # every host, and the same login may exist on more than one.
    host: str = ""
    # agent-fabric ADR-029 rule 16, amended 2026-10-08; absent from an older
    # agentd's record, in which case the deck re-enters regardless.
    last_session: str | None = None
    resumable: bool | None = None


def parse_state_line(line: str) -> StateRecord | None:
    """A record, or None when the line is not one. The stream's row for an
    account with no state on the channel has no `ts`: that is no record."""
    try:
        row = json.loads(line)
        address = row["address"]
        ts = row["ts"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(ts, str) or parse_utc(ts) is None:
        return None
    sessions = tuple(
        Session(s["session"], s.get("state", "unknown"), s.get("since", ""))
        for s in row.get("sessions") or []
        if isinstance(s, dict) and s.get("session")
    )
    host, _, login = address.rpartition("/")
    return StateRecord(
        login=login,
        host=host,
        state=row.get("state", "unknown"),
        sessions=sessions,
        ts=ts,
        last_session=row.get("last_session"),
        resumable=row.get("resumable"),
    )


def parse_utc(stamp):
    import datetime

    if not isinstance(stamp, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def for_this_host(record: StateRecord | None, host: str | None) -> bool:
    """Whether a stream record describes an account on the deck's own host.
    With the host unknown every record is taken, as before hosts mattered."""
    return record is not None and (host is None or record.host == host)


def baselines_from_snapshot(
    lines: Iterable[str], host: str | None = None
) -> dict[str, frozenset[str]]:
    """Per account, the sessions live in a snapshot taken before the deck acts:
    sessions elsewhere, which its re-entry cannot have started. The account's
    last_session is never part of it: bringing that session back is what the
    deck waits for, and a record from before the restart may still list it."""
    baselines: dict[str, frozenset[str]] = {}
    for line in lines:
        record = parse_state_line(line)
        if not for_this_host(record, host):
            continue
        baselines[record.login] = frozenset(
            s.session for s in record.sessions
            if s.state in LIVE_STATES and s.session != record.last_session
        )
    return baselines


def newer_live_sessions(
    record: StateRecord | None, acted_at: str, baseline: frozenset[str] = frozenset()
) -> list[Session]:
    """Sessions the deck's re-entry may have started: live, in their state
    since after the action, and not already live before it (`baseline`). A
    session's `since` is a state change, not a start, so an older session
    turning working after the action is excluded by the baseline, not by time."""
    acted = parse_utc(acted_at)
    if record is None or acted is None:
        return []
    return [
        s for s in record.sessions
        if s.state in LIVE_STATES
        and s.session not in baseline
        # Stamps are whole seconds: a session that went live in the second of
        # the action counts; one live before it is in the baseline instead. A
        # session whose since cannot be read is never counted as the deck's.
        and (parse_utc(s.since) or acted - ONE_SECOND) >= acted
    ]


def recovery_status(
    acted_at: str,
    now: str,
    elapsed_s: float,
    record: StateRecord | None,
    pane_bare: bool | None,
    pane_last_line: str = "",
    baseline: frozenset[str] = frozenset(),
) -> str:
    """The status of an account tab the deck re-entered (decision 5).
    `baseline` holds the account's sessions live before the action."""
    posted, current = (parse_utc(record.ts) if record else None), parse_utc(now)
    if posted is None or current is None or (current - posted).total_seconds() > STALE_AFTER_S:
        return "stale"
    # The deck's re-entry runs in the pane: once the pane is a bare shell again
    # it has ended, whatever other sessions of the account do elsewhere.
    if pane_bare and elapsed_s >= ENTRY_GRACE_S:
        return "failed"
    newer = newer_live_sessions(record, acted_at, baseline)
    if newer and not pane_bare:
        if record.last_session is not None:
            return "resumed" if any(s.session == record.last_session for s in newer) else "fresh"
        # An older agentd names no last_session: fabric-resume says which it did.
        return "fresh" if "fresh" in pane_last_line.lower() else "resumed"
    if elapsed_s >= RESTORE_WAIT_S:
        return "failed"
    return "restoring"


def printable(text: str) -> str:
    """Another account's pane text, safe to print on the operator's terminal."""
    return "".join(ch for ch in text if ch == "\t" or (ch.isprintable() and ord(ch) >= 0x20))


# ---------------------------------------------------------------- adapters


@dataclass
class Herdr:
    """herdr's CLI, as the deck's login sees it."""

    binary: str = field(default_factory=lambda: shutil.which("herdr") or "herdr")

    def text(self, *args: str) -> str:
        result = subprocess.run(
            [self.binary, *args], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[:300]
            raise DeckError(f"herdr {' '.join(args)}: exit {result.returncode}: {detail}")
        return result.stdout

    def call(self, *args: str) -> dict:
        out = self.text(*args)
        return json.loads(out).get("result", {}) if out.strip() else {}

    def workspaces(self) -> list[dict]:
        return self.call("workspace", "list").get("workspaces", [])

    def account_tabs(self, logins: set[str]) -> list[AccountTab]:
        panes = self.call("pane", "list").get("panes", [])
        root_pane: dict[str, str] = {}
        pane_count: dict[str, int] = {}
        for pane in panes:
            root_pane.setdefault(pane["tab_id"], pane["pane_id"])
            pane_count[pane["tab_id"]] = pane_count.get(pane["tab_id"], 0) + 1
        tabs = []
        for workspace in self.workspaces():
            listing = self.call("tab", "list", "--workspace", workspace["workspace_id"])
            for tab in listing.get("tabs", []):
                label = tab.get("label")
                if label in logins and tab["tab_id"] in root_pane:
                    tabs.append(
                        AccountTab(
                            label, tab["tab_id"], workspace["workspace_id"],
                            root_pane[tab["tab_id"]], pane_count[tab["tab_id"]],
                        )
                    )
        return tabs

    def process(self, pane_id: str) -> PaneProcess:
        info = self.call("pane", "process-info", "--pane", pane_id).get("process_info", {})
        return PaneProcess(
            shell_pid=info.get("shell_pid"),
            foreground_process_group_id=info.get("foreground_process_group_id"),
            foreground_names=tuple(p.get("name", "") for p in info.get("foreground_processes", [])),
        )


class DeckError(RuntimeError):
    pass


def moveto_list() -> str:
    return subprocess.run(
        ["moveto", "--list"], capture_output=True, text=True, timeout=60, check=True
    ).stdout


def local_host() -> str | None:
    """This host's name as the fleet addresses it (the host part of
    fabric-whoami's address), or None when it cannot be told."""
    try:
        result = subprocess.run(
            ["fabric-whoami", "--json"], capture_output=True, text=True, timeout=30
        )
        address = json.loads(result.stdout).get("address", "")
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
        return None
    host, _, _ = address.rpartition("/")
    return host or None


def states_snapshot() -> list[str]:
    """One read of the state stream: a line per placed account."""
    import sys

    try:
        result = subprocess.run(
            ["fabric-ctl", "all", "states", "--json"], capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        reason = str(error)
    else:
        # Exit 1 only means some account has no record; the relay's own
        # failures (unreachable, refused) exit higher with nothing on stdout.
        if result.returncode in (0, 1) and result.stdout.strip():
            return result.stdout.splitlines()
        reason = (result.stderr.strip() or f"exit {result.returncode}, no records")[:300]
    print(f"fabric-deck: no state snapshot before acting ({reason}); "
          "sessions already running elsewhere may be mistaken for resumed ones", file=sys.stderr)
    return []


def moveto_has_resume() -> bool:
    result = subprocess.run(["moveto", "--help"], capture_output=True, text=True, timeout=30)
    return "--resume" in (result.stdout + result.stderr)


def load_catalog(path: str | None) -> dict | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# --------------------------------------------------------------------- run

SETTLED = frozenset({"resumed", "fresh", "failed"})


def utc_now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_workspace(
    herdr: Herdr, label: str, cwd: str, spare_tabs: list[str]
) -> str:
    """The workspace with this label, created if missing. A new workspace
    starts with one numbered tab; it is noted in `spare_tabs` to be closed
    once the account tabs exist, never one the operator had."""
    for workspace in herdr.workspaces():
        if workspace.get("label") == label:
            return workspace["workspace_id"]
    made = herdr.call("workspace", "create", "--label", label, "--cwd", cwd, "--no-focus")
    if made.get("tab", {}).get("tab_id"):
        spare_tabs.append(made["tab"]["tab_id"])
    return made["workspace"]["workspace_id"]


def execute(herdr: Herdr, actions: list[Action], cwd: str, resume_flag: bool) -> dict[str, str]:
    """Carry out the plan; returns the pane each re-entered account went to."""
    entered: dict[str, str] = {}
    spare_tabs: list[str] = []
    try:
        _execute(herdr, actions, cwd, resume_flag, entered, spare_tabs)
    finally:
        for tab_id in spare_tabs:
            try:
                herdr.call("tab", "close", tab_id)
            except DeckError as error:
                # Never let a failed cleanup hide why execute stopped.
                print(f"fabric-deck: could not close spare tab {tab_id}: {error}")
    return entered


def _execute(
    herdr: Herdr, actions: list[Action], cwd: str, resume_flag: bool,
    entered: dict[str, str], spare_tabs: list[str],
) -> None:
    for action in actions:
        if isinstance(action, CreateTab):
            workspace = ensure_workspace(herdr, action.workspace_label, cwd, spare_tabs)
            made = herdr.call(
                "tab", "create", "--workspace", workspace, "--cwd", cwd,
                "--label", action.login, "--no-focus",
            )
            pane = made["root_pane"]["pane_id"]
        elif isinstance(action, Reenter):
            pane = action.pane_id
        else:
            continue
        herdr.call("pane", "run", pane, reenter_command(action.login, resume_flag))
        entered[action.login] = pane


def last_line(herdr: Herdr, pane: str) -> str:
    read = herdr.text("pane", "read", pane, "--source", "recent", "--lines", "5", "--format", "text")
    lines = [line.strip() for line in read.splitlines() if line.strip()]
    # The shell's prompt follows whatever moveto or fabric-resume printed last,
    # so the reason is the line before it.
    return printable(" | ".join(lines[-2:]))


def fabric_resume_line(herdr: Herdr, pane: str) -> str:
    """fabric-resume's own line in the pane's recent output. Once the agent's
    screen is up, the pane's last lines are the agent's, so the line is
    searched for rather than taken from the bottom."""
    read = herdr.text("pane", "read", pane, "--source", "recent", "--lines", "200", "--format", "text")
    said = [line.strip() for line in read.splitlines() if line.strip().startswith("fabric-resume")]
    return printable(said[-1]) if said else ""


def poll(
    herdr: Herdr,
    entered: dict[str, str],
    records: dict[str, StateRecord],
    acted_at: str,
    now: str,
    elapsed_s: float,
    baselines: dict[str, frozenset[str]] | None = None,
) -> dict[str, tuple[str, str]]:
    """One pass over the re-entered accounts: login -> (status, detail).

    The pane is read when it can decide or explain the status: a bare pane
    (its last lines say why it failed), and a new session with no last_session
    to judge it by (fabric-resume's line says whether it resumed or started
    fresh). A herdr error is retried on the next pass until the wait ends."""
    result: dict[str, tuple[str, str]] = {}
    for login, pane in entered.items():
        record = records.get(login)
        baseline = frozenset((baselines or {}).get(login, ()))
        try:
            bare = is_bare_shell(herdr.process(pane))
            if bare:
                tail = last_line(herdr, pane)
            elif record is not None and record.last_session is None and newer_live_sessions(
                record, acted_at, baseline
            ):
                tail = fabric_resume_line(herdr, pane)
            else:
                tail = ""
        except DeckError as error:
            waited = elapsed_s >= RESTORE_WAIT_S
            result[login] = ("failed" if waited else "restoring", printable(str(error)))
            continue
        status = recovery_status(acted_at, now, elapsed_s, record, bare, tail, baseline)
        result[login] = (status, tail if status in {"failed", "fresh"} else "")
    return result


def snapshot_then_act(snapshot, act) -> tuple[dict[str, frozenset[str]], str, dict[str, str]]:
    """The baseline is read before any pane is touched, so a session of an
    account that runs elsewhere is known as not the deck's however soon it
    changes state. Returns the baselines, the action's time and the panes."""
    baselines = snapshot()
    acted_at = utc_now()
    return baselines, acted_at, act()


def status_line(login: str, status: str, detail: str = "") -> str:
    suffix = f"  {detail}" if detail else ""
    return f"{login:<28} {status}{suffix}"


def main(argv: list[str] | None = None) -> int:
    import argparse
    import getpass
    import queue
    import threading
    import sys
    import time

    parser = argparse.ArgumentParser(
        prog="fabric-deck",
        description="Fleet Deck: bring every agent account's herdr tab back into its account.",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    parser.add_argument("--catalog", help="the role catalogue (identities/roles/catalog.json)")
    parser.add_argument("--exclude", action="append", default=[], help="a login to leave out")
    parser.add_argument("--cwd", default=os.path.expanduser("~/projects"))
    args = parser.parse_args(argv)

    herdr = Herdr()
    accounts = parse_moveto_list(moveto_list(), exclude={getpass.getuser(), *args.exclude})
    logins = {account.login for account in accounts}
    tabs = herdr.account_tabs(logins)
    processes = {tab.pane_id: herdr.process(tab.pane_id) for tab in tabs}
    workspace_labels = {w.get("label") for w in herdr.workspaces()}
    actions = plan(accounts, tabs, processes, workspace_labels, load_catalog(args.catalog))

    for action in actions:
        kind = type(action).__name__
        where = getattr(action, "workspace_label", None) or getattr(action, "pane_id", "")
        print(status_line(action.login, kind.lower(), where))
    if args.dry_run:
        return 0

    resume_flag = moveto_has_resume()
    host = local_host()
    if host is None:
        print("fabric-deck: cannot tell this host's fleet name (fabric-whoami); "
              "state records of the same login on other hosts may be mixed in", file=sys.stderr)
    baselines, acted_at, entered = snapshot_then_act(
        lambda: baselines_from_snapshot(states_snapshot(), host),
        lambda: execute(herdr, actions, args.cwd, resume_flag),
    )
    started = time.monotonic()
    if not entered:
        return 0
    print(f"re-entered {len(entered)} account(s) at {acted_at}; "
          f"waiting up to {RESTORE_WAIT_S}s (RESTORE_WAIT_S)"
          + ("" if resume_flag else "; moveto has no --resume yet: sessions are not resumed"))

    stream = subprocess.Popen(
        ["fabric-ctl", "all", "states", "--follow", "--json"],
        stdout=subprocess.PIPE, text=True,
    )
    # A reader thread, so a quiet stream never stalls the restoring wait and a
    # burst of lines is never left unread in a buffer select cannot see.
    lines: "queue.Queue[str | None]" = queue.Queue()

    def pump() -> None:
        for raw in stream.stdout or []:
            lines.put(raw)
        lines.put(None)

    threading.Thread(target=pump, name="fabric-deck-states", daemon=True).start()
    records: dict[str, StateRecord] = {}
    shown: dict[str, str] = {}
    stream_ended = False
    try:
        while True:
            try:
                raw = lines.get(timeout=1.0)
                while True:
                    if raw is None:
                        stream_ended = True
                    else:
                        parsed = parse_state_line(raw)
                        if for_this_host(parsed, host):
                            records[parsed.login] = parsed
                    raw = lines.get_nowait()
            except queue.Empty:
                pass
            elapsed = time.monotonic() - started
            for login, (status, detail) in poll(
                herdr, entered, records, acted_at, utc_now(), elapsed, baselines
            ).items():
                if shown.get(login) != status:
                    shown[login] = status
                    print(status_line(login, status, detail), flush=True)
            if all(shown.get(login) in SETTLED for login in entered) or elapsed > RESTORE_WAIT_S + 5:
                return 0 if all(shown.get(login) != "failed" for login in entered) else 1
            if stream_ended:
                print("fabric-deck: the state stream ended", file=sys.stderr)
                return 2
    finally:
        stream.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
