"""fabric-view: Fleet Deck's views of the fleet, in herdr plugin panes.

    fabric-view board                 every placed agent, one row each
    fabric-view agent [--agent L]     one agent; the login defaults to the
                                      herdr tab the pane was opened from
    fabric-view open board|agent      for a plugin action: open that pane

The data is agent-fabric's tools/fabric/fleet.py, imported from the
agent-fabric checkout, never copied (agent-fabric ADR-046). A view reads on
demand: at open it draws what fleet.py's cache holds, with its time, and
fetches; it refreshes each section by its cost class while the pane has
focus (terminal focus reporting, DECSET 1004) and stops when focus leaves;
`r` refetches every section once. A fetch already running when focus
leaves runs to its end (fleet.py's sources are bounded), and starts
nothing after it.

A view only reads. It calls no herdr socket: `server.socket_access =
"outside_panes"` refuses a pane's process, and the agent view takes its
login from HERDR_PLUGIN_CONTEXT_JSON instead. `open` is the one herdr call,
and it runs as a plugin action, which herdr places outside the panes.
"""

from __future__ import annotations

import datetime
import json
import os
import queue
import select
import shutil
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import view_render as vr

FOCUS_ON = "\x1b[?1004h"
FOCUS_OFF = "\x1b[?1004l"
TICK_S = 0.25
TOKENS_DAYS = 7
PLUGIN_ID = "fabric.fleet"
# Set by `open`: the pane was opened focused, at the person's key.
OPENED_FOCUSED = "FABRIC_VIEW_OPENED_FOCUSED"


# ── where agent-fabric is ───────────────────────────────────────────

def fabric_root(env: dict[str, str], which: Callable[[str], str | None] = shutil.which) -> str | None:
    """AGENT_FABRIC_ROOT, else the checkout the installed `fabric-ctl`
    belongs to (bin/ is a link into it): the same tree whose fleet.py the
    rest of the fleet runs."""
    root = env.get("AGENT_FABRIC_ROOT")
    if root:
        return root
    ctl = which("fabric-ctl")
    if not ctl:
        return None
    return os.path.dirname(os.path.dirname(os.path.realpath(ctl)))


def import_fleet(root: str):
    tools = os.path.join(root, "tools", "fabric")
    if not os.path.isfile(os.path.join(tools, "fleet.py")):
        raise ImportError(f"{tools} has no fleet.py: agent-fabric there predates fabric-fleet")
    sys.path.insert(0, tools)
    import fleet  # noqa: PLC0415 — found only once the root is known
    return fleet


def context_login(env: dict[str, str]) -> str | None:
    """The agent of the tab the overlay was opened from: the deck labels
    each agent's tab with its login."""
    try:
        ctx = json.loads(env.get("HERDR_PLUGIN_CONTEXT_JSON") or "{}")
    except ValueError:
        return None
    label = ctx.get("tab_label") if isinstance(ctx, dict) else None
    return label.strip() if isinstance(label, str) and label.strip() else None


# ── input ───────────────────────────────────────────────────────────

FOCUS_IN = "focus-in"
FOCUS_OUT = "focus-out"
UP, DOWN, PAGE_UP, PAGE_DOWN, HOME, END = "up", "down", "page-up", "page-down", "home", "end"
ENTER, ESCAPE, BACK = "enter", "escape", "back"

SEQUENCES = {
    b"\x1b[I": FOCUS_IN, b"\x1b[O": FOCUS_OUT,
    b"\x1b[A": UP, b"\x1bOA": UP, b"\x1b[B": DOWN, b"\x1bOB": DOWN,
    b"\x1b[5~": PAGE_UP, b"\x1b[6~": PAGE_DOWN,
    b"\x1b[H": HOME, b"\x1bOH": HOME, b"\x1b[1~": HOME,
    b"\x1b[F": END, b"\x1bOF": END, b"\x1b[4~": END,
}
SINGLE = {b"\r": ENTER, b"\n": ENTER, b"\x7f": BACK, b"\x08": BACK, b"\x03": "q"}


def parse_input(buf: bytes, final: bool) -> tuple[list[str], bytes]:
    """Events from raw terminal bytes, and the bytes of an unfinished escape
    sequence to keep for the next read. `final` (no more bytes came) makes a
    lone ESC the Escape key. An unknown sequence is dropped whole, so its
    letters never act as keys."""
    events: list[str] = []
    i = 0
    while i < len(buf):
        b = buf[i:i + 1]
        if b != b"\x1b":
            events.append(SINGLE.get(b, b.decode("latin-1")))
            i += 1
            continue
        rest = buf[i:]
        if len(rest) == 1:
            if final:
                events.append(ESCAPE)
                i += 1
                continue
            return events, rest
        if rest[1:2] not in (b"[", b"O"):
            events.append(ESCAPE)   # ESC then a key: Escape, and the key next
            i += 1
            continue
        end = 2
        while end < len(rest) and not (0x40 <= rest[end] <= 0x7e):
            end += 1
        if end >= len(rest):
            if final:
                return events, b""
            return events, rest
        seq = rest[: end + 1]
        if seq in SEQUENCES:
            events.append(SEQUENCES[seq])
        i += end + 1
    return events, b""


# ── fetching ────────────────────────────────────────────────────────

@dataclass
class Refresher:
    """Which sections to fetch, and when: each section once at open,
    whatever the focus; then again once its TTL has passed since its last
    fetch ended, and only while focused. Pure: the clock and the starting
    are the caller's."""
    ttl: dict[str, float]
    finished: dict[str, float] = field(default_factory=dict)
    running: set[str] = field(default_factory=set)

    def due(self, now: float, focused: bool | None) -> list[str]:
        return [s for s, ttl in self.ttl.items()
                if s not in self.running
                and (s not in self.finished or (focused is True and now - self.finished[s] >= ttl))]

    def refetch(self) -> list[str]:
        """`r`: every section not already being read."""
        return [s for s in self.ttl if s not in self.running]

    def started(self, section: str) -> None:
        self.running.add(section)

    def ended(self, section: str, now: float) -> None:
        self.running.discard(section)
        self.finished[section] = now


@dataclass
class Result:
    section: str
    records: dict[str, dict]      # login -> record
    why: str | None = None         # the whole fetch failed (fleet refused)
    asker: object = None           # the view whose fetch this was


class Store:
    """The records a view shows, cached or fetched, per section and login."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, dict]] = {}
        self.fetched = False

    def put(self, section: str, records: dict[str, dict]) -> None:
        self.records.setdefault(section, {}).update(records)

    def get(self, section: str, login: str) -> dict | None:
        return self.records.get(section, {}).get(login)


def cached_records(fleet, section: str, env: dict[str, str]) -> dict[str, dict]:
    """fleet.py's cache as it is, however old: drawn at open with its own
    `at`, so a person sees the last answer before the first fetch ends."""
    directory, _ = fleet.cache_dir(env)
    days = TOKENS_DAYS if section == "tokens" else None
    name = fleet.cache_name(type("Q", (), {"days": days})(), fleet.SECTIONS[section])
    return {login: e["record"] for login, e in fleet.cache_read(directory, name).items()}


class Fetcher:
    """Runs fleet.fetch for one section in a thread, results to a queue."""

    def __init__(self, fleet, agent: str | None, results: "queue.Queue[Result]", asker: object) -> None:
        self.fleet = fleet
        self.agent = agent
        self.results = results
        self.asker = asker

    def start(self, section: str, force: bool) -> None:
        threading.Thread(target=self._run, args=(section, force), daemon=True).start()

    def _run(self, section: str, force: bool) -> None:
        days = TOKENS_DAYS if section == "tokens" else None
        try:
            doc = self.fleet.fetch([section], self.agent, 0 if force else None, days=days)
            records = {a["login"]: a["sections"][section] for a in doc["agents"]}
            self.results.put(Result(section, records, asker=self.asker))
        except Exception as e:  # noqa: BLE001 — a refusal is shown as that section's failure, never a crash
            self.results.put(Result(section, {}, f"{type(e).__name__}: {e}", self.asker))


# ── the views ───────────────────────────────────────────────────────

class View:
    """One screen: its sections, its refresher, its fetcher."""

    def __init__(self, fleet, sections: tuple[str, ...], agent: str | None, store: Store,
                 results: "queue.Queue[Result]") -> None:
        self.sections = sections
        self.agent = agent
        self.store = store
        self.refresher = Refresher({s: fleet.SECTIONS[s].ttl for s in sections})
        self.fetcher = Fetcher(fleet, agent, results, self)
        self.whys: dict[str, str] = {}

    def tick(self, focused: bool | None) -> None:
        for s in self.refresher.due(time.monotonic(), focused):
            self.refresher.started(s)
            self.fetcher.start(s, force=False)

    def refetch(self) -> None:
        for s in self.refresher.refetch():
            self.refresher.started(s)
            self.fetcher.start(s, force=True)

    def owns(self, result: Result) -> bool:
        return result.asker is self

    def take(self, result: Result) -> None:
        self.refresher.ended(result.section, time.monotonic())
        if result.why:
            self.whys[result.section] = result.why
        else:
            self.whys.pop(result.section, None)


def agents_of(placements, store: Store, sections: tuple[str, ...], whys: dict[str, str]) -> list[vr.Agent]:
    out = []
    for login, a in placements.items():
        recs = {}
        for s in sections:
            rec = store.get(s, login)
            if s in whys:
                # The last fetch of the whole section failed: an older
                # record drawn as current would hide it.
                rec = {"status": "failed", "src": "fleet", "at": None, "why": whys[s]}
            recs[s] = rec
        out.append(vr.Agent(login, a.host, a.kind, recs))
    return out


def status(view: View, agents: list[vr.Agent], focused: bool, store: Store) -> vr.Status:
    records = [r for a in agents for s, r in a.sections.items() if s in view.sections]
    return vr.Status(focused=focused, fetching=tuple(s for s in view.sections if s in view.refresher.running),
                     now=datetime.datetime.now(datetime.timezone.utc), oldest=vr.oldest_at(records),
                     from_cache=not store.fetched)


# ── the terminal ────────────────────────────────────────────────────

class Painter:
    def __init__(self, curses, screen) -> None:
        self.curses = curses
        self.screen = screen
        c = curses
        self.attrs = {vr.NORMAL: c.A_NORMAL, vr.DIM: c.A_DIM, vr.BOLD: c.A_BOLD,
                      vr.SELECTED: c.A_REVERSE, vr.FAILED: c.A_BOLD, vr.WARN: c.A_BOLD}
        if c.has_colors() and not os.environ.get("NO_COLOR"):
            c.start_color()
            c.use_default_colors()
            c.init_pair(1, c.COLOR_RED, -1)
            c.init_pair(2, c.COLOR_YELLOW, -1)
            self.attrs[vr.FAILED] = c.color_pair(1)
            self.attrs[vr.WARN] = c.color_pair(2)

    def paint(self, lines: list[vr.Line]) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        for y, line in enumerate(lines[:height]):
            x = 0
            for text, style in line:
                if x >= width:
                    break
                # The bottom-right cell cannot be written without scrolling.
                room = width - x - (1 if y == height - 1 else 0)
                part = vr.take(vr.clean(text), room)
                try:
                    self.screen.addstr(y, x, part, self.attrs.get(style, 0))
                except (self.curses.error, UnicodeEncodeError):
                    pass   # a cell the terminal cannot take stays blank, never a crash
                x += vr.cells(part)
        self.screen.refresh()


def run(curses, screen, fleet, mode: str, login: str | None) -> int:
    curses.curs_set(0)
    curses.raw()
    curses.noecho()
    sys.stdout.write(FOCUS_ON)
    sys.stdout.flush()
    painter = Painter(curses, screen)
    ascii_only = "utf" not in (sys.stdout.encoding or "").lower()
    env = dict(os.environ)
    try:
        placements = fleet.load_placements(fleet.roots.engine_root())
    except Exception as e:  # noqa: BLE001
        return show_message(curses, screen, painter, "Fleet", f"The hosts registry could not be read:\n{e}")
    if mode == "agent" and login not in placements:
        where = f"the tab {login!r}" if login else "this tab"
        return show_message(curses, screen, painter, "Agent",
                            f"{where} is not a placed agent's.\n"
                            "Open this view from an agent's tab, whose label is its login.")

    store = Store()
    sections = vr.BOARD_SECTIONS if mode == "board" else vr.AGENT_SECTIONS
    for s in set(vr.BOARD_SECTIONS) | set(vr.AGENT_SECTIONS):
        try:
            store.put(s, cached_records(fleet, s, env))
        except Exception:  # noqa: BLE001 — a cache that cannot be read is an empty one
            pass
    results: "queue.Queue[Result]" = queue.Queue()
    board = View(fleet, vr.BOARD_SECTIONS, None, store, results) if mode == "board" else None
    agent_view = View(fleet, vr.AGENT_SECTIONS, login, store, results) if mode == "agent" else None
    samples = vr.Samples()
    selected = scroll = 0
    # Unknown until herdr reports a change or a key arrives, unless `open`
    # says the pane was opened focused. herdr reports focus changes only,
    # and a pane opened in the background never had focus to lose:
    # assuming focus at open would fetch in the background.
    focused: bool | None = True if env.get(OPENED_FOCUSED) == "1" else None
    pending = b""
    size = None
    while True:
        current = agent_view or board
        current.tick(focused)
        while True:
            try:
                r = results.get_nowait()
            except queue.Empty:
                break
            store.put(r.section, r.records)
            store.fetched = store.fetched or not r.why
            for v in (board, agent_view):
                if v is not None and v.owns(r):
                    v.take(r)
            if agent_view and r.section == "proc":
                samples.add(store.get("proc", agent_view.agent))
        now_size = os.get_terminal_size(sys.stdout.fileno())
        if now_size != size:
            size = now_size
            curses.resizeterm(size.lines, size.columns)
        height, width = screen.getmaxyx()
        if agent_view is not None:
            a = agents_of({agent_view.agent: placements[agent_view.agent]}, store, agent_view.sections, agent_view.whys)[0]
            keys = vr.OVERLAY_KEYS if mode == "agent" else vr.AGENT_KEYS
            lines, scroll = vr.agent_lines(a, samples, status(agent_view, [a], focused, store), scroll,
                                           width, height, keys, ascii_only)
        else:
            agents = agents_of(placements, store, board.sections, board.whys)
            hosts = host_records(agents)
            lines = vr.board_lines(agents, hosts, status(board, agents, focused, store), selected, width, height)
        painter.paint(lines)

        ready, _, _ = select.select([sys.stdin], [], [], TICK_S)
        if ready:
            chunk = os.read(sys.stdin.fileno(), 4096)
            if not chunk:
                return 0
            events, pending = parse_input(pending + chunk, final=False)
        else:
            events, pending = parse_input(pending, final=True)
        page = max(1, height - 4)
        for ev in events:
            if ev in (FOCUS_IN, FOCUS_OUT):
                focused = ev == FOCUS_IN
                continue
            focused = True    # a key reached this pane, so it has focus
            if ev == "r":
                current.refetch()
            elif ev in ("q", "Q"):
                return 0
            elif agent_view is not None:
                if ev in (ESCAPE, BACK, "h") and board is not None:
                    agent_view, samples, scroll = None, vr.Samples(), 0
                elif ev in (ESCAPE,) and board is None:
                    return 0
                else:
                    scroll = move(scroll, ev, page, 1 << 16)
            else:
                if ev == ENTER and placements:
                    target = list(placements)[max(0, min(selected, len(placements) - 1))]
                    agent_view = View(fleet, vr.AGENT_SECTIONS, target, store, results)
                    samples, scroll = vr.Samples(), 0
                    samples.add(store.get("proc", target))
                else:
                    selected = max(0, min(move(selected, ev, page, len(placements) - 1), len(placements) - 1))


def host_records(agents: list[vr.Agent]) -> dict[str, dict | None]:
    """One `host` record per machine: every agent on it carries the same
    machine, so the freshest answer stands for it."""
    out: dict[str, dict | None] = {}
    for a in agents:
        rec = a.sections.get("host")
        best = out.get(a.host)
        if a.host not in out or (rec is not None and (best is None or vr.failed(best)
                                                      or (vr.ok_data(rec) is not None and str(rec.get("at")) > str(best.get("at"))))):
            out[a.host] = rec
    return out


def move(pos: int, ev: str, page: int, last: int) -> int:
    step = {UP: -1, "k": -1, DOWN: 1, "j": 1, PAGE_UP: -page, PAGE_DOWN: page}.get(ev)
    if step is not None:
        return max(0, pos + step)
    if ev in (HOME, "g"):
        return 0
    if ev in (END, "G"):
        return last
    return pos


def show_message(curses, screen, painter: Painter, title: str, text: str) -> int:
    pending = b""
    while True:
        height, width = screen.getmaxyx()
        painter.paint(vr.message_lines(title, text, "q close", width, height))
        ready, _, _ = select.select([sys.stdin], [], [], TICK_S)
        if ready:
            chunk = os.read(sys.stdin.fileno(), 64)
            if not chunk:
                return 0
            events, pending = parse_input(pending + chunk, final=False)
        else:
            events, pending = parse_input(pending, final=True)
        # A focus report is not a key: only a key closes this.
        if any(ev in ("q", "Q", ESCAPE, ENTER) for ev in events):
            return 0


# ── the commands ────────────────────────────────────────────────────

USAGE = "usage: fabric-view board | agent [--agent LOGIN] | open board|agent"


def open_pane(entrypoint: str, env: dict[str, str]) -> int:
    """A plugin action's command: open the entrypoint's pane. The pane then
    runs with its own context, so the overlay learns the tab it covers."""
    herdr = env.get("HERDR_BIN_PATH") or shutil.which("herdr")
    if not herdr:
        print("fabric-view: no herdr to ask (HERDR_BIN_PATH is not set)", file=sys.stderr)
        return 2
    plugin = env.get("HERDR_PLUGIN_ID") or PLUGIN_ID
    # --focus: the person pressed a key to see this view. herdr focuses the
    # pane before the view turns focus reporting on, so no focus-in reaches
    # it; the view is told instead.
    os.execv(herdr, [herdr, "plugin", "pane", "open", "--plugin", plugin, "--entrypoint", entrypoint,
                     "--focus", "--env", f"{OPENED_FOCUSED}=1"])
    return 0   # not reached


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(USAGE, file=sys.stderr if not args else sys.stdout)
        return 0 if args else 2
    mode, rest = args[0], args[1:]
    if mode == "open":
        if rest not in (["board"], ["agent"]):
            print(USAGE, file=sys.stderr)
            return 2
        return open_pane(rest[0], dict(os.environ))
    if mode not in ("board", "agent"):
        print(USAGE, file=sys.stderr)
        return 2
    login = None
    if mode == "agent":
        if rest[:1] == ["--agent"] and len(rest) == 2:
            login = rest[1]
        elif rest:
            print(USAGE, file=sys.stderr)
            return 2
        else:
            login = context_login(dict(os.environ))
    elif rest:
        print(USAGE, file=sys.stderr)
        return 2
    root = fabric_root(dict(os.environ))
    if root is None:
        print("fabric-view: agent-fabric not found: set AGENT_FABRIC_ROOT, or put fabric-ctl on PATH", file=sys.stderr)
        return 2
    try:
        fleet = import_fleet(root)
    except ImportError as e:
        print(f"fabric-view: {e}", file=sys.stderr)
        return 2

    import curses  # noqa: PLC0415 — `open` and the refusals above need no terminal
    os.environ.setdefault("ESCDELAY", "25")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        return curses.wrapper(lambda screen: run(curses, screen, fleet, mode, login))
    except KeyboardInterrupt:
        return 0
    finally:
        sys.stdout.write(FOCUS_OFF)
        sys.stdout.flush()
