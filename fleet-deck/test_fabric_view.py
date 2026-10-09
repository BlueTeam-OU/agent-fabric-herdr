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
    def test_nothing_is_fetched_without_focus(self):
        r = fv.Refresher({"proc": 5, "jobs": 30})
        self.assertEqual(r.due(0, focused=False), [])
        self.assertEqual(r.due(0, focused=True), ["proc", "jobs"])

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


if __name__ == "__main__":
    unittest.main()
