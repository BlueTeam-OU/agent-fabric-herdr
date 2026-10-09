"""Fleet views: what the board and the agent view say, laid out as lines.

Pure: records in, lines out. A record is fleet.py's section record
({"status": "ok", "src", "at", "data"} or {"status": "failed", "src", "at",
"why"}); a section not read yet, from the cache or a fetch, is None. The
curses loop in fabric_view.py only paints what this module returns, so every
word a person reads is tested here without a terminal.

A line is a list of segments (text, style). Styles are names the painter
maps to attributes: every state they carry is also in the text, so the
views read the same without colour (NO_COLOR, a monochrome terminal).
"""

from __future__ import annotations

import datetime
import unicodedata
from dataclasses import dataclass, field

Seg = tuple[str, str]
Line = list[Seg]

NORMAL = "normal"
DIM = "dim"
BOLD = "bold"
SELECTED = "selected"
FAILED = "failed"
WARN = "warn"

# A cell no source has answered for yet, from the cache or a fetch.
UNREAD = "…"
# A cell whose section failed for this agent; the why is in the footer
# (board) or beside the section (agent view).
NOT_READ = "?"
NONE = "-"
# After a value that is fleet.py's last good one, kept while a fresh read
# fails: a mark in the text, so it reads without colour and on the
# selected row, explained where the screen says why.
STALE = "~"

SPARK = "▁▂▃▄▅▆▇█"
SPARK_ASCII = "_.-=+*#@"

BOARD_KEYS = "↑↓ select  Enter agent  c compare  p plan  P PRs  r refetch  q close"
AGENT_KEYS = "↑↓ scroll  r refetch  Esc back  q close"
OVERLAY_KEYS = "↑↓ scroll  r refetch  q close"


# ── values ──────────────────────────────────────────────────────────

def ok_data(record: dict | None) -> dict | None:
    """The record's value: an answer, or the last good one fleet.py keeps
    while a fresh read fails within the section's stale window."""
    if isinstance(record, dict) and record.get("status") in ("ok", "stale") and isinstance(record.get("data"), dict):
        return record["data"]
    return None


def stale(record: dict | None) -> bool:
    return isinstance(record, dict) and record.get("status") == "stale" and ok_data(record) is not None


def failed(record: dict | None) -> bool:
    return isinstance(record, dict) and record.get("status") == "failed"


def parse_utc(stamp) -> datetime.datetime | None:
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        t = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def clock(stamp, now: datetime.datetime) -> str:
    """A UTC time as the person compares it with now: HH:MMZ today, else the
    date. Always UTC, because every source stamps UTC and two time zones on
    one screen would be read as two times."""
    t = parse_utc(stamp)
    if t is None:
        return NONE
    t = t.astimezone(datetime.timezone.utc)
    if t.date() == now.astimezone(datetime.timezone.utc).date():
        return t.strftime("%H:%MZ")
    return t.strftime("%b %d")


def age(stamp, now: datetime.datetime) -> str:
    t = parse_utc(stamp)
    if t is None:
        return "never"
    s = int((now - t).total_seconds())
    if s < 0:
        return "just now"
    if s < 60:
        return f"{s} s ago"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return f"{s // 86400} d ago"


def size_kb(kb) -> str:
    if not isinstance(kb, (int, float)):
        return NONE
    mb = kb / 1024
    if mb < 1000:
        return f"{mb:.0f}M"
    return f"{mb / 1024:.1f}G"


def count(n) -> str:
    if not isinstance(n, (int, float)):
        return NONE
    for div, unit in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
        if n >= div:
            return f"{n / div:.1f}{unit}"
    return f"{n:.0f}"


def pct(v) -> str:
    return f"{v:.0f}%" if isinstance(v, (int, float)) else NONE


def sparkline(values: list[float], width: int, ascii_only: bool = False) -> str:
    """The last `width` values, scaled between their own min and max. A flat
    series is drawn at the bottom: no change reads as no change."""
    glyphs = SPARK_ASCII if ascii_only else SPARK
    vals = [v for v in values if isinstance(v, (int, float))][-width:] if width > 0 else []
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return glyphs[0] * len(vals)
    top = len(glyphs) - 1
    return "".join(glyphs[round((v - lo) / (hi - lo) * top)] for v in vals)


# What stands for a character that would move the cursor if drawn.
CONTROL = "\ufffd"


def clean(text: str) -> str:
    """Text as it may be drawn. A job title, a branch or a why comes from
    another account, and a control character in it (\\r, \\b, \\n, a C1
    code) moves the terminal's cursor: \\r alone repaints the row's agent
    and state from a title. Each is shown as one visible placeholder."""
    return "".join(CONTROL if unicodedata.category(c)[0] == "C" else c for c in text)


def char_cells(c: str) -> int:
    if unicodedata.combining(c) or unicodedata.category(c) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1


def cells(text: str) -> int:
    """Terminal cells, not characters: a CJK title is twice its length."""
    return sum(char_cells(c) for c in text)


def take(text: str, width: int) -> str:
    """The longest prefix of `text` that fits `width` cells."""
    out, used = [], 0
    for c in text:
        w = char_cells(c)
        if used + w > width:
            break
        out.append(c)
        used += w
    return "".join(out)


def fit(text: str, width: int) -> str:
    """Clean, then cut to `width` cells, marking the cut."""
    text = clean(text)
    if width <= 0:
        return ""
    if cells(text) <= width:
        return text
    return take(text, width - 1) + "…" if width > 1 else take(text, 1)


def line_text(line: Line) -> str:
    return "".join(t for t, _ in line)


# ── the cells, one rule each ────────────────────────────────────────

def cell(record: dict | None, value) -> tuple[str, str]:
    """(text, style) for a value read from a record: unread, failed, or the
    value as the caller formatted it."""
    if record is None:
        return UNREAD, DIM
    if failed(record):
        return NOT_READ, FAILED
    if ok_data(record) is None:
        return NOT_READ, FAILED
    # A stale value is drawn, marked; the footer says since when and why.
    if stale(record):
        return value(ok_data(record)) + STALE, WARN
    return value(ok_data(record)), NORMAL


def state_word(data: dict) -> str:
    state = data.get("state")
    if isinstance(state, str) and state:
        return state
    return "no session" if not data.get("sessions") else NONE


def open_jobs(data: dict | None) -> list[dict]:
    jobs = (data or {}).get("jobs")
    jobs = jobs.get("jobs") if isinstance(jobs, dict) else None
    return [j for j in jobs if isinstance(j, dict)] if isinstance(jobs, list) else []


def current_job(jobs: list[dict]) -> dict | None:
    """The job the agent is on: an active one; else a blocked one, which is
    what it waits on. A queued or delivered job is not what it is doing."""
    for state in ("active", "blocked"):
        for j in jobs:
            if j.get("state") == state:
                return j
    return None


def job_label(job: dict | None) -> str:
    if job is None:
        return NONE
    mark = "" if job.get("state") == "active" else f"({job.get('state')}) "
    return f"{job.get('id', '?')} {mark}{job.get('title') or ''}".strip()


def tokens_total(data: dict) -> int | None:
    tok = data.get("tokens")
    if not isinstance(tok, dict):
        return None
    if tok.get("status") == "no-records":
        return 0
    total = 0
    for path in ("claude", "broker"):
        p = tok.get(path)
        if isinstance(p, dict):
            total += sum(p.get(k) or 0 for k in ("input", "cache_write", "cache_read", "output")
                         if isinstance(p.get(k), (int, float)))
    return total


def window(data: dict, name: str) -> str:
    w = data.get(name)
    if isinstance(w, dict) and isinstance(w.get("utilization"), (int, float)):
        return pct(w["utilization"])
    status = data.get("usage_status")
    return "n/a" if status and status != "ok" else NONE


def pr_label(data: dict) -> str:
    prs = data.get("prs")
    if data.get("prs_ok") is False:
        return NOT_READ
    if not isinstance(prs, list) or not prs:
        return NONE
    head = pr_number(prs[0].get("pr"))
    return (f"#{head}" if head else "no PR") + (f" +{len(prs) - 1}" if len(prs) > 1 else "")


def pr_number(value) -> str | None:
    """pr-gate names a pushed branch without a PR by a word (`none`), not a
    null: only a number is a PR."""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value if isinstance(value, str) and value.isdigit() else None


# ── the board ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Column:
    key: str
    title: str
    width: int          # the minimum; `flex` columns take what is left
    drop: int           # 0 is never dropped; a higher number goes first when narrow
    flex: bool = False
    right: bool = False


BOARD_COLUMNS = (
    Column("login", "agent", 8, 0),
    Column("state", "state", 10, 0),
    Column("job", "current job", 12, 0, flex=True),
    Column("jobs", "closed/open", 11, 4, right=True),
    Column("rss", "RSS", 6, 3, right=True),
    Column("cpu", "CPU", 5, 5, right=True),
    Column("tokens", "tok 7d", 7, 7, right=True),
    Column("five_hour", "5h", 4, 6, right=True),
    Column("pr", "PR", 7, 2),
)

JOB_MAX = 60

BOARD_SECTIONS = ("states", "proc", "jobs", "closed_jobs", "prs", "usage", "host", "tokens")


@dataclass
class Agent:
    login: str
    host: str
    kind: str
    sections: dict[str, dict | None] = field(default_factory=dict)


def board_cells(a: Agent) -> dict[str, tuple[str, str]]:
    s = a.sections
    jobs = s.get("jobs")
    closed = s.get("closed_jobs")
    if jobs is None and closed is None:
        jobs_cell = (UNREAD, DIM)
    else:
        open_n = len(open_jobs(ok_data(jobs))) if ok_data(jobs) is not None else None
        closed_n = (ok_data(closed) or {}).get("closed_total") if ok_data(closed) is not None else None
        left = str(closed_n) if closed_n is not None else (UNREAD if closed is None else NOT_READ)
        right = str(open_n) if open_n is not None else (UNREAD if jobs is None else NOT_READ)
        old = STALE if stale(jobs) or stale(closed) else ""
        jobs_cell = (f"{left}/{right}{old}", FAILED if NOT_READ in (left, right) else WARN if old else NORMAL)
    return {
        "login": (a.login, BOLD),
        "state": cell(s.get("states"), state_word),
        "job": cell(jobs, lambda d: job_label(current_job(open_jobs(d)))),
        "jobs": jobs_cell,
        "rss": cell(s.get("proc"), lambda d: size_kb(d.get("rss_kb"))),
        "cpu": cell(s.get("proc"), lambda d: pct(d.get("cpu_pct"))),
        "tokens": cell(s.get("tokens"), lambda d: count(tokens_total(d))),
        "five_hour": cell(s.get("usage"), lambda d: window(d, "five_hour")),
        "pr": cell(s.get("prs"), pr_label),
    }


def board_columns(agents: list[Agent], width: int) -> list[tuple[Column, int]]:
    """The columns that fit `width`, each with its width: drop the least
    needed first, then give the flex column what is left."""
    login_w = max([BOARD_COLUMNS[0].width] + [cells(clean(a.login)) for a in agents])
    cols = [c for c in BOARD_COLUMNS]

    def need(cs: list[Column]) -> int:
        widths = [login_w if c.key == "login" else c.width for c in cs]
        return 2 + sum(widths) + (len(cs) - 1)   # the marker, and one space between columns

    while need(cols) > width and any(c.drop for c in cols):
        cols.remove(max((c for c in cols if c.drop), key=lambda c: c.drop))
    # The flex column grows to JOB_MAX at most: past that, the numbers drift
    # so far from the agent's name that a row no longer reads as one.
    spare = max(0, min(width - need(cols), JOB_MAX - next(c.width for c in cols if c.flex)))
    return [(c, login_w if c.key == "login" else c.width + (spare if c.flex else 0)) for c in cols]


def pad(text: str, width: int, right: bool) -> str:
    text = fit(text, width)
    room = " " * (width - cells(text))
    return room + text if right else text + room


def board_row(a: Agent, cols: list[tuple[Column, int]], selected: bool) -> Line:
    cells = board_cells(a)
    line: Line = [("> " if selected else "  ", SELECTED if selected else NORMAL)]
    for i, (c, w) in enumerate(cols):
        text, style = cells[c.key]
        # The whole selected row is reversed; a failed cell keeps its `?`.
        line.append((("" if i == 0 else " ") + pad(text, w, c.right), SELECTED if selected else style))
    return line


def board_header(cols: list[tuple[Column, int]]) -> Line:
    return [("  " + " ".join(pad(c.title, w, c.right) for c, w in cols), BOLD)]


def host_line(host: str, record: dict | None) -> Line:
    if record is None:
        return [(f"{host}: memory {UNREAD}", DIM)]
    data = ok_data(record)
    if data is None:
        return [(f"{host}: memory not read: {record.get('why') or 'no answer'}", FAILED)]
    machine = data.get("machine") if isinstance(data.get("machine"), dict) else {}
    mem = machine.get("mem_mb") if isinstance(machine.get("mem_mb"), dict) else {}
    parts = [host + ":" + (f" {STALE}" if stale(record) else "")]
    total, avail = mem.get("total"), mem.get("available")
    if isinstance(total, (int, float)) and isinstance(avail, (int, float)):
        parts.append(f"memory {(total - avail) / 1024:.1f} of {total / 1024:.1f} GB used")
    else:
        parts.append("memory unknown")
    if isinstance(mem.get("swap_total"), (int, float)) and isinstance(mem.get("swap_free"), (int, float)) and mem["swap_total"]:
        parts.append(f"swap {(mem['swap_total'] - mem['swap_free']) / 1024:.1f} GB")
    pressure = machine.get("memory_pressure")
    if isinstance(pressure, dict) and pressure.get("status") == "ok":
        last = pressure.get("last") if isinstance(pressure.get("last"), list) else []
        sample = last[-1] if last and isinstance(last[-1], dict) else {}
        some, full = sample.get("some_avg10"), sample.get("full_avg10")
        # PSI avg10: the share of the last 10 s some / all tasks stalled on
        # memory. Shown as read; no threshold is the deck's to judge.
        if isinstance(some, (int, float)):
            full_text = f"{full:.1f}%" if isinstance(full, (int, float)) else NONE
            parts.append(f"pressure some {some:.1f}% full {full_text}")
        else:
            parts.append("pressure not reported by the kernel")
    elif isinstance(pressure, dict):
        parts.append(f"pressure {pressure.get('status') or 'unknown'}")
    return [(" ".join(parts), NORMAL)]


def problem(name: str, record: dict | None) -> str | None:
    """Why a section's cell reads `?`: its failure, or an answer that says
    itself it is not one (pr-gate could not ask GitHub)."""
    if failed(record):
        return record.get("why") or "no answer"
    data = ok_data(record)
    if record is not None and data is None:
        return "the answer had no data"
    if name == "prs" and data is not None and data.get("prs_ok") is False:
        return "pr-gate could not list pull requests (GitHub did not answer); PRs unknown"
    return None


def failure_lines(agents: list[Agent], sections: tuple[str, ...], width: int, limit: int,
                  now: datetime.datetime | None = None) -> list[Line]:
    """One line per section that reads `?` for some agents, and one per
    section drawn stale (`~`) for some: who, and the first why. A why is
    often the same for all (a source down), so each is said once, not per
    agent. Past `limit`, the rest are named, failures and stales apart, and
    their whys are in each agent's view."""
    fails: list[tuple[str, Line]] = []
    for name in sections:
        whys = [w for a in agents if (w := problem(name, a.sections.get(name))) is not None]
        if not whys:
            continue
        who = "all agents" if len(whys) == len(agents) else f"{len(whys)} agent{'s' if len(whys) > 1 else ''}"
        fails.append((name, [(fit(f"? {name} not read for {who}: {whys[0]}", width), FAILED)]))
    stales: list[tuple[str, Line]] = []
    for name in sections:
        olds = [a for a in agents if stale(a.sections.get(name))]
        if olds:
            stales.append((name, [(fit(stale_text(name, olds, agents, now), width), WARN)]))
    items = [(FAILED, n, l) for n, l in fails] + [(WARN, n, l) for n, l in stales]
    if len(items) <= limit:
        return [l for _, _, l in items]
    # Keep as many lines whole as leave room for the tails that name the rest.
    for room in (limit - 1, limit - 2):
        rest = items[room:]
        tails = []
        for kind, word in ((FAILED, "? also not read"), (WARN, f"{STALE} also stale")):
            names = [n for k, n, _ in rest if k == kind]
            if names:
                tails.append([(fit(f"{word}: {', '.join(names)}" + why_where(names), width), kind)])
        if room + len(tails) <= limit:
            return [l for _, _, l in items[:room]] + tails
    return [l for _, _, l in items[:max(0, limit)]]


def why_where(names: list[str]) -> str:
    """Where the whys of the sections a footer could only name are: each
    agent's view shows its own sections; the host's is in the host line."""
    where = [n for n in names if n in AGENT_SECTIONS]
    return f"; why for {', '.join(where)} in each agent's view (Enter)" if where else ""


def stale_text(name: str, olds: list[Agent], agents: list[Agent], now: datetime.datetime | None) -> str:
    """`~ proc stale for a, b, read 5 min ago: why`: whose values are the
    marked ones, by name while that fits a line's worth."""
    if len(olds) == len(agents):
        who = "all agents"
    elif len(olds) <= 3:
        who = ", ".join(a.login for a in olds)
    else:
        who = f"{len(olds)} agents"
    rec = olds[0].sections[name]
    when = f", read {age(rec.get('at'), now)}" if now is not None else ""
    return f"{STALE} {name} stale for {who}{when}: {rec.get('why') or 'the last read failed'}"


@dataclass
class Status:
    """What the person needs to judge the numbers: is this live, how old is
    it, is something being read now."""
    focused: bool | None         # None: herdr has not said, and no key came yet
    fetching: tuple[str, ...]
    now: datetime.datetime
    oldest: str | None           # the oldest `at` among the records shown
    from_cache: bool             # nothing fetched yet: everything shown is the cache's


def status_line(title: str, st: Status, width: int) -> Line:
    if st.from_cache:
        when = f"from cache, {age(st.oldest, st.now)}" if st.oldest else "nothing read yet"
    else:
        when = f"oldest value {age(st.oldest, st.now)}" if st.oldest else "nothing read yet"
    mode = {True: "live", False: "paused: not focused", None: "paused: press a key to go live"}[st.focused]
    tail = f" · reading {', '.join(st.fetching)}" if st.fetching else ""
    return [(fit(f"{title} · {mode} · {when}{tail}", width), BOLD if st.focused is True else WARN)]


def oldest_at(records) -> str | None:
    stamps = [(parse_utc(r.get("at")), r.get("at")) for r in records if isinstance(r, dict)]
    stamps = [(t, s) for t, s in stamps if t is not None]
    return min(stamps)[1] if stamps else None


def board_lines(agents: list[Agent], hosts: dict[str, dict | None], st: Status,
                selected: int, width: int, height: int) -> list[Line]:
    """The whole board for a width × height window: a status line, the
    header, the rows (scrolled to keep the selection in view), and the
    footer: host memory, what was not read, the keys."""
    cols = board_columns(agents, width)
    top = [status_line(f"Fleet · {len(agents)} agents", st, width), board_header(cols)]
    footer = [host_line(h, r) for h, r in sorted(hosts.items())]
    footer += failure_lines(agents, BOARD_SECTIONS, width, limit=3, now=st.now)
    footer.append([(fit(BOARD_KEYS, width), DIM)])
    room = max(1, height - len(top) - len(footer))
    first = 0
    if agents:
        selected = max(0, min(selected, len(agents) - 1))
        first = min(max(0, selected - room + 1), max(0, len(agents) - room))
    rows = [board_row(a, cols, i == selected) for i, a in enumerate(agents)][first: first + room]
    if not agents:
        rows = [[("  no placed agents in the hosts registry", DIM)]]
    rows += [[("", NORMAL)]] * (room - len(rows))
    return [clip(line, width) for line in (top + rows + footer)][:height]


def clip(line: Line, width: int) -> Line:
    """A line cleaned and cut to `width` cells: every line drawn passes
    here or through `fit`, so no drawn text moves the cursor or wraps."""
    out: Line = []
    left = width
    for text, style in line:
        if left <= 0:
            break
        part = take(clean(text), left)
        out.append((part, style))
        left -= cells(part)
    return out


# ── the agent view ──────────────────────────────────────────────────

AGENT_SECTIONS = ("states", "presence", "proc", "jobs", "closed_jobs", "prs", "tokens", "usage")


@dataclass
class Samples:
    """Resource samples taken while this view was open, one per distinct
    `at`: a cache hit repeats a sample, and is not a new one."""
    since: str | None = None
    at: list[str] = field(default_factory=list)
    rss_kb: list[float] = field(default_factory=list)
    cpu_pct: list[float] = field(default_factory=list)

    def add(self, record: dict | None) -> None:
        data = ok_data(record)
        if data is None or record.get("at") in self.at:
            return
        self.since = self.since or record.get("at")
        self.at.append(record.get("at"))
        self.rss_kb.append(data.get("rss_kb") if isinstance(data.get("rss_kb"), (int, float)) else None)
        self.cpu_pct.append(data.get("cpu_pct") if isinstance(data.get("cpu_pct"), (int, float)) else None)


def heading(title: str, record: dict | None, now: datetime.datetime) -> Line:
    if record is None:
        return [(title, BOLD), (f"  {UNREAD} not read yet", DIM)]
    src = record.get("src") or "?"
    if stale(record):
        return [(title, BOLD), (f"  {src}, {age(record.get('at'), now)}, stale {STALE}", WARN)]
    return [(title, BOLD), (f"  {src}, {age(record.get('at'), now)}", DIM)]


def wrap_cells(text: str, width: int, indent: str = "") -> list[str]:
    """Words into lines of at most `width` cells, later lines indented; a
    word wider than a line is split. The one exception: a single
    character wider than the whole width goes on a line of its own.
    textwrap counts characters, and a line of wide characters it makes
    is twice as wide as it thinks."""
    width = max(1, width)
    # An indent that leaves no room for a cell is dropped, not overflowed.
    indent = indent if cells(indent) < width else ""
    lines: list[str] = []
    line = ""
    for word in text.split():
        while True:
            lead = indent if lines else ""
            sep = " " if line else lead
            if cells(line + sep + word) <= width:
                line += sep + word
                break
            if line:
                lines.append(line)
                line = ""
                continue
            room = width - cells(lead)
            if char_cells(word[0]) > room:
                # It fits the width but not beside the indent: this line
                # goes without the indent rather than over the width.
                lead, room = "", width
            # At least one character, so the word always shrinks.
            head = take(word, room) or word[0]
            lines.append(lead + head)
            word = word[len(head):]
            if not word:
                break
    if line:
        lines.append(line)
    return lines


def not_read(record: dict | None, width: int) -> list[Line]:
    """Why a section is missing, whole: its point is often at the end (who
    refused, and why), so it is wrapped, never cut."""
    if failed(record):
        text = clean(f"not read: {record.get('why') or 'no answer'}")
        return [[("  " + part, FAILED)] for part in wrap_cells(text, max(10, width - 4), indent="  ")]
    if record is not None and ok_data(record) is None:
        return [[("  not read: the answer had no data", FAILED)]]
    if stale(record):
        text = clean(f"{STALE} stale: the last good value; the fresh read failed: {record.get('why') or 'no answer'}")
        return [[("  " + part, WARN)] for part in wrap_cells(text, max(10, width - 4), indent="  ")]
    return []


def job_line(j: dict, now: datetime.datetime, width: int) -> Line:
    head = f"  {str(j.get('id', '?')):<5} {str(j.get('state') or '?'):<9} {clock(j.get('updated'), now):>6}  "
    return [(head, NORMAL), (fit(str(j.get("title") or ""), max(0, width - cells(clean(head)))), NORMAL)]


def agent_body(a: Agent, samples: Samples, now: datetime.datetime, width: int, ascii_only: bool = False) -> list[Line]:
    s = a.sections
    out: list[Line] = []

    states = s.get("states")
    out.append(heading("Session", states, now))
    out += not_read(states, width)
    data = ok_data(states)
    if data is not None:
        since = clock(data.get("since"), now)
        out.append([("  state ", DIM), (state_word(data), BOLD), (f" since {since}", NORMAL)])
        session = data.get("last_session")
        if isinstance(session, str) and session:
            more = " · resumable" if data.get("resumable") else ""
            out.append([(f"  session {session[:8]}{more}", NORMAL)])
    presence = ok_data(s.get("presence"))
    if presence is not None and isinstance(presence.get("presence"), dict):
        p = presence["presence"]
        word = "online" if p.get("online") else "offline"
        out.append([(f"  {word} · {p.get('sessions') or 0} session(s)" + (" · planning" if p.get("planning") else ""), NORMAL)])
    jobs = open_jobs(ok_data(s.get("jobs")))
    waits = [j for j in jobs if j.get("state") == "blocked" and j.get("blocked_on")]
    for j in waits:
        out.append([("  waits on ", DIM), (fit(f"{j.get('blocked_on')} ({j.get('id')})", max(0, width - 11)), WARN)])
    out.append([("", NORMAL)])

    proc = s.get("proc")
    out.append(heading("Resources", proc, now))
    out += not_read(proc, width)
    data = ok_data(proc)
    if data is not None:
        out.append([(f"  RSS {size_kb(data.get('rss_kb'))}  swap {size_kb(data.get('swap_kb'))}  "
                     f"CPU {pct(data.get('cpu_pct'))}  processes {data.get('procs', NONE)}", NORMAL)])
    if len(samples.at) > 1:
        span = max(8, width - 14)
        out.append([("  RSS ", DIM), (sparkline(samples.rss_kb, span, ascii_only), NORMAL)])
        out.append([("  CPU ", DIM), (sparkline(samples.cpu_pct, span, ascii_only), NORMAL)])
        out.append([(f"  {len(samples.at)} samples since {clock(samples.since, now)}, while focused", DIM)])
    out.append([("", NORMAL)])

    rec = s.get("jobs")
    out.append(heading(f"Open jobs ({len(jobs)})" if ok_data(rec) is not None else "Open jobs", rec, now))
    out += not_read(rec, width)
    out += [job_line(j, now, width) for j in jobs]
    if ok_data(rec) is not None and not jobs:
        out.append([("  none", DIM)])
    out.append([("", NORMAL)])
    rec = s.get("closed_jobs")
    data = ok_data(rec)
    closed = data.get("closed") if data and isinstance(data.get("closed"), list) else []
    total = data.get("closed_total") if data else None
    title = f"Closed jobs ({total})" if isinstance(total, int) else "Closed jobs"
    out.append(heading(title, rec, now))
    out += not_read(rec, width)
    out += [job_line(j, now, width) for j in closed if isinstance(j, dict)]
    if isinstance(total, int) and total > len(closed):
        out.append([(f"  and {total - len(closed)} older", DIM)])
    out.append([("", NORMAL)])

    rec = s.get("prs")
    out.append(heading("Pull requests", rec, now))
    out += not_read(rec, width)
    data = ok_data(rec)
    if data is not None:
        if data.get("prs_ok") is False or data.get("fetch_ok") is False:
            out.append([("  as of the last fetch: GitHub or origin did not answer", WARN)])
        for p in data.get("prs") or []:
            label = f"#{pr_number(p.get('pr'))}" if pr_number(p.get("pr")) else "no PR"
            out.append([(fit(f"  {label}  {p.get('branch') or ''}  {p.get('ahead') or 0} ahead", width), NORMAL)])
        if not data.get("prs"):
            out.append([("  none in flight", DIM)])
    out.append([("", NORMAL)])

    rec = s.get("tokens")
    out.append(heading("Tokens, 7 days", rec, now))
    out += not_read(rec, width)
    data = ok_data(rec)
    tok = data.get("tokens") if data and isinstance(data.get("tokens"), dict) else None
    if tok is not None:
        if tok.get("status") == "no-records":
            out.append([("  no requests recorded", DIM)])
        else:
            reqs = tok.get("requests") if isinstance(tok.get("requests"), dict) else {}
            out.append([(f"  {count(tokens_total(data))} tokens in {count(sum(v for v in reqs.values() if isinstance(v, (int, float))))} requests", NORMAL)])
            models = tok.get("models") if isinstance(tok.get("models"), dict) else {}
            for model, m in list(models.items())[:3]:
                if isinstance(m, dict):
                    n = sum(m.get(k) or 0 for k in ("input", "cache_write", "cache_read", "output") if isinstance(m.get(k), (int, float)))
                    out.append([(fit(f"  {count(n):>7}  {model}", width), NORMAL)])
    out.append([("", NORMAL)])

    rec = s.get("usage")
    out.append(heading("Usage windows", rec, now))
    out += not_read(rec, width)
    data = ok_data(rec)
    if data is not None:
        if data.get("usage_status") not in (None, "ok"):
            out.append([(f"  {data.get('usage_status')}", DIM)])
        for name, label in (("five_hour", "5 hours"), ("seven_day", "7 days")):
            w = data.get(name)
            if isinstance(w, dict):
                out.append([(f"  {label:<8} {pct(w.get('utilization')):>4}  resets {clock(w.get('resets_at'), now)}", NORMAL)])
    return [clip(line, width) for line in out]


def agent_where(a: Agent) -> str:
    states = ok_data(a.sections.get("states")) or {}
    role = states.get("role") or NONE
    project = states.get("project") or NONE
    return f"{role} · {project} · {a.host}"


def agent_lines(a: Agent, samples: Samples, st: Status, scroll: int, width: int, height: int,
                keys: str = AGENT_KEYS, ascii_only: bool = False) -> tuple[list[Line], int]:
    """The agent view and the scroll it was drawn at, clamped to the body."""
    # The login and whether this is live come first: on a narrow overlay
    # the rest is what gets cut.
    top = [status_line(a.login, st, width), [(fit(agent_where(a), width), DIM)]]
    footer = [[(fit(keys, width), DIM)]]
    body = agent_body(a, samples, st.now, width, ascii_only)
    room = max(1, height - len(top) - len(footer))
    scroll = max(0, min(scroll, len(body) - room))
    shown = body[scroll: scroll + room]
    shown += [[("", NORMAL)]] * (room - len(shown))
    return (top + shown + footer)[:height], scroll


def message_lines(title: str, text: str, keys: str, width: int, height: int) -> list[Line]:
    """A view that cannot show its data says why, in its own place."""
    body = [[(fit(part, width), NORMAL)] for part in text.splitlines()]
    lines = [[(fit(title, width), BOLD)], [("", NORMAL)]] + body
    lines += [[("", NORMAL)]] * max(0, height - len(lines) - 1)
    return (lines + [[(fit(keys, width), DIM)]])[:height]
