"""view_render: the board and the agent view on fixture records.

The records have fleet.py's shape. proc, states and presence are copied
from a live `fabric-fleet --json` on develop-qzapp (2026-10-09). jobs,
closed_jobs, prs, usage, host and tokens follow the ops' code in
agent-fabric (runtime/control/jobs.mjs, ops/usage.mjs, ops/host.mjs,
pressure.mjs; tools/fabric/fleet.py's prs_read and closed_jobs_read),
because they answer only a host operator and were not read live.
"""

import datetime
import unittest

import view_render as vr

NOW = datetime.datetime(2026, 10, 9, 11, 5, 0, tzinfo=datetime.timezone.utc)


def ok(src, at, data):
    return {"status": "ok", "src": src, "at": at, "data": data}


def bad(src, why):
    return {"status": "failed", "src": src, "at": "2026-10-09T11:00:30Z", "why": why}


PROC = ok("proc-local", "2026-10-09T11:00:19Z", {"uid": 1001, "cpu_pct": 1.6, "rss_kb": 531684, "swap_kb": 244696, "procs": 18})
STATES = ok("op:states", "2026-10-09T11:00:22Z", {
    "ts": "2026-10-09T11:00:06.652Z", "role": "architect-cto", "project": "gzapp",
    "sessions": [{"session": "9c3ad185-b9c3-4607-9d12-f8ac78d0897e", "state": "idle", "since": "2026-10-09T11:00:06Z"}],
    "state": "idle", "since": "2026-10-09T11:00:06Z", "last_session": "9c3ad185-b9c3-4607-9d12-f8ac78d0897e", "resumable": True})
PRESENCE = ok("op:presence", "2026-10-09T11:00:24Z", {"presence": {
    "status": "ok", "online": True, "sessions": 1, "since": "2026-10-08T06:28:26.190Z",
    "role": "architect-cto", "project": "gzapp", "planning": False}})
JOBS = ok("op:jobs", "2026-10-09T11:00:25Z", {"jobs": {"status": "ok", "jobs": [
    {"id": "j34", "state": "blocked", "title": "Fleet Deck: one tab per agent", "project": "herdr", "topic": "herdr",
     "priority": "normal", "source": "owner", "blocked_on": "agent-fabric activation PR", "artifacts": [], "updated": "2026-10-08T17:00:00Z"},
    {"id": "j40", "state": "active", "title": "Fleet Deck R1: fabric-view board and agent overlay as a herdr plugin",
     "project": "herdr", "topic": "fleet-deck", "priority": "normal", "source": "owner", "blocked_on": None,
     "artifacts": [], "updated": "2026-10-09T10:57:46Z"},
    {"id": "j42", "state": "queued", "title": "labels", "project": "interweave", "topic": None,
     "priority": "normal", "source": "self", "blocked_on": None, "artifacts": [], "updated": "2026-10-09T09:00:00Z"}]}})
CLOSED = ok("hostexec", "2026-10-09T11:00:40Z", {"closed_total": 23, "closed": [
    {"id": "j39", "title": "sync upstream", "state": "done", "topic": "herdr", "project": "herdr", "updated": "2026-10-09T09:28:00Z"},
    {"id": "j38", "title": "duplicate sync", "state": "dropped", "topic": "herdr", "project": "herdr", "updated": "2026-10-09T07:22:00Z"}]})
PRS = ok("pr-gate", "2026-10-09T11:01:00Z", {"prs": [
    {"pr": 9, "branch": "develop-qzapp/rust-ui-dev-01/feat/fleet-views", "ahead": 4, "last_commit": "2026-10-09T11:00:00Z", "paths_total": 6},
    {"pr": "none", "branch": "develop-qzapp/rust-ui-dev-01/fix/other", "ahead": 1, "last_commit": None, "paths_total": 1}],
    "fetch_ok": True, "prs_ok": True, "base": "origin/master"})
USAGE = ok("op:usage", "2026-10-09T11:00:26Z", {"usage_status": "ok",
    "five_hour": {"utilization": 37.0, "resets_at": "2026-10-09T13:00:00Z"},
    "seven_day": {"utilization": 12.4, "resets_at": "2026-10-14T00:00:00Z"}})
HOST = ok("op:host", "2026-10-09T11:00:27Z", {"machine": {
    "status": "ok", "cpus": 8, "loadavg": [1.2, 1.0, 0.9],
    "mem_mb": {"total": 32000, "available": 12000, "swap_total": 8192, "swap_free": 6144},
    "balloon_mb": None, "disk": [], "leases": [], "top_rss": [],
    "memory_pressure": {"status": "ok", "interval_s": 60, "samples": 30, "since": "2026-10-09T10:30:00Z",
                        "last": [{"ts": "2026-10-09T11:00:00Z", "some_avg10": 0.42, "full_avg10": 0.0, "mem_available_mb": 12000}],
                        "hour": {"samples": 30, "some_avg10": None, "full_avg10": None, "mem_available_mb": None}}}})
TOKENS = ok("op:tokens", "2026-10-09T10:58:00Z", {"email": None, "role": "architect-cto", "tokens": {
    "status": "ok", "days": 7, "files": 40, "requests": {"session": 900, "subagent": 300},
    "first": "2026-10-02T08:00:00Z", "last": "2026-10-09T10:57:00Z",
    "models": {"claude-opus-5-5": {"requests": 1000, "input": 1_000_000, "cache_write": 2_000_000, "cache_read": 40_000_000,
                                   "output": 500_000, "equiv": 9_000_000, "path": "claude"},
               "deepseek/v4-pro": {"requests": 200, "input": 100_000, "cache_write": 0, "cache_read": 0, "output": 50_000,
                                   "equiv": 350_000, "path": "broker"}},
    "claude": {"requests": 1000, "input": 1_000_000, "cache_write": 2_000_000, "cache_read": 40_000_000, "output": 500_000, "equiv": 9_000_000},
    "broker": {"requests": 200, "input": 100_000, "cache_write": 0, "cache_read": 0, "output": 50_000, "equiv": 350_000},
    "ratios": {"input": 1, "cache_write": 1.25, "cache_read": 0.1, "output": 5}}})

FULL = {"states": STATES, "presence": PRESENCE, "proc": PROC, "jobs": JOBS, "closed_jobs": CLOSED,
        "prs": PRS, "usage": USAGE, "host": HOST, "tokens": TOKENS}
NOT_OPERATOR = "op:jobs: fabric-ctl jobs: fabric-ctl: develop-qzapp/rust-ui-dev-01 is not a host operator"


def fleet():
    alpha = vr.Agent("architect-cto-01", "develop-qzapp", "agent", dict(FULL))
    beta = vr.Agent("web-dev-02", "develop-qzapp", "agent", {
        "states": ok("op:states", "2026-10-09T11:00:22Z", {"sessions": [], "state": None}),
        "proc": PROC, "jobs": bad("op:jobs", NOT_OPERATOR), "closed_jobs": None,
        "prs": ok("pr-gate", "2026-10-09T11:01:00Z", {"prs": [], "fetch_ok": True, "prs_ok": True, "base": "origin/main"}),
        "usage": ok("op:usage", "2026-10-09T11:00:26Z", {"usage_status": "no-credentials"}),
        "host": None, "tokens": ok("op:tokens", "2026-10-09T10:58:00Z", {"tokens": {"status": "no-records", "days": 7}})})
    return [alpha, beta]


def status(**kw):
    base = dict(focused=True, fetching=(), now=NOW, oldest="2026-10-09T11:00:19Z", from_cache=False)
    base.update(kw)
    return vr.Status(**base)


def texts(lines):
    return [vr.line_text(line) for line in lines]


class Board(unittest.TestCase):
    def test_a_row_says_each_column_from_its_record(self):
        lines = texts(vr.board_lines(fleet(), {}, status(), 0, 140, 20))
        row = next(t for t in lines if "architect-cto-01" in t)
        for word in ("idle", "j40 Fleet Deck R1", "23/3", "519M", "2%", "43.6M", "37%", "#9 +1"):
            self.assertIn(word, row)
        self.assertTrue(row.startswith("> "), "the selected row is marked in text, not only in colour")

    def test_a_blocked_job_is_the_current_one_only_without_an_active_one(self):
        jobs = vr.open_jobs(JOBS["data"])
        self.assertEqual(vr.current_job(jobs)["id"], "j40")
        self.assertEqual(vr.job_label(vr.current_job([j for j in jobs if j["id"] != "j40"])),
                         "j34 (blocked) Fleet Deck: one tab per agent")

    def test_failed_unread_and_absent_cells_say_which_they_are(self):
        cells = vr.board_cells(fleet()[1])
        self.assertEqual(cells["job"], (vr.NOT_READ, vr.FAILED))
        self.assertEqual(cells["jobs"], (f"{vr.UNREAD}/{vr.NOT_READ}", vr.FAILED))
        self.assertEqual(cells["state"][0], "no session")
        self.assertEqual(cells["five_hour"][0], "n/a")
        self.assertEqual(cells["tokens"][0], "0")
        self.assertEqual(cells["pr"][0], vr.NONE)

    def test_a_failed_section_is_said_once_in_the_footer_with_its_why(self):
        lines = texts(vr.board_lines(fleet(), {}, status(), 0, 140, 20))
        said = [t for t in lines if t.startswith("? jobs")]
        self.assertEqual(len(said), 1)
        self.assertIn("1 agent", said[0])
        self.assertIn("not a host operator", said[0])

    def test_host_memory_and_pressure_in_the_footer(self):
        lines = texts(vr.board_lines(fleet(), {"develop-qzapp": HOST}, status(), 0, 140, 20))
        self.assertIn("develop-qzapp: memory 19.5 of 31.2 GB used swap 2.0 GB pressure some 0.4% full 0.0%", lines)

    def test_narrow_drops_the_least_needed_columns_and_keeps_agent_state_job(self):
        for width in (60, 48):
            cols = [c.key for c, _ in vr.board_columns(fleet(), width)]
            self.assertEqual(cols[:3], ["login", "state", "job"])
            for line in texts(vr.board_lines(fleet(), {}, status(), 0, width, 20)):
                self.assertLessEqual(len(line), width)
        self.assertNotIn("tokens", [c.key for c, _ in vr.board_columns(fleet(), 60)])
        self.assertEqual(len(vr.board_columns(fleet(), 200)), len(vr.BOARD_COLUMNS))

    def test_a_branch_without_a_pr_is_never_a_pr_number(self):
        self.assertEqual(vr.pr_label({"prs": [{"pr": "none"}]}), "no PR")
        self.assertEqual(vr.pr_label({"prs": [{"pr": "12"}, {"pr": None}]}), "#12 +1")
        body = texts(vr.agent_body(fleet()[0], vr.Samples(), NOW, 100))
        self.assertIn("  no PR  develop-qzapp/rust-ui-dev-01/fix/other  1 ahead", body)

    def test_a_wide_window_keeps_the_numbers_near_the_name(self):
        widths = dict((c.key, w) for c, w in vr.board_columns(fleet(), 300))
        self.assertEqual(widths["job"], vr.JOB_MAX)

    def test_the_selected_row_is_reversed_whole(self):
        row = vr.board_row(fleet()[1], vr.board_columns(fleet(), 140), True)
        self.assertEqual({style for _, style in row}, {vr.SELECTED})
        self.assertIn(vr.NOT_READ, vr.line_text(row))

    def test_a_long_title_is_cut_with_a_mark(self):
        row = texts(vr.board_lines(fleet(), {}, status(), 0, 70, 20))[2]
        self.assertIn("…", row)
        self.assertLessEqual(len(row), 70)

    def test_the_selection_stays_in_view_when_rows_overflow(self):
        many = [vr.Agent(f"agent-{i:02}", "h", "agent", {}) for i in range(40)]
        lines = texts(vr.board_lines(many, {}, status(), 35, 100, 12))
        self.assertEqual(len(lines), 12)
        self.assertTrue(any(t.startswith("> agent-35") for t in lines))

    def test_the_status_line_says_live_paused_cached_and_reading(self):
        self.assertIn("live", texts([vr.status_line("Fleet", status(), 100)])[0])
        paused = texts([vr.status_line("Fleet", status(focused=False), 100)])[0]
        self.assertIn("paused: not focused", paused)
        unknown = texts([vr.status_line("Fleet", status(focused=None), 100)])[0]
        self.assertIn("paused: press a key to go live", unknown)
        cached = texts([vr.status_line("Fleet", status(from_cache=True, fetching=("jobs", "prs")), 100)])[0]
        self.assertIn("from cache, 4 min ago", cached)
        self.assertIn("reading jobs, prs", cached)

    def test_unread_cells_before_any_answer(self):
        bare = vr.Agent("x", "h", "agent", {})
        self.assertTrue(all(t == vr.UNREAD for k, (t, _) in vr.board_cells(bare).items() if k not in ("login", "jobs")))


class AgentView(unittest.TestCase):
    def body(self, agent, samples=None, width=100):
        return texts(vr.agent_body(agent, samples or vr.Samples(), NOW, width))

    def test_every_section_with_its_source_and_age(self):
        body = self.body(fleet()[0])
        for heading in ("Session  op:states, 4 min ago", "Resources  proc-local, 4 min ago", "Open jobs (3)  op:jobs",
                        "Closed jobs (23)  hostexec", "Pull requests  pr-gate", "Tokens, 7 days  op:tokens, 7 min ago",
                        "Usage windows  op:usage"):
            self.assertTrue(any(t.startswith(heading) for t in body), heading)

    def test_session_state_and_what_it_waits_on(self):
        body = self.body(fleet()[0])
        self.assertIn("  state idle since 11:00Z", body)
        self.assertIn("  session 9c3ad185 · resumable", body)
        self.assertIn("  waits on agent-fabric activation PR (j34)", body)
        self.assertIn("  online · 1 session(s)", body)

    def test_jobs_with_their_times(self):
        body = self.body(fleet()[0])
        self.assertTrue(any(t.startswith("  j40   active    10:57Z  Fleet Deck R1") for t in body))
        self.assertTrue(any(t.startswith("  j34   blocked   Oct 08  Fleet Deck") for t in body))
        self.assertIn("  and 21 older", body)

    def test_tokens_usage_and_prs(self):
        body = self.body(fleet()[0])
        self.assertIn("  43.6M tokens in 1.2k requests", body)
        self.assertIn("    43.5M  claude-opus-5-5", body)
        self.assertIn("  5 hours   37%  resets 13:00Z", body)
        self.assertIn("  7 days    12%  resets Oct 14", body)
        self.assertIn("  #9  develop-qzapp/rust-ui-dev-01/feat/fleet-views  4 ahead", body)

    def test_a_failed_section_says_why_in_place(self):
        body = self.body(fleet()[1])
        i = next(i for i, t in enumerate(body) if t.startswith("Open jobs"))
        self.assertIn("is not a host operator", " ".join(" ".join(body[i + 1: i + 3]).split()))
        self.assertTrue(all(len(t) <= 60 for t in self.body(fleet()[1], width=60)))
        self.assertIn("  no-credentials", body)
        self.assertIn("  no requests recorded", body)

    def test_sparklines_from_distinct_samples_only(self):
        s = vr.Samples()
        for at, rss, cpu in (("t1", 100, 1.0), ("t1", 100, 1.0), ("t2", 200, 5.0), ("t3", 150, 3.0)):
            s.add(ok("proc-local", at, {"rss_kb": rss, "cpu_pct": cpu}))
        self.assertEqual(s.at, ["t1", "t2", "t3"])
        self.assertEqual(vr.sparkline(s.rss_kb, 10), "▁█▅")
        self.assertEqual(vr.sparkline([3, 3, 3], 10), "▁▁▁")
        self.assertEqual(vr.sparkline(s.cpu_pct, 10, ascii_only=True), "_@+")

    def test_scroll_is_clamped_to_the_body(self):
        a = fleet()[0]
        lines, scroll = vr.agent_lines(a, vr.Samples(), status(), 999, 100, 10)
        self.assertEqual(len(lines), 10)
        self.assertEqual(scroll, len(vr.agent_body(a, vr.Samples(), NOW, 100)) - 7)
        self.assertTrue(texts(lines)[0].startswith("architect-cto-01 · live · "))
        self.assertEqual(texts(lines)[1], "architect-cto · gzapp · develop-qzapp")
        self.assertEqual(texts(lines)[-1], vr.AGENT_KEYS)

    def test_every_line_fits_a_narrow_overlay(self):
        for t in texts(vr.agent_lines(fleet()[0], vr.Samples(), status(), 0, 40, 60)[0]):
            self.assertLessEqual(len(t), 40)


class OtherAccountsText(unittest.TestCase):
    """Titles, branches and whys come from other accounts (the threat
    model): none may move the cursor or overflow its line."""

    def hostile(self):
        a = fleet()[0]
        jobs = [dict(j) for j in vr.open_jobs(JOBS["data"])]
        jobs[1]["title"] = "J1 fix\rFORGED\bx\nnext\x9bline"
        jobs[0]["title"] = "漢" * 60
        a.sections["jobs"] = ok("op:jobs", JOBS["at"], {"jobs": {"status": "ok", "jobs": jobs}})
        a.sections["prs"] = ok("pr-gate", PRS["at"], dict(PRS["data"], prs=[{"pr": 9, "branch": "b\r\x1b[31mred", "ahead": 1}]))
        b = fleet()[1]
        b.sections["jobs"] = bad("op:jobs", "refused\rFORGED")
        return [a, b]

    def assert_drawable(self, lines, width):
        for line in lines:
            text = vr.line_text(line)
            self.assertFalse([c for c in text if vr.unicodedata.category(c)[0] == "C"], repr(text))
            self.assertLessEqual(vr.cells(text), width, repr(text))

    def test_the_board_draws_no_control_character_and_fits_in_cells(self):
        for width in (140, 70, 40):
            self.assert_drawable(vr.board_lines(self.hostile(), {}, status(), 0, width, 20), width)
        row = texts(vr.board_lines(self.hostile(), {}, status(), 0, 140, 20))[2]
        self.assertTrue(row.startswith("> architect-cto-01"), row)
        self.assertIn("J1 fix" + vr.CONTROL + "FORGED", row)

    def test_the_agent_view_draws_no_control_character_and_fits_in_cells(self):
        for width in (100, 40):
            a = self.hostile()[0]
            self.assert_drawable(vr.agent_lines(a, vr.Samples(), status(), 0, width, 80)[0], width)
            self.assert_drawable(vr.agent_lines(self.hostile()[1], vr.Samples(), status(), 0, width, 80)[0], width)

    def test_wide_characters_are_measured_in_cells(self):
        self.assertEqual(vr.cells("漢字ab"), 6)
        self.assertEqual(vr.cells(vr.fit("漢" * 30, 40)), 39)
        self.assertEqual(vr.cells(vr.pad("漢字", 6, right=True)), 6)


class WhysOnScreen(unittest.TestCase):
    def test_prs_that_could_not_be_listed_are_said_in_the_footer(self):
        agents = fleet()
        agents[0].sections["prs"] = ok("pr-gate", PRS["at"], dict(PRS["data"], prs_ok=False))
        lines = texts(vr.board_lines(agents, {}, status(), 0, 140, 20))
        self.assertTrue(any(t.startswith("? prs not read for 1 agent: pr-gate could not list") for t in lines))

    def test_sections_past_the_footer_are_named_with_where_their_why_is(self):
        agents = fleet()
        for name in ("jobs", "usage", "host", "tokens"):
            for a in agents:
                a.sections[name] = bad(f"op:{name}", f"{name} refused")
        lines = texts(vr.failure_lines(agents, vr.BOARD_SECTIONS, 140, limit=3))
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[-1], "? also not read: host, tokens; why in each agent's view (Enter)")


class Values(unittest.TestCase):
    def test_clock_and_age(self):
        self.assertEqual(vr.clock("2026-10-09T10:57:46Z", NOW), "10:57Z")
        self.assertEqual(vr.clock("2026-10-08T10:57:46Z", NOW), "Oct 08")
        self.assertEqual(vr.clock(None, NOW), vr.NONE)
        self.assertEqual(vr.age("2026-10-09T11:04:30Z", NOW), "30 s ago")
        self.assertEqual(vr.age("2026-10-07T11:04:30Z", NOW), "2 d ago")
        self.assertEqual(vr.age(None, NOW), "never")

    def test_sizes_and_counts(self):
        self.assertEqual(vr.size_kb(531684), "519M")
        self.assertEqual(vr.size_kb(3 * 1024 * 1024), "3.0G")
        self.assertEqual(vr.count(43_650_000), "43.6M")
        self.assertEqual(vr.count(999), "999")


if __name__ == "__main__":
    unittest.main()
