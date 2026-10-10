"""report_render: the compare view, the plan view and the PRs popup on
fixture records.

The record shapes are fleet.py's on python-dev-03's
feat/fleet-deck-data (3b386162), read live on develop-qzapp on
2026-10-09: plans as one fleet-wide record, the PR rows with fabric-pr
gate's fields, prs_unplaced as a record, done_total beside closed_total,
and `stale` records carrying their last good data.
"""

import datetime
import unittest

import report_render as rr
import view_render as vr
from test_view_render import CLOSED, JOBS, NOW, TOKENS, bad, ok


def status(**kw):
    return vr.Status(**{"focused": True, "fetching": (), "now": NOW, "oldest": "2026-10-09T11:00:19Z",
                        "from_cache": False, **kw})


def proc(rss, cpu=1.0, swap=0, status="ok"):
    rec = ok("proc-local", "2026-10-09T11:00:19Z", {"rss_kb": rss, "cpu_pct": cpu, "swap_kb": swap, "procs": 3})
    if status == "stale":
        rec = dict(rec, status="stale", age_s=600, why="timeout after 20 s")
    return rec


def text(lines):
    return [vr.line_text(l) for l in lines]


def style_of(lines, needle):
    for line in lines:
        for t, s in line:
            if needle in t:
                return s
    raise AssertionError(f"{needle!r} not drawn")


class Compare(unittest.TestCase):
    def agents(self):
        return [vr.Agent("small", "h", "agent", {"proc": proc(100_000)}),
                vr.Agent("big", "h", "agent", {"proc": proc(4_000_000)}),
                vr.Agent("down", "h", "agent", {"proc": bad("proc-local", "fleet_proc on h: timeout")}),
                vr.Agent("new", "h", "agent", {"proc": None})]

    def test_one_bar_per_agent_largest_first_scaled_to_the_largest(self):
        lines, _ = rr.compare_lines(self.agents(), 0, status(), 0, 80, 14)
        rows = text(lines)
        self.assertIn("operational, not a score", rows[1])
        order = [r.split()[0] for r in rows[2:6]]
        self.assertEqual(order, ["big", "small", "down", "new"])
        big = rows[2].count(rr.BAR)
        small = rows[3].count(rr.BAR)
        self.assertGreater(big, 40)
        self.assertGreaterEqual(small, 1)    # a non-zero value always has a bar
        self.assertLess(small, big)

    def test_an_unread_or_failed_value_has_no_bar_and_says_which(self):
        lines, _ = rr.compare_lines(self.agents(), 0, status(), 0, 80, 14)
        rows = text(lines)
        self.assertNotIn(rr.BAR, rows[4])
        self.assertIn(vr.NOT_READ, rows[4])
        self.assertIn(vr.UNREAD, rows[5])
        self.assertTrue(any("proc not read for 1 agent(s): fleet_proc on h: timeout" in r for r in rows))

    def test_a_stale_value_is_drawn_marked_and_its_why_said(self):
        agents = [vr.Agent("a", "h", "agent", {"proc": proc(2_000_000, status="stale")})]
        lines, _ = rr.compare_lines(agents, 0, status(), 0, 80, 10)
        self.assertEqual(style_of(lines, vr.size_kb(2_000_000)), vr.WARN)
        self.assertTrue(any("stale" in r and "timeout after 20 s" in r for r in text(lines)))

    def test_a_failed_and_a_stale_agent_of_one_section_are_both_said(self):
        agents = [vr.Agent("a", "h", "agent", {"proc": bad("proc-local", "down")}),
                  vr.Agent("b", "h", "agent", {"proc": proc(5000, status="stale")})]
        rows = text(rr.compare_lines(agents, 0, status(), 0, 100, 12)[0])
        self.assertTrue(any(r.startswith("? proc not read for 1 agent(s): down") for r in rows))
        self.assertTrue(any(r.startswith("~ proc stale for b") for r in rows))
        self.assertTrue(any(r.startswith("b ") and "5M~" in r for r in rows))

    def test_every_metric_reads_its_section(self):
        recs = {"proc": proc(2048, cpu=12.5, swap=4096), "tokens": TOKENS, "jobs": JOBS,
                "closed_jobs": ok("hostexec", "2026-10-09T11:00:40Z", dict(CLOSED["data"], done_total=17))}
        a = vr.Agent("a", "h", "agent", recs)
        shown = {m.key: rr.metric_value(a, m)[1] for m in rr.METRICS}
        self.assertEqual(shown["rss"], "2M")
        self.assertEqual(shown["cpu"], "12.5%")
        self.assertEqual(shown["swap"], "4M")
        self.assertEqual(shown["done"], "17")
        self.assertEqual(shown["open"], "3")
        self.assertNotEqual(shown["tokens"], vr.NOT_READ)

    def test_jobs_done_never_counts_dropped_or_guesses_from_a_partial_list(self):
        whole = ok("hostexec", "t", {"closed_total": 2, "closed": [{"state": "done"}, {"state": "dropped"}]})
        self.assertEqual(rr.metric_value(vr.Agent("a", "h", "agent", {"closed_jobs": whole}), rr.METRICS[4])[1], "1")
        lines, _ = rr.compare_lines([vr.Agent("a", "h", "agent", {"closed_jobs": CLOSED})], 4, status(), 0, 60, 12)
        self.assertIn(vr.NOT_READ, text(lines)[2])
        self.assertTrue(any("done_total" in r for r in text(lines)))   # the why, wrapped, not cut

    def test_the_chosen_metric_is_in_words_and_survives_a_narrow_pane(self):
        wide, _ = rr.compare_lines(self.agents(), 3, status(), 0, 120, 14)
        self.assertTrue(any("[4 tokens, 7 days]" in r for r in text(wide)))
        narrow, _ = rr.compare_lines(self.agents(), 5, status(), 0, 30, 14)
        self.assertTrue(any("[6 of 6: open jobs]" in r for r in text(narrow)))
        self.assertTrue(all(vr.cells(r) <= 30 for r in text(narrow)))


PLANS = ok("fabric-plan", "2026-10-09T11:00:00Z", {"login": "user", "plans": [{
    "id": "p3", "title": "Fleet Deck R2", "status": "open", "created_at": "2026-10-09T07:00:00Z", "steps": [
        {"id": "s1", "title": "fleet sections", "owner": "python-dev-03", "depends_on": [], "job": "python-dev-03:j15",
         "state": "done", "reason": None, "started": "2026-10-09T08:00:00Z", "finished": "2026-10-09T10:00:00Z", "est_days": None},
        {"id": "s2", "title": "views", "owner": "rust-ui-dev-01", "depends_on": ["s1"], "job": "rust-ui-dev-01:j46",
         "state": "active", "reason": None, "started": "2026-10-09T09:00:00Z", "finished": None, "est_days": None},
        {"id": "s3", "title": "ssh panes", "owner": "rust-ui-dev-01", "depends_on": ["s2"], "job": None,
         "state": "waiting", "reason": None, "started": None, "finished": None, "est_days": 0.5},
        {"id": "s4", "title": "hunk", "owner": "user", "depends_on": ["s3"], "job": "user:j9",
         "state": "unknown", "reason": "user's job list could not be read", "started": None, "finished": None, "est_days": None}]}]})


class Plans(unittest.TestCase):
    def test_the_board_puts_each_step_in_its_states_lane(self):
        lines, _ = rr.plan_lines(PLANS, status(), 0, 120, 40)
        rows = text(lines)
        header = next(r for r in rows if "to do (" in r)
        for lane in ("to do (1)", "queued (0)", "doing (1)", "delivered (0)", "done (1)", "other (1)"):
            self.assertIn(lane, header)
        self.assertTrue(any("s3 waiting: ssh" in r for r in rows))   # a card is cut to its lane; the Gantt has it whole
        self.assertEqual(style_of(lines, "s4 unknown: hunk"), vr.WARN)

    def test_a_narrow_pane_stacks_the_lanes(self):
        lines, _ = rr.plan_lines(PLANS, status(), 0, 50, 60)
        rows = text(lines)
        self.assertIn("  doing (1)", rows)
        self.assertTrue(all(vr.cells(r) <= 50 for r in rows))

    def test_the_gantt_has_owner_title_dependencies_and_a_now_line(self):
        lines, _ = rr.plan_lines(PLANS, status(), 0, 120, 40)
        rows = text(lines)
        s3 = next(r for r in rows if r.startswith("s3 rust-ui-dev-01 ssh panes"))
        self.assertIn("⇠s2", s3)
        self.assertIn(rr.HOLLOW, s3)
        self.assertTrue(s3.rstrip().endswith("est"))
        s1 = next(r for r in rows if r.startswith("s1 python-dev-03"))
        self.assertIn(rr.BAR, s1)
        self.assertNotIn("est", s1[rr.GANTT_LABEL_MAX:])
        self.assertIn(rr.NOW_MARK, s1)   # s1 ended before now: the now-line crosses its row
        self.assertTrue(any("now 11:05Z" in r for r in rows))

    def test_an_estimate_starts_after_what_it_waits_for(self):
        steps = PLANS["data"]["plans"][0]["steps"]
        sp = rr.spans(steps, NOW)
        self.assertFalse(sp["s1"].estimated)
        self.assertEqual(sp["s2"].end, NOW)              # running: to now
        self.assertEqual(sp["s3"].start, NOW)            # after s2, which runs to now
        self.assertEqual(sp["s3"].end - sp["s3"].start, datetime.timedelta(days=0.5))
        self.assertEqual(sp["s4"].start, sp["s3"].end)
        self.assertEqual(sp["s4"].end - sp["s4"].start, datetime.timedelta(days=rr.DEFAULT_EST_DAYS))

    def test_a_dependency_cycle_ends(self):
        steps = [{"id": "a", "depends_on": ["b"], "state": "planned"}, {"id": "b", "depends_on": ["a"], "state": "planned"}]
        self.assertEqual(set(rr.spans(steps, NOW)), {"a", "b"})

    def test_ascii_draws_the_same_with_plain_characters(self):
        lines, _ = rr.plan_lines(PLANS, status(), 0, 120, 40, ascii_only=True)
        body = "\n".join(text(lines))
        for glyph in (rr.BAR, rr.HOLLOW, rr.NOW_MARK, "⇠"):
            self.assertNotIn(glyph, body)
        self.assertIn("<-s2", body)

    def test_unread_failed_stale_and_empty(self):
        self.assertIn("not read yet", "\n".join(text(rr.plan_lines(None, status(), 0, 80, 10)[0])))
        failed = bad("fabric-plan", "fabric-plan: the plan files cannot be read by this login, which is not the coordinator's")
        rows = text(rr.plan_lines(failed, status(), 0, 40, 12)[0])
        self.assertTrue(any("coordinator's" in r for r in rows))   # wrapped, not cut
        stale = dict(PLANS, status="stale", age_s=900, why="timeout")
        self.assertEqual(style_of(rr.plan_lines(stale, status(), 0, 120, 40)[0], "stale: timeout"), vr.WARN)
        empty = ok("fabric-plan", "t", {"login": "web-dev-01", "plans": []})
        self.assertIn("  no plans kept by web-dev-01", text(rr.plan_lines(empty, status(), 0, 80, 10)[0]))

    def test_scrolling_is_clamped_to_the_body(self):
        _, scroll = rr.plan_lines(PLANS, status(), 999, 120, 10)
        lines, again = rr.plan_lines(PLANS, status(), scroll, 120, 10)
        self.assertEqual(scroll, again)
        self.assertEqual(len(lines), 10)


def gate_row(n, **kw):
    row = {"pr": n, "number": n, "branch": f"develop-qzapp/x/feat/{n}", "ahead": 2, "last_commit": None, "paths_total": 1,
           "repo": "BlueTeam-OU/agent-fabric", "title": f"change {n}", "head": "abc", "work_commits": 3, "fix_commits": 1,
           "checks": "green", "review": "head reviewed", "unresolved_threads": "0", "armed": "no", "queue_position": "",
           "draft": False, "verdict": "MERGEABLE — ask the owner (under 8 work commits, gate met)"}
    row.update(kw)
    return row


def branch_row(name):
    return {"pr": "none", "number": None, "branch": name, "ahead": 1, "repo": "BlueTeam-OU/agent-fabric",
            "title": None, "verdict": None, "work_commits": None}


def prs_rec(rows, **kw):
    return ok("pr-gate", "2026-10-09T11:01:00Z", {"prs": rows, "fetch_ok": True, "prs_ok": True, "base": "origin/main",
                                                    "gate_ok": True, **kw})


class Prs(unittest.TestCase):
    def test_prs_by_owner_with_the_gates_verdict(self):
        agents = [vr.Agent("alice", "h", "agent", {"prs": prs_rec([gate_row(158, verdict="BLOCKED: 1 check(s) pending")])}),
                  vr.Agent("bob", "h", "agent", {"prs": prs_rec([])}),
                  vr.Agent("carol", "h", "agent", {"prs": prs_rec([gate_row(156)])})]
        lines, _ = rr.prs_lines(agents, None, status(), 0, 100, 20)
        rows = text(lines)
        self.assertIn("Pull requests in flight · 2", rows[0])
        self.assertIn("agent-fabric only", rows[1])
        self.assertFalse(any(r.startswith("bob") for r in rows))       # nothing in flight: not listed
        self.assertTrue(any(r.startswith("alice · 1 PR") for r in rows))
        self.assertTrue(any("#158  BlueTeam-OU/agent-fabric  change 158" in r for r in rows))
        self.assertTrue(any("3 work, 1 fix · checks green · review head reviewed · armed no" in r for r in rows))
        self.assertEqual(style_of(lines, "BLOCKED: 1 check"), vr.WARN)
        self.assertEqual(style_of(lines, "MERGEABLE"), vr.BOLD)

    def test_branches_without_a_pr_are_counted_not_listed(self):
        rows_in = [gate_row(9), branch_row("develop-qzapp/a/for/b/x"), branch_row("develop-qzapp/a/for/b/y")]
        lines, _ = rr.prs_lines([vr.Agent("a", "h", "agent", {"prs": prs_rec(rows_in)})], None, status(), 0, 100, 20)
        rows = text(lines)
        self.assertIn("Pull requests in flight · 1", rows[0])
        self.assertTrue(any("+ 2 pushed branches without a PR" in r for r in rows))
        only = prs_rec([branch_row("develop-qzapp/c/feat/z")])
        rows = text(rr.prs_lines([vr.Agent("c", "h", "agent", {"prs": only})], None, status(), 0, 100, 20)[0])
        self.assertIn("c · no PR", rows)
        self.assertFalse(any("for/b/x" in r for r in rows))

    def test_a_gate_or_github_that_did_not_answer_is_said(self):
        no_gate = prs_rec([gate_row(9, verdict=None, work_commits=None, checks=None, review=None, armed=None)],
                          gate_ok=False, gate_why="gh: rate limited")
        no_gh = prs_rec([gate_row(9)], prs_ok=False)
        rows = text(rr.prs_lines([vr.Agent("a", "h", "agent", {"prs": no_gate}),
                                  vr.Agent("b", "h", "agent", {"prs": no_gh})], None, status(), 0, 120, 20)[0])
        self.assertTrue(any("gate not read: gh: rate limited" in r for r in rows))
        self.assertTrue(any("no gate verdict" in r for r in rows))
        self.assertTrue(any("GitHub or origin did not answer" in r for r in rows))

    def test_unplaced_owners_failures_and_unread(self):
        unplaced = prs_rec([gate_row(77, owner="develop-qzapp/gone")])
        agents = [vr.Agent("a", "h", "agent", {"prs": bad("pr-gate", "pr-gate: cannot read the repository")}),
                  vr.Agent("b", "h", "agent", {"prs": None})]
        rows = text(rr.prs_lines(agents, unplaced, status(), 0, 100, 20)[0])
        self.assertTrue(any("a: not read: pr-gate: cannot read the repository" in r for r in rows))
        self.assertTrue(any("not a placed agent's · 1 PR" in r for r in rows))
        self.assertTrue(any("develop-qzapp/gone" in r for r in rows))
        self.assertTrue(any("not read yet for 1 agent(s)" in r for r in rows))
        rows = text(rr.prs_lines([], bad("pr-gate", "down"), status(), 0, 100, 20)[0])
        self.assertTrue(any("not a placed agent's: not read: down" in r for r in rows))

    def test_a_stale_owner_or_unplaced_list_says_since_when_and_why(self):
        old = dict(prs_rec([gate_row(12)]), status="stale", at="2026-10-09T08:05:00Z", age_s=10800, why="pr-gate: timeout")
        rows = text(rr.prs_lines([vr.Agent("a", "h", "agent", {"prs": old})], old, status(), 0, 120, 20)[0])
        self.assertTrue(any(r.startswith("a · 1 PR  ~ stale, read 3 h ago: pr-gate: timeout") for r in rows))
        self.assertTrue(any(r.startswith("not a placed agent's · 1 PR  ~ stale") for r in rows))

    def test_nothing_in_flight(self):
        rows = text(rr.prs_lines([vr.Agent("a", "h", "agent", {"prs": prs_rec([])})], None, status(), 0, 60, 8)[0])
        self.assertIn("  no pull requests in flight", rows)


if __name__ == "__main__":
    unittest.main()
