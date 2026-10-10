"""Fleet reports: the compare view, the plan view and the PRs popup, laid
out as lines.

Pure, like view_render: fleet.py's records in, lines out, every word a
person reads tested here without a terminal. The per-agent records are the
board's; `plans` is one fleet-wide record (a plan's steps belong to many
agents, and some to none placed here), and so is the list of pull requests
whose owner is not a placed agent.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Callable

from view_render import (BOLD, DIM, FAILED, NONE, NORMAL, NOT_READ, STALE, UNREAD, WARN, Agent, Line, failed,
                         Status, cells, clean, clip, clock, count, fit, ok_data, open_jobs, pad, parse_utc,
                         age, pr_number, size_kb, stale, stale_text, status_line, tokens_total, wrap_cells)

COMPARE_KEYS = "←→ metric  1-6 metric  b board  p plan  P PRs  r refetch  q close"
PLAN_KEYS = "↑↓ scroll  b board  c compare  P PRs  r refetch  q close"
PRS_KEYS = "↑↓ scroll  r refetch  q close"
PRS_IN_TAB_KEYS = "↑↓ scroll  r refetch  Esc back  q close"

BAR = "█"
BAR_ASCII = "#"
HOLLOW = "░"
HOLLOW_ASCII = "-"
NOW_MARK = "│"
NOW_MARK_ASCII = "|"


# ── compare ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Metric:
    key: str
    title: str
    section: str
    value: Callable[[dict], float | None]
    show: Callable[[float], str]


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def jobs_done(data: dict) -> float | None:
    """Jobs closed as done, never dropped: fleet.py's done_total, else a
    count of the closed list when that list is the whole of it."""
    if _num(data.get("done_total")) is not None:
        return _num(data["done_total"])
    closed = data.get("closed")
    total = data.get("closed_total")
    if isinstance(closed, list) and isinstance(total, int) and len(closed) == total:
        return float(sum(1 for j in closed if isinstance(j, dict) and j.get("state") == "done"))
    return None


METRICS = (
    Metric("rss", "RSS", "proc", lambda d: _num(d.get("rss_kb")), size_kb),
    Metric("cpu", "CPU", "proc", lambda d: _num(d.get("cpu_pct")), lambda v: f"{v:.1f}%"),
    Metric("swap", "swap", "proc", lambda d: _num(d.get("swap_kb")), size_kb),
    Metric("tokens", "tokens, 7 days", "tokens", lambda d: _num(tokens_total(d)), count),
    Metric("done", "jobs done", "closed_jobs", jobs_done, lambda v: f"{v:.0f}"),
    Metric("open", "open jobs", "jobs", lambda d: float(len(open_jobs(d))) if isinstance(d.get("jobs"), dict) else None,
           lambda v: f"{v:.0f}"),
)

COMPARE_SECTIONS = ("proc", "tokens", "closed_jobs", "jobs")
MISSING = {"done": "fleet.py gave no done_total, and the closed list it gave is not the whole of it"}


def metric_value(a: Agent, m: Metric) -> tuple[float | None, str, str]:
    """(value, text, style): the value to draw a bar for, if there is one."""
    rec = a.sections.get(m.section)
    if rec is None:
        return None, UNREAD, DIM
    data = ok_data(rec)
    if data is None:
        return None, NOT_READ, FAILED
    v = m.value(data)
    if v is None:
        return None, NOT_READ, FAILED
    if stale(rec):
        return v, m.show(v) + STALE, WARN
    return v, m.show(v), NORMAL


def compare_lines(agents: list[Agent], metric: int, st: Status, scroll: int, width: int, height: int,
                  ascii_only: bool = False) -> tuple[list[Line], int]:
    """One bar per agent for one metric, longest first, scaled to the
    largest. Operational, not a score: the label says so where the metric
    is named, since a ranked bar reads as one."""
    m = METRICS[metric % len(METRICS)]
    top = [status_line(f"Compare · {m.title}", st, width),
           [(fit(f"{m.title}: operational, not a score", width), DIM)]]
    rows = [(a, *metric_value(a, m)) for a in agents]
    # Unknown values last, in the board's order; known ones largest first.
    known = sorted((r for r in rows if r[1] is not None), key=lambda r: -r[1])
    rows = known + [r for r in rows if r[1] is None]
    name_w = max([5] + [cells(clean(a.login)) for a in agents])
    text_w = max([4] + [cells(t) for _, _, t, _ in rows])
    bar_w = max(1, width - name_w - text_w - 4)
    peak = max((r[1] for r in known), default=0.0)
    glyph = BAR_ASCII if ascii_only else BAR
    body: list[Line] = []
    for a, v, text, style in rows:
        if v is None:
            bar = ""
        elif peak <= 0:
            bar = ""
        else:
            # A non-zero value is never drawn as no bar at all.
            n = max(1, round(v / peak * bar_w)) if v > 0 else 0
            bar = glyph * n
        body.append([(pad(a.login, name_w, False) + "  ", BOLD), (pad(text, text_w, True) + "  ", style),
                     (bar, NORMAL if style != FAILED else FAILED)])
    if not agents:
        body = [[("  no placed agents in the hosts registry", DIM)]]
    whys = section_problems(agents, m.section, st.now)
    unknown = [a for a, v, text, _ in rows
               if v is None and text == NOT_READ and ok_data(a.sections.get(m.section)) is not None]
    if unknown:
        # The section answered, but without this metric's number: say
        # whose and why, rather than a bare `?`.
        whys.insert(0, f"? {m.title} not in the answer for {len(unknown)} agent(s): {MISSING.get(m.key, 'no value')}")
    # A why is wrapped, never cut: its point is often at its end.
    footer = [[(part, FAILED if why.startswith("?") else WARN)]
              for why in whys for part in wrap_cells(clean(why), width, indent="  ")[:3]]
    footer += [[(fit(metric_tabs(metric, width), width), DIM)], [(fit(COMPARE_KEYS, width), DIM)]]
    return framed(top, body, footer, scroll, width, height)


def metric_tabs(metric: int, width: int) -> str:
    """Every metric, the chosen one bracketed: in words, so the choice
    reads without colour. Where they do not fit, only the chosen one and
    its place, so the choice is never what gets cut."""
    i = metric % len(METRICS)
    full = metric_list(i)
    return full if cells(full) <= width else f"[{i + 1} of {len(METRICS)}: {METRICS[i].title}]"


def metric_list(metric: int) -> str:
    return "  ".join(f"[{i + 1} {m.title}]" if i == metric else f"{i + 1} {m.title}"
                     for i, m in enumerate(METRICS))


def section_problems(agents: list[Agent], section: str, now: datetime.datetime) -> list[str]:
    """Why some bars are missing (`?`) and why some are marked stale (`~`),
    each said once: both can hold at once, for different agents."""
    out = []
    whys = [r.get("why") or "no answer" for a in agents
            if isinstance(r := a.sections.get(section), dict) and ok_data(r) is None]
    if whys:
        who = "all agents" if len(whys) == len(agents) else f"{len(whys)} agent(s)"
        out.append(f"? {section} not read for {who}: {whys[0]}")
    olds = [a for a in agents if stale(a.sections.get(section))]
    if olds:
        out.append(stale_text(section, olds, agents, now))
    return out


def framed(top: list[Line], body: list[Line], footer: list[Line], scroll: int, width: int,
           height: int) -> tuple[list[Line], int]:
    room = max(1, height - len(top) - len(footer))
    scroll = max(0, min(scroll, len(body) - room))
    shown = body[scroll: scroll + room]
    shown += [[("", NORMAL)]] * (room - len(shown))
    return [clip(line, width) for line in (top + shown + footer)][:height], scroll


# ── plans ───────────────────────────────────────────────────────────

# The board's lanes, in the order work moves; each lane holds the step
# states named beside it. A state no lane names goes to "other", shown.
LANES = (
    ("to do", ("planned", "waiting")),
    ("queued", ("queued",)),
    ("doing", ("active", "blocked")),
    ("delivered", ("delivered",)),
    ("done", ("done", "dropped")),
)
OTHER_LANE = "other"
# A step with no time from its job is drawn this long unless the plan says.
DEFAULT_EST_DAYS = 1.0
GANTT_LABEL_MAX = 34


def lane_of(state: str) -> str:
    for name, states in LANES:
        if state in states:
            return name
    return OTHER_LANE


def steps_of(plan: dict) -> list[dict]:
    steps = plan.get("steps")
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def text_of(value, default: str = NONE) -> str:
    return value if isinstance(value, str) and value else default


def plan_lines(record: dict | None, st: Status, scroll: int, width: int, height: int,
               ascii_only: bool = False, keys: str = PLAN_KEYS) -> tuple[list[Line], int]:
    top = [status_line("Plans", st, width)]
    footer = [[(fit(keys, width), DIM)]]
    body: list[Line] = []
    if record is None:
        body.append([(f"  {UNREAD} not read yet", DIM)])
    elif ok_data(record) is None:
        why = clean(f"not read: {record.get('why') or 'no answer'}")
        body += [[("  " + part, FAILED)] for part in wrap_cells(why, max(10, width - 4), indent="  ")]
    else:
        if stale(record):
            body.append([(fit(f"  stale: {record.get('why') or 'the last read failed'}", width), WARN)])
        plans = [p for p in (ok_data(record).get("plans") or []) if isinstance(p, dict)]
        if not plans:
            # fabric-plan reads the plan files of the login it runs as: on
            # any but the coordinator's, none is the answer, not a fault.
            whose = ok_data(record).get("login")
            body.append([(fit(f"  no plans kept by {whose}" if isinstance(whose, str) and whose else "  no plans", width), DIM)])
        for plan in plans:
            body += plan_body(plan, st.now, width, ascii_only)
            body.append([("", NORMAL)])
    return framed(top, body, footer, scroll, width, height)


def plan_body(plan: dict, now: datetime.datetime, width: int, ascii_only: bool) -> list[Line]:
    steps = steps_of(plan)
    done = sum(1 for s in steps if s.get("state") == "done")
    head = f"{text_of(plan.get('id'), '?')}  {text_of(plan.get('title'), '')}"
    out: list[Line] = [[(fit(head, width), BOLD)],
                       [(fit(f"  {text_of(plan.get('status'))} · {done} of {len(steps)} steps done", width), DIM)]]
    out += board(steps, width)
    out.append([("", NORMAL)])
    out += gantt(steps, now, width, ascii_only)
    return out


def card(step: dict) -> tuple[str, str]:
    state = text_of(step.get("state"), "unknown")
    lane = lane_of(state)
    # The lane says most of the state; the card says what the lane does not.
    mark = "" if state in (lane, "planned", "queued", "active", "delivered", "done") else f"{state}: "
    style = WARN if state in ("blocked", "unknown") else DIM if state == "dropped" else NORMAL
    return f"{text_of(step.get('id'), '?')} {mark}{text_of(step.get('title'), '')} · {text_of(step.get('owner'))}", style


def board(steps: list[dict], width: int) -> list[Line]:
    """The steps by state: lanes side by side where they fit, one lane per
    line block where they do not. An empty lane is drawn, so the board
    keeps its shape from plan to plan."""
    lanes = [(name, [s for s in steps if lane_of(text_of(s.get("state"), "unknown")) == name]) for name, _ in LANES]
    other = [s for s in steps if lane_of(text_of(s.get("state"), "unknown")) == OTHER_LANE]
    if other:
        lanes.append((OTHER_LANE, other))
    col = (width - 2 - (len(lanes) - 1)) // len(lanes)
    if col >= 12:
        out: list[Line] = [[("  " + " ".join(pad(f"{name} ({len(ss)})", col, False) for name, ss in lanes), BOLD)]]
        for i in range(max(len(ss) for _, ss in lanes)):
            line: Line = [("  ", NORMAL)]
            for j, (_, ss) in enumerate(lanes):
                text, style = card(ss[i]) if i < len(ss) else ("", NORMAL)
                line.append(((" " if j else "") + pad(text, col, False), style))
            out.append(line)
        return out
    out = []
    for name, ss in lanes:
        out.append([(fit(f"  {name} ({len(ss)})", width), BOLD)])
        for s in ss:
            text, style = card(s)
            out.append([(fit(f"    {text}", width), style)])
    return out


@dataclass(frozen=True)
class Span:
    start: datetime.datetime
    end: datetime.datetime
    estimated: bool


def spans(steps: list[dict], now: datetime.datetime) -> dict[str, Span]:
    """When each step ran, from its job's log, or, without that, an estimate:
    after the steps it waits for (or now, whichever is later), for its
    est_days. A step that started and has not finished runs to now."""
    by_id = {text_of(s.get("id"), f"#{i}"): s for i, s in enumerate(steps)}
    out: dict[str, Span] = {}

    def one(sid: str, seen: frozenset[str]) -> Span:
        if sid in out:
            return out[sid]
        s = by_id[sid]
        started, finished = parse_utc(s.get("started")), parse_utc(s.get("finished"))
        est = _num(s.get("est_days"))
        length = datetime.timedelta(days=est if est and est > 0 else DEFAULT_EST_DAYS)
        if started is not None:
            span = Span(started, max(finished or now, started), False)
        else:
            after = [one(d, seen | {sid}).end for d in (s.get("depends_on") or [])
                     if isinstance(d, str) and d in by_id and d not in seen and d != sid]
            begin = max([now] + after) if finished is None else finished - length
            span = Span(begin, begin + length if finished is None else finished, True)
        out[sid] = span
        return span

    for sid in by_id:
        one(sid, frozenset())
    return out


def gantt(steps: list[dict], now: datetime.datetime, width: int, ascii_only: bool) -> list[Line]:
    """One row per step: its label (id, owner, title, what it waits for),
    then its bar on a time axis shared by the plan, with a now-line. A
    bar from the job's times is solid; an estimate is hollow and says
    `est`, since its place is a guess."""
    if not steps:
        return [[("  no steps", DIM)]]
    ids = [text_of(s.get("id"), f"#{i}") for i, s in enumerate(steps)]
    sp = spans(steps, now)
    lo = min([now] + [x.start for x in sp.values()])
    hi = max([now] + [x.end for x in sp.values()])
    label_w = min(GANTT_LABEL_MAX, max(12, width // 3))
    axis_w = max(4, width - label_w - 2 - 4)   # room for " est"
    total = max((hi - lo).total_seconds(), 1.0)

    def x(t: datetime.datetime) -> int:
        return min(axis_w - 1, max(0, int((t - lo).total_seconds() / total * (axis_w - 1))))

    solid, hollow = (BAR_ASCII, HOLLOW_ASCII) if ascii_only else (BAR, HOLLOW)
    now_mark = NOW_MARK_ASCII if ascii_only else NOW_MARK
    now_x = x(now)
    out: list[Line] = [[(pad("step · owner", label_w, False) + "  ", BOLD),
                        (axis_line(lo, hi, now, axis_w, now_x), DIM)]]
    for sid, s in zip(ids, steps):
        span = sp[sid]
        a, b = x(span.start), x(span.end)
        row = [" "] * axis_w
        for i in range(a, max(a, b) + 1):
            row[i] = hollow if span.estimated else solid
        if row[now_x] == " ":
            row[now_x] = now_mark
        deps = [d for d in (s.get("depends_on") or []) if isinstance(d, str)]
        label = f"{sid} {text_of(s.get('owner'))} {text_of(s.get('title'), '')}"
        if deps:
            label += f" ⇠{','.join(deps)}" if not ascii_only else f" <-{','.join(deps)}"
        state = text_of(s.get("state"), "unknown")
        style = WARN if state in ("blocked", "unknown") else DIM if span.estimated or state == "dropped" else NORMAL
        out.append([(pad(label, label_w, False) + "  ", NORMAL), ("".join(row), style),
                    (" est" if span.estimated else "", DIM)])
    out.append([(fit(f"  {now_mark} now {clock(now.isoformat(), now)} · solid: from the job's log · "
                     f"{hollow} est: no time recorded, drawn after what it waits for", width), DIM)])
    return out


def axis_line(lo: datetime.datetime, hi: datetime.datetime, now: datetime.datetime, width: int, now_x: int) -> str:
    left, right = clock(lo.isoformat(), now), clock(hi.isoformat(), now)
    gap = width - cells(left) - cells(right)
    return left + " " * max(1, gap) + right if gap >= 1 else left


# ── pull requests ───────────────────────────────────────────────────

def verdict_style(verdict: str) -> str:
    if verdict.startswith("BLOCKED") or "held" in verdict:
        return WARN
    if verdict.startswith("MERGEABLE"):
        return BOLD
    return NORMAL


def pr_rows(data: dict | None) -> list[dict]:
    rows = (data or {}).get("prs")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def pr_entry(p: dict, width: int) -> list[Line]:
    num = pr_number(p.get("number", p.get("pr")))
    label = f"#{num}" if num else "no PR"
    repo = text_of(p.get("repo"), "")
    title = text_of(p.get("title"), text_of(p.get("branch"), ""))
    first = f"    {label}  {repo + '  ' if repo else ''}{title}"
    out: list[Line] = [[(fit(first, width), NORMAL)]]
    facts = []
    if isinstance(p.get("work_commits"), int):
        facts.append(f"{p['work_commits']} work, {p.get('fix_commits') or 0} fix")
    elif isinstance(p.get("ahead"), int):
        facts.append(f"{p['ahead']} ahead")
    for key, name in (("checks", "checks"), ("review", "review"), ("armed", "armed")):
        if isinstance(p.get(key), str) and p[key]:
            facts.append(f"{name} {p[key]}")
    if p.get("draft") is True:
        facts.append("draft")
    if facts:
        out.append([(fit("      " + " · ".join(facts), width), DIM)])
    verdict = p.get("verdict")
    if isinstance(verdict, str) and verdict:
        out.append([(fit(f"      {verdict}", width), verdict_style(verdict))])
    elif num:
        out.append([(fit("      no gate verdict", width), DIM)])
    return out


def split_prs(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(pull requests, pushed branches without one): pr-gate's in-flight
    rows are both, and a branch is work in flight, not a PR at a gate."""
    prs = [r for r in rows if pr_number(r.get("number", r.get("pr")))]
    return prs, [r for r in rows if not pr_number(r.get("number", r.get("pr")))]


def pr_count(n: int) -> str:
    return "no PR" if n == 0 else f"{n} PR{'s' if n > 1 else ''}"


def bare_line(bare: list[dict], width: int) -> list[Line]:
    if not bare:
        return []
    n = len(bare)
    return [[(fit(f"    + {n} pushed branch{'es' if n > 1 else ''} without a PR", width), DIM)]]


def stale_caveat(rec: dict | None, now: datetime.datetime) -> str:
    if not stale(rec):
        return ""
    return f"  {STALE} stale, read {age(rec.get('at'), now)}: {rec.get('why') or 'the last read failed'}"


def pr_caveat(data: dict) -> str:
    if data.get("prs_ok") is False or data.get("fetch_ok") is False:
        return "  (as of the last fetch: GitHub or origin did not answer)"
    if data.get("gate_ok") is False:
        return f"  (gate not read: {text_of(data.get('gate_why'), 'no answer')})"
    return ""


def prs_lines(agents: list[Agent], unplaced: dict | None, st: Status, scroll: int, width: int,
              height: int, keys: str = PRS_KEYS) -> tuple[list[Line], int]:
    """In-flight pull requests by owner, each with the gate's verdict. An
    agent with none is left out; one whose PRs were not read is said."""
    body: list[Line] = []
    shown = 0
    unread = [a.login for a in agents if a.sections.get("prs") is None]
    for a in agents:
        rec = a.sections.get("prs")
        if rec is None:
            continue
        data = ok_data(rec)
        if data is None:
            body.append([(fit(f"  {a.login}: not read: {rec.get('why') or 'no answer'}", width), FAILED)])
            continue
        prs, bare = split_prs(pr_rows(data))
        if not prs and not bare:
            continue
        shown += len(prs)
        mark = stale_caveat(rec, st.now) or pr_caveat(data)
        body.append([(a.login, BOLD), (f" · {pr_count(len(prs))}{mark}", WARN if mark else DIM)])
        for p in prs:
            body += pr_entry(p, width)
        body += bare_line(bare, width)
    others, others_bare = split_prs(pr_rows(ok_data(unplaced)))
    if failed(unplaced):
        body.append([(fit(f"  not a placed agent's: not read: {unplaced.get('why') or 'no answer'}", width), FAILED)])
    elif others or others_bare:
        shown += len(others)
        mark = stale_caveat(unplaced, st.now) or pr_caveat(ok_data(unplaced) or {})
        body.append([("not a placed agent's", BOLD), (f" · {pr_count(len(others))}{mark}", WARN if mark else DIM)])
        for p in others:
            body += [[(fit(f"    {text_of(p.get('owner'), '?')}", width), DIM)]] + pr_entry(p, width)
        body += bare_line(others_bare, width)
    if unread:
        body.append([(fit(f"  {UNREAD} not read yet for {len(unread)} agent(s)", width), DIM)])
    if not body:
        body = [[("  no pull requests in flight", DIM)]]
    # fleet.py reads the gate in agent-fabric's checkout only; each row's
    # repo says so too, but the scope belongs where the count is.
    top = [status_line(f"Pull requests in flight · {shown}", st, width),
           [(fit("agent-fabric only: other repositories are not read", width), DIM)]]
    return framed(top, body, [[(fit(keys, width), DIM)]], scroll, width, height)
