"""fabric_view: input, the refresh rule, and where its data comes from."""

import json
import os
import tempfile
import unittest

import fabric_view as fv


class Input(unittest.TestCase):
    def test_focus_reports_and_keys(self):
        events, rest = fv.parse_input(b"\x1b[Ojr\x1b[I\x1b[A\r", final=False)
        self.assertEqual(events, [fv.FOCUS_OUT, "j", "r", fv.FOCUS_IN, fv.UP, fv.ENTER])
        self.assertEqual(rest, b"")

    def test_a_sequence_split_across_reads_is_kept_for_the_next(self):
        events, rest = fv.parse_input(b"j\x1b[", final=False)
        self.assertEqual((events, rest), (["j"], b"\x1b["))
        events, rest = fv.parse_input(rest + b"O", final=False)
        self.assertEqual((events, rest), ([fv.FOCUS_OUT], b""))

    def test_a_lone_escape_is_the_escape_key_once_nothing_follows(self):
        self.assertEqual(fv.parse_input(b"\x1b", final=False), ([], b"\x1b"))
        self.assertEqual(fv.parse_input(b"\x1b", final=True), ([fv.ESCAPE], b""))

    def test_an_unknown_sequence_never_acts_as_its_letters(self):
        events, _ = fv.parse_input(b"\x1b[200~q\x1b[1;5Cr", final=False)
        self.assertEqual(events, ["q", "r"])   # the q and r typed between, not the sequences' own letters

    def test_ctrl_c_closes(self):
        self.assertEqual(fv.parse_input(b"\x03", final=False)[0], ["q"])


class Refresh(unittest.TestCase):
    def test_once_at_open_whatever_the_focus_then_nothing_without_it(self):
        for focus in (None, False, True):
            r = fv.Refresher({"proc": 5, "jobs": 30})
            self.assertEqual(r.due(0, focused=focus), ["proc", "jobs"])
            for s in ("proc", "jobs"):
                r.started(s)
                r.ended(s, 1)
            self.assertEqual(r.due(100, focused=focus), ["proc", "jobs"] if focus else [])

    def test_each_section_again_after_its_ttl_and_never_twice_at_once(self):
        r = fv.Refresher({"proc": 5, "jobs": 30})
        for s in r.due(0, True):
            r.started(s)
        self.assertEqual(r.due(100, True), [])        # still running
        r.ended("proc", 10)
        r.ended("jobs", 10)
        self.assertEqual(r.due(14, True), [])
        self.assertEqual(r.due(15, True), ["proc"])
        self.assertEqual(r.due(40, True), ["proc", "jobs"])
        self.assertEqual(r.due(40, False), [])
        self.assertEqual(r.due(40, None), [])

    def test_r_refetches_what_is_not_already_running(self):
        r = fv.Refresher({"proc": 5, "jobs": 30})
        r.started("jobs")
        self.assertEqual(r.refetch(), ["proc"])


class Sources(unittest.TestCase):
    def test_root_from_the_environment_else_the_installed_fabric_ctl(self):
        self.assertEqual(fv.fabric_root({"AGENT_FABRIC_ROOT": "/af"}, lambda _: None), "/af")
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "af", "bin"))
            os.makedirs(os.path.join(d, "path"))
            real = os.path.join(d, "af", "bin", "fabric-ctl")
            open(real, "w").close()
            link = os.path.join(d, "path", "fabric-ctl")
            os.symlink(real, link)
            self.assertEqual(fv.fabric_root({"AGENT_FABRIC_ROOT": ""}, lambda _: link), os.path.realpath(os.path.join(d, "af")))
        self.assertIsNone(fv.fabric_root({}, lambda _: None))

    def test_the_overlays_login_is_its_tabs_label(self):
        ctx = {"tab_id": "w1:t3", "tab_label": "web-dev-02", "focused_pane_id": "w1:p9"}
        self.assertEqual(fv.context_login({"HERDR_PLUGIN_CONTEXT_JSON": json.dumps(ctx)}), "web-dev-02")
        self.assertIsNone(fv.context_login({"HERDR_PLUGIN_CONTEXT_JSON": json.dumps({"tab_id": "w1:t3"})}))
        self.assertIsNone(fv.context_login({"HERDR_PLUGIN_CONTEXT_JSON": "not json"}))
        self.assertIsNone(fv.context_login({}))

    def test_one_host_record_per_machine_the_freshest_answer(self):
        import view_render as vr
        old = {"status": "ok", "src": "op:host", "at": "2026-10-09T11:00:00Z", "data": {"machine": {}}}
        new = dict(old, at="2026-10-09T11:01:00Z")
        down = {"status": "failed", "src": "op:host", "at": "2026-10-09T11:02:00Z", "why": "x"}
        agents = [vr.Agent("a", "h1", "agent", {"host": down}), vr.Agent("b", "h1", "agent", {"host": old}),
                  vr.Agent("c", "h1", "agent", {"host": new}), vr.Agent("d", "h2", "agent", {"host": None})]
        self.assertEqual(fv.host_records(agents), {"h1": new, "h2": None})


class Records(unittest.TestCase):
    def test_a_failed_fetch_of_the_whole_section_wins_over_an_older_record(self):
        from types import SimpleNamespace
        store = fv.Store()
        old = {"status": "ok", "src": "op:jobs", "at": "2026-10-09T10:00:00Z", "data": {"jobs": {"jobs": []}}}
        store.put("jobs", {"alice": old})
        placements = {"alice": SimpleNamespace(host="h", kind="agent")}
        shown = fv.agents_of(placements, store, ("jobs",), {"jobs": "FleetError: alice is not a placed account"})
        self.assertEqual(shown[0].sections["jobs"]["status"], "failed")
        self.assertIn("not a placed account", shown[0].sections["jobs"]["why"])
        self.assertIs(fv.agents_of(placements, store, ("jobs",), {})[0].sections["jobs"], old)


class Navigation(unittest.TestCase):
    def test_the_fleet_tabs_screens_are_a_key_away_and_esc_leaves_prs_for_where_it_was(self):
        nav = fv.Nav(fv.BOARD)
        self.assertIsNone(nav.key("c", rows=3, page=10))
        self.assertEqual(nav.screen, fv.COMPARE)
        nav.key("P", 3, 10)
        self.assertEqual((nav.screen, nav.back), (fv.PRS, fv.COMPARE))
        nav.key(fv.ESCAPE, 3, 10)
        self.assertEqual((nav.screen, nav.back), (fv.COMPARE, None))
        nav.key("p", 3, 10)
        nav.key("b", 3, 10)
        self.assertEqual(nav.screen, fv.BOARD)
        self.assertEqual(nav.key(fv.ESCAPE, 3, 10), None)   # Esc on the board closes nothing

    def test_the_popup_is_prs_alone_and_esc_closes_it(self):
        nav = fv.Nav(fv.PRS)
        nav.key("c", 3, 10)
        self.assertEqual(nav.screen, fv.PRS)
        self.assertEqual(nav.key(fv.ESCAPE, 3, 10), fv.QUIT)

    def test_metrics_cycle_both_ways_and_by_number(self):
        nav = fv.Nav(fv.COMPARE)
        nav.key(fv.LEFT, 3, 10)
        self.assertEqual(nav.metric, len(fv.rr.METRICS) - 1)
        nav.key(fv.RIGHT, 3, 10)
        self.assertEqual(nav.metric, 0)
        nav.key("5", 3, 10)
        self.assertEqual(nav.metric, 4)
        nav.key("9", 3, 10)
        self.assertEqual(nav.metric, 4)

    def test_enter_opens_the_selected_agent_and_selection_is_clamped(self):
        nav = fv.Nav(fv.BOARD)
        for _ in range(5):
            nav.key(fv.DOWN, rows=3, page=10)
        self.assertEqual(nav.selected, 2)
        self.assertEqual(nav.key(fv.ENTER, 3, 10), fv.OPEN_AGENT)
        self.assertIsNone(fv.Nav(fv.BOARD).key(fv.ENTER, rows=0, page=10))

    def test_arrows_are_parsed(self):
        self.assertEqual(fv.parse_input(b"\x1b[C\x1b[D\x1bOC", final=False)[0], [fv.RIGHT, fv.LEFT, fv.RIGHT])

    def test_a_popup_is_opened_sized_and_focused(self):
        argv = fv.open_argv("/bin/herdr", "fabric.fleet", "prs")
        self.assertEqual(argv[argv.index("--width") + 1], "80%")
        self.assertIn("--focus", argv)
        self.assertNotIn("--width", fv.open_argv("/bin/herdr", "fabric.fleet", "board"))


class FleetWide(unittest.TestCase):
    def test_plans_come_from_the_documents_top_level(self):
        rec = {"status": "ok", "src": "fabric-plan", "at": "t", "data": {"login": "user", "plans": []}}
        self.assertEqual(fv.answer_of({"agents": [], "plans": rec}, "plans"), ({fv.FLEET: rec}, None, {}))
        records, why, _ = fv.answer_of({"agents": []}, "plans")
        self.assertEqual(records, {})
        self.assertIn("no plans", why)

    def test_prs_carry_the_unplaced_record_beside_them(self):
        rec = {"status": "ok", "src": "pr-gate", "at": "t", "data": {"prs": []}}
        unplaced = {"status": "ok", "src": "pr-gate", "at": "t", "data": {"prs": [{"pr": 1}]}}
        doc = {"agents": [{"login": "a", "sections": {"prs": rec}}], "prs_unplaced": unplaced}
        self.assertEqual(fv.answer_of(doc, "prs"), ({"a": rec}, None, {fv.UNPLACED: {fv.FLEET: unplaced}}))

    def test_a_fleet_py_without_prs_unplaced_is_said_not_shown_as_none(self):
        import report_render as rr
        import view_render as vr
        rec = {"status": "ok", "src": "pr-gate", "at": "t", "data": {"prs": []}}
        _, _, extra = fv.answer_of({"agents": [{"login": "a", "sections": {"prs": rec}}]}, "prs")
        unplaced = extra[fv.UNPLACED][fv.FLEET]
        self.assertEqual(unplaced["status"], "failed")
        st = vr.Status(focused=True, fetching=(), now=__import__("datetime").datetime.now(), oldest=None, from_cache=False)
        rows = [vr.line_text(l) for l in rr.prs_lines([vr.Agent("a", "h", "agent", {"prs": rec})], unplaced, st, 0, 120, 10)[0]]
        self.assertTrue(any("not a placed agent's: not read: agent-fabric's fleet.py here does not list them" in r for r in rows))

    def test_a_section_fleet_does_not_serve_is_said_and_never_asked(self):
        from types import SimpleNamespace
        import queue
        fleet = SimpleNamespace(SECTIONS={"prs": SimpleNamespace(ttl=120)})
        view = fv.View(fleet, ("plans",), None, fv.Store(), queue.Queue())
        self.assertEqual(view.refresher.due(0, True), [])
        self.assertIn("serves no plans section", fv.fleet_record(view.store, "plans", view.whys)["why"])


if __name__ == "__main__":
    unittest.main()
