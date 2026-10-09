"""The states of an agent's harness pane, and what the deck does in each.

The contract is agent-fabric's docs/fleet-deck/tab-states.md (#115,
27452bd6). Two observations decide a pane's state: whether moveto runs in
its foreground, and whether a harness runs under that moveto. The account's
stream record only tells a pane with no harness whether its session runs
somewhere else. Everything here is pure: the run loop observes, calls
`step`, and carries out the one re-arm it may return.
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass, replace

# How long a --resume the deck started may run without a harness before the
# deck calls it failed: the daemon upgrade's stop budget (90 s) plus a
# launcher's start (architect-cto, 2026-10-08).
RESTORE_WAIT_S = 120

# A pane this soon after the deck armed it is the operator's shell not yet
# having started moveto, not moveto having ended.
ENTRY_GRACE_S = 5

# The stream posts on every change and every ten minutes; a record older than
# two heartbeats means the account's control agent stopped answering.
STALE_AFTER_S = 2 * 600

# Session states that count as a live session, most wanting a person first.
LIVE_ORDER = ("blocked", "working", "idle")
LIVE_STATES = frozenset(LIVE_ORDER)

# moveto's modes, as the last argument of its `sudo ... enter` hand-off.
WAIT, RESUME, WATCH, PLAIN = "--wait", "--resume", "--watch", ""
MODES = frozenset({WAIT, RESUME, WATCH})

HARNESS, SHELL, STATUS = "harness", "shell", "status"
PANE_ROLES = (HARNESS, SHELL, STATUS)
# The harness is the pane a person works in; the shell and status panes
# share the rest, one above the other.
HARNESS_RATIO = 0.65


class State(enum.Enum):
    ABSENT = "absent"
    RUNNING = "running"
    STARTING = "starting"
    ELSEWHERE = "elsewhere"
    IDLE = "idle"
    FAILED = "failed"


@dataclass(frozen=True)
class Seen:
    """One look at a harness pane. None is "herdr or /proc could not say",
    on which the deck changes nothing."""

    present: bool
    moveto: bool | None = None
    harness: bool | None = None
    # moveto's mode from its argv, when moveto runs: what the pane holds.
    mode: str | None = None


@dataclass(frozen=True)
class Live:
    """The account's newest stream record, reduced to what the machine uses."""

    count: int
    state: str  # the live session state that most wants a person, or "none"
    fresh: bool


@dataclass(frozen=True)
class Track:
    """The deck's memory of one harness pane, kept for this run of the deck.

    `armed_at` and `armed_mode` are when and how the deck last started a
    moveto in the pane (monotonic seconds), None for a pane it found already
    running. `harness_seen` is whether a harness has appeared since.
    `ended_here` marks an IDLE whose pane holds the account's shell, not a
    `--wait`, shown as shell rather than dormant. `session_at` is when a
    session on the account was first seen with no harness here yet.
    `quick_ends` counts the deck's own arms in a row that ended within
    QUICK_EXIT_S with no harness; `halted` is a pane the deck stopped
    re-arming after them."""

    state: State
    armed_at: float | None = None
    armed_mode: str | None = None
    harness_seen: bool = False
    ended_here: bool = False
    session_at: float | None = None
    quick_ends: int = 0
    halted: bool = False


@dataclass(frozen=True)
class Arm:
    """Start `moveto <account> <mode>` in the pane's bare operator shell."""

    mode: str


# A moveto the deck started that ends this soon with no harness did not get
# going (sudo refused, the account is gone, enter failed). The first such end
# is re-armed as the contract says; a second in a row stops the deck from
# typing the same failing command again every few seconds.
QUICK_EXIT_S = 15
QUICK_ENDS_TO_HALT = 2

# A harness that appears within this long of a session-up is that session:
# the stream and the process walk see one start at slightly different times,
# and the pane is not called "running elsewhere" in between.
SAME_SESSION_S = 5


def live_from_record(sessions, ts_age_s: float | None) -> Live | None:
    """`sessions` are (session, state) pairs of the newest record; None when
    the account has no record."""
    if ts_age_s is None:
        return None
    states = [state for _, state in sessions if state in LIVE_STATES]
    top = next((s for s in LIVE_ORDER if s in states), "none")
    return Live(count=len(states), state=top, fresh=ts_age_s <= STALE_AFTER_S)


def step(track: Track, seen: Seen, live: Live | None, now: float) -> tuple[Track, Arm | None]:
    """One observation of a pane: its next state, and the re-arm the deck
    does, if any. A re-arm is only ever returned for a pane at the operator's
    bare shell: while moveto runs, the deck never types into or kills it."""
    if not seen.present:
        return Track(State.ABSENT), None
    if seen.moveto is None:
        return track, None
    if seen.moveto is False:
        return _moveto_ended(track, live, now)
    if track.halted:
        # A person started moveto in the pane the deck had stopped re-arming.
        track = Track(State.IDLE, armed_mode=seen.mode, ended_here=seen.mode == PLAIN)
    if seen.harness is None:
        return track, None
    if seen.harness:
        return replace(track, state=State.RUNNING, harness_seen=True, ended_here=False,
                       session_at=None, quick_ends=0), None
    count = live.count if live is not None else None
    if track.state is State.RUNNING:
        # harness-down: the account's shell is still in the pane. The stream
        # reports the session's end a little after /proc shows it, so a
        # session still up is "elsewhere" only once the window has passed.
        if count is not None and count >= 1:
            if track.session_at is None:
                return replace(track, session_at=now), None
            if now - track.session_at < SAME_SESSION_S:
                return track, None
            return replace(track, state=State.ELSEWHERE, session_at=None), None
        return replace(track, state=State.IDLE, ended_here=True, session_at=None), None
    if count is None:
        return track, None
    if count == 0:
        track = replace(track, session_at=None)
        if track.state is State.STARTING:
            if track.armed_at is not None and now - track.armed_at >= RESTORE_WAIT_S:
                # Nothing is re-armed: moveto, by now the account's shell, still runs.
                return replace(track, state=State.FAILED), None
            return track, None
        if track.state is State.ELSEWHERE:
            # The pane holds what it was armed with: a plain shell reads shell.
            return replace(track, state=State.IDLE, ended_here=track.armed_mode == PLAIN), None
        # IDLE stays IDLE and FAILED stays FAILED: it behaves as IDLE, shown failed.
        return track, None
    if track.state is State.ELSEWHERE:
        return track, None
    # A session is up and no harness is here (yet): elsewhere, once it has
    # been up longer than a start takes to reach both the stream and /proc.
    if track.session_at is None:
        return replace(track, session_at=now), None
    if now - track.session_at >= SAME_SESSION_S:
        return replace(track, state=State.ELSEWHERE, session_at=None), None
    return track, None


def _moveto_ended(track: Track, live: Live | None, now: float) -> tuple[Track, Arm | None]:
    if track.armed_at is not None and now - track.armed_at < ENTRY_GRACE_S:
        return track, None
    if track.halted:
        return track, None
    quick = (track.armed_at is not None and track.armed_mode is not None
             and not track.harness_seen and now - track.armed_at < QUICK_EXIT_S)
    ends = track.quick_ends + 1 if quick else 0
    if ends >= QUICK_ENDS_TO_HALT:
        return Track(State.FAILED, quick_ends=ends, halted=True), None
    if live is not None and live.count >= 1:
        return Track(State.ELSEWHERE, armed_at=now, armed_mode=PLAIN, quick_ends=ends), Arm(PLAIN)
    # Failed only for a --resume this run of the deck started that produced no
    # harness: a --wait that ends may be a person's choice (the deck cannot see
    # Enter), and a pane it found running may have had a harness before.
    if track.armed_mode == RESUME and track.armed_at is not None and not track.harness_seen:
        return Track(State.FAILED, armed_at=now, armed_mode=WAIT, quick_ends=ends), Arm(WAIT)
    return Track(State.IDLE, armed_at=now, armed_mode=WAIT, quick_ends=ends), Arm(WAIT)


def restore(before_live: bool, live: Live | None, now: float) -> tuple[Track, Arm]:
    """The restore decision for a harness pane that is missing or at the
    operator's bare shell. An unknown or stale `live` never leads to
    --resume: fabric-resume's refusal is the guard for a record that looks
    fresh and is wrong."""
    if live is None or not live.fresh:
        return Track(State.IDLE, armed_at=now, armed_mode=WAIT), Arm(WAIT)
    if live.count >= 1:
        # Enter must not start a second session: a plain shell, never --wait.
        return Track(State.ELSEWHERE, armed_at=now, armed_mode=PLAIN), Arm(PLAIN)
    if before_live:
        return Track(State.STARTING, armed_at=now, armed_mode=RESUME), Arm(RESUME)
    return Track(State.IDLE, armed_at=now, armed_mode=WAIT), Arm(WAIT)


def classify(seen: Seen, live: Live | None) -> Track | None:
    """A pane that survived a deck restart, with moveto in its foreground:
    classified, never re-armed. None when it cannot be classified yet."""
    if not seen.present or seen.moveto is not True or seen.harness is None:
        return None
    if seen.harness:
        return Track(State.RUNNING, armed_mode=seen.mode, harness_seen=True)
    if live is not None and live.count >= 1:
        return Track(State.ELSEWHERE, armed_mode=seen.mode)
    return Track(State.IDLE, armed_mode=seen.mode, ended_here=seen.mode == PLAIN)


# ----------------------------------------------------------------- before

# A fall of `before` settles only on an answer from the same herdr server
# this long after it: a session that ended while herdr stayed up.
SETTLE_S = 5


@dataclass(frozen=True)
class Before:
    """One account's `before`: whether its session was running, and a fall
    seen but not yet settled (its wall-clock time and the herdr server
    instance that was answering then)."""

    running: bool = False
    fall_at: float | None = None
    fall_server: tuple[int, int] | None = None


def note_live(before: Before, count: int, at: float, server: tuple[int, int] | None,
              settling: bool) -> Before:
    """The account's live count seen at `at`. A rise is written at once and
    cancels a pending fall; a fall waits to be settled, and is not even
    noted while herdr is lost or its restore undecided (`settling` False)."""
    if count >= 1:
        return Before(running=True)
    if not before.running or before.fall_at is not None:
        return before
    if not settling or server is None:
        return before
    return replace(before, fall_at=at, fall_server=server)


def settle(before: Before, server: tuple[int, int] | None, at: float) -> Before:
    """A herdr request answered at `at` by `server`. It settles a pending fall
    when the same server instance answers SETTLE_S after the fall: herdr
    stayed up, so the session ended by itself, not with herdr."""
    if before.fall_at is None or server is None or server != before.fall_server:
        return before
    if at - before.fall_at < SETTLE_S:
        return before
    return Before(running=False)


def lost(before: Before) -> Before:
    """herdr's server was lost: a pending fall is discarded, and the session
    stays recorded as running for the restore that ends the loss."""
    return replace(before, fall_at=None, fall_server=None)


def at_start(before: Before, server: tuple[int, int] | None) -> Before:
    """A fall left pending by an earlier run of the deck settles only if the
    server answering now is the instance that answered before the fall (its
    pid and start ticks): then herdr stayed up across it. Any other server,
    or none, means herdr restarted, and the fall is dropped."""
    if before.fall_at is None:
        return before
    if server is not None and server == before.fall_server:
        return Before(running=False)
    return lost(before)


def before_live(before: Before | None, first_run_live: Live | None) -> bool:
    """Whether a session was alive before the restart: the deck's own record,
    or on a first run (no record yet) a fresh stream record listing one."""
    if before is not None:
        return before.running
    return first_run_live is not None and first_run_live.fresh and first_run_live.count >= 1


# --------------------------------------------------------------- display


@dataclass(frozen=True)
class Shown:
    """What herdr's agent panel shows for a harness pane: the semantic state
    (which drives herdr's waits, notifications and rollups) and the word a
    person reads, from the contract's "the deck shows" column."""

    status: str
    # The word in the agent row in place of herdr's agent name; empty while a
    # harness runs, when herdr's own name ("claude") is the right one.
    label: str


def display(track: Track, live: Live | None) -> Shown:
    if live is None or not live.fresh:
        return Shown("unknown", "stale")
    if track.state is State.RUNNING:
        # herdr's own agent name and the session's state; a harness whose
        # session has not posted yet is starting: working.
        return Shown(live.state if live.count >= 1 else "working", "")
    if track.state is State.STARTING:
        return Shown("working", "restoring")
    if track.state is State.ELSEWHERE:
        return Shown("unknown", "running elsewhere")
    if track.state is State.FAILED:
        # A person is needed: blocked raises herdr's attention, the word says why.
        return Shown("blocked", "failed")
    if track.state is State.IDLE:
        return Shown("idle", "shell" if track.ended_here else "dormant")
    return Shown("unknown", "absent")


# ------------------------------------------------------------- foreground


# How moveto entered the account: its `sudo` hand-off, or an ssh session
# whose forced command runs `enter` as the account (agent-fabric ADR-048).
SUDO, SSH = "sudo", "ssh"


@dataclass(frozen=True)
class Moveto:
    """moveto's `sudo ... enter <dir> <title> [mode]`, or `ssh ... <login>@<host>
    <mode|shell>`, in a pane's foreground."""

    pid: int
    mode: str
    via: str = SUDO


def moveto_in(foreground: list[tuple[int, list[str]]], login: str) -> Moveto | None:
    """The account's moveto among a pane's foreground processes ((pid, argv)
    each): its `sudo ... enter <dir> <title> [mode]` hand-off, moveto's own
    process before the hand-off, or `enter` itself for the deck's own login
    (no sudo). Any other foreground is not this account's moveto."""
    for pid, argv in foreground:
        if not argv:
            continue
        program = os.path.basename(argv[0])
        if program == "ssh":
            mode = _ssh_mode(argv[1:], login)
            if mode is not None:
                return Moveto(pid, mode, SSH)
            continue
        enter = any(arg.endswith("/moveto/enter") for arg in argv)
        if program == "sudo":
            if enter and _sudo_user_is(argv, login):
                return Moveto(pid, _mode(argv))
            continue
        script = next((i for i, arg in enumerate(argv) if os.path.basename(arg) == "moveto"), None)
        if script is not None and argv[script + 1:script + 2] == [login]:
            return Moveto(pid, _mode(argv))
        if enter and login in argv:
            return Moveto(pid, _mode(argv))
    return None


def _mode(argv: list[str]) -> str:
    return argv[-1] if argv[-1] in MODES else PLAIN


# ssh's options that take the next argument as their value (OpenSSH 9).
_SSH_VALUE_OPTIONS = frozenset("BbcDEeFIiJLlmOoPpQRSWw")
# What enter-ssh accepts as the whole remote command, and the mode each is.
_SSH_WORDS = {WAIT: WAIT, WATCH: WATCH, RESUME: RESUME, "shell": PLAIN}


def _ssh_mode(args: list[str], login: str) -> str | None:
    """The mode of an ssh into this login's forced command: the account as
    the destination's user (`<login>@host`, `ssh://<login>@host`, or `-l
    <login>`), and one of enter-ssh's four words as the whole remote
    command. Anything else is some other ssh, not this account's moveto."""
    user = None
    rest: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            rest = args[i + 1:]
            break
        if arg.startswith("-") and len(arg) > 1:
            # A flag cluster (-tt, -4A); the last letter may take a value,
            # given in the same word (-p2222) or as the next one.
            last = len(arg) - 1
            for j, letter in enumerate(arg[1:], start=1):
                if letter in _SSH_VALUE_OPTIONS:
                    value = arg[j + 1:] if j < last else (args[i + 1] if i + 1 < len(args) else "")
                    if letter == "l":
                        user = value
                    if j == last:
                        i += 1
                    break
            i += 1
            continue
        rest = args[i:]
        break
    if not rest:
        return None
    destination, command = rest[0], rest[1:]
    if command[:1] == ["--"]:
        command = command[1:]
    destination = destination.removeprefix("ssh://")
    if "@" in destination:
        user = destination.rsplit("@", 1)[0]
    if user != login or len(command) != 1:
        return None
    return _SSH_WORDS.get(command[0])


def _sudo_user_is(argv: list[str], login: str) -> bool:
    for i, arg in enumerate(argv[:-1]):
        if arg == "-u" and argv[i + 1] == login:
            return True
    return f"--user={login}" in argv


def is_harness(argv: list[str]) -> bool:
    """A harness process: Claude Code itself, or agent-fabric's launcher."""
    if not argv:
        return False
    program = os.path.basename(argv[0])
    if program == "claude":
        return True
    # The launcher is a Python running launch.py as its script, not any
    # process naming the file.
    if program != "fabric-python" and not program.startswith("python"):
        return False
    return (_python_script(argv[1:]) or "").endswith("/tools/fabric/launch.py")


# Python options that take the next argument as their value.
_PYTHON_VALUE_OPTIONS = frozenset({"-X", "-W", "-Q"})


def _python_script(args: list[str]) -> str | None:
    """The script a Python command line runs: its first argument that is
    neither an option nor an option's value. None for -c and -m."""
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in ("-c", "-m"):
            return None
        if arg in _PYTHON_VALUE_OPTIONS:
            skip = True
            continue
        if arg.startswith("-"):
            continue
        return arg
    return None
