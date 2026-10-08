import unittest

from fabric_deck import (
    RESTORE_WAIT_S,
    StateRecord,
    parse_state_line,
    recovery_status,
    NEW_WORKSPACE,
    Account,
    AccountTab,
    CreateTab,
    Leave,
    PaneProcess,
    Reenter,
    Undetermined,
    is_bare_shell,
    parse_moveto_list,
    plan,
    reenter_command,
    seed_workspace,
)

CATALOG = {
    "groups": ["Coordinator", "Rust Developer", "Experts"],
    "roles": [
        {"id": "fabric-coordinator", "group": "Coordinator"},
        {"id": "rust-ui-dev", "group": "Rust Developer"},
        {"id": "language-culture", "group": "Experts"},
        {"id": "orphan-role", "group": "A group the catalogue does not list"},
    ],
}

BARE = PaneProcess(shell_pid=10, foreground_process_group_id=10, foreground_names=("bash",))
IN_MOVETO = PaneProcess(shell_pid=10, foreground_process_group_id=22, foreground_names=("sudo",))


def tab(login, pane):
    return AccountTab(login=login, tab_id=f"t-{login}", workspace_id="w1", pane_id=pane)


class ParseMovetoList(unittest.TestCase):
    def test_reads_account_and_role_and_skips_the_excluded_login(self):
        text = (
            "user               fabric-coordinator  agent-fabric\n"
            "rust-ui-dev-01     rust-ui-dev         herdr interweave\n"
            "\n"
            "lonely\n"
        )
        self.assertEqual(
            parse_moveto_list(text, exclude={"user"}),
            [Account("rust-ui-dev-01", "rust-ui-dev")],
        )


class BareShell(unittest.TestCase):
    def test_a_shell_that_is_its_own_foreground_group_is_bare(self):
        self.assertIs(is_bare_shell(BARE), True)

    def test_a_running_moveto_session_is_not_bare(self):
        self.assertIs(is_bare_shell(IN_MOVETO), False)

    def test_unknown_when_herdr_cannot_tell(self):
        self.assertIsNone(is_bare_shell(PaneProcess(None, 10)))
        self.assertIsNone(is_bare_shell(PaneProcess(10, None)))


class Seed(unittest.TestCase):
    def test_a_role_goes_to_its_catalogue_group(self):
        self.assertEqual(seed_workspace("rust-ui-dev", CATALOG), "Rust Developer")

    def test_unlisted_role_unlisted_group_or_no_catalogue_go_to_new(self):
        self.assertEqual(seed_workspace("nobody", CATALOG), NEW_WORKSPACE)
        self.assertEqual(seed_workspace("orphan-role", CATALOG), NEW_WORKSPACE)
        self.assertEqual(seed_workspace("rust-ui-dev", None), NEW_WORKSPACE)


class Plan(unittest.TestCase):
    accounts = [Account("coord", "fabric-coordinator"), Account("ui", "rust-ui-dev")]

    def test_first_setup_seeds_every_tab_from_the_catalogue(self):
        actions = plan(self.accounts, [], {}, set(), CATALOG)
        self.assertEqual(
            actions,
            [CreateTab("coord", "Coordinator"), CreateTab("ui", "Rust Developer")],
        )

    def test_after_restart_bare_tabs_are_reentered_and_live_ones_left(self):
        tabs = [tab("coord", "p1"), tab("ui", "p2")]
        actions = plan(self.accounts, tabs, {"p1": BARE, "p2": IN_MOVETO}, {"fabric"}, CATALOG)
        self.assertEqual(actions, [Reenter("coord", "p1"), Leave("ui", "p2")])

    def test_a_later_account_goes_to_its_group_only_if_the_operator_kept_it(self):
        tabs = [tab("coord", "p1")]
        kept = plan(self.accounts, tabs, {"p1": IN_MOVETO}, {"Rust Developer"}, CATALOG)
        self.assertEqual(kept[1], CreateTab("ui", "Rust Developer"))
        removed = plan(self.accounts, tabs, {"p1": IN_MOVETO}, {"Mine"}, CATALOG)
        self.assertEqual(removed[1], CreateTab("ui", NEW_WORKSPACE))

    def test_a_pane_herdr_cannot_describe_is_not_guessed_at(self):
        tabs = [tab("coord", "p1"), tab("ui", "p2")]
        actions = plan(self.accounts, tabs, {"p2": IN_MOVETO}, set(), CATALOG)
        self.assertEqual(actions[0], Undetermined("coord", "p1"))

    def test_a_duplicate_label_does_not_create_a_third_tab(self):
        tabs = [tab("coord", "p1"), AccountTab("coord", "t-dup", "w2", "p9"), tab("ui", "p2")]
        actions = plan(self.accounts, tabs, {"p1": BARE, "p2": IN_MOVETO, "p9": BARE}, set(), CATALOG)
        self.assertEqual(actions, [Reenter("coord", "p1"), Leave("ui", "p2")])


class ReenterCommand(unittest.TestCase):
    def test_uses_resume_once_moveto_offers_it(self):
        self.assertEqual(reenter_command("ui", True), "moveto ui --resume")
        self.assertEqual(reenter_command("ui", False), "moveto ui")


ACTED = "2026-10-08T05:00:00Z"


NOW = "2026-10-08T05:01:00Z"


def record(state="idle", since="2026-10-08T05:00:30Z", sessions=("s-new",), last=None,
           ts="2026-10-08T05:00:50Z"):
    """`since` is the session's start; `ts` is when the stream posted the record."""
    return StateRecord("ui", state, tuple(sessions), since, ts, last_session=last)


class Statuses(unittest.TestCase):
    def test_parses_a_stream_line_of_today(self):
        line = (
            '{"address":"develop-qzapp/ui","ts":"2026-10-08T05:00:31Z","role":"rust-ui-dev",'
            '"sessions":[{"session":"s1","state":"idle","since":"2026-10-08T05:00:30Z"}],'
            '"state":"idle","since":"2026-10-08T05:00:30Z"}'
        )
        parsed = parse_state_line(line)
        self.assertEqual((parsed.login, parsed.state, parsed.session_ids), ("ui", "idle", ("s1",)))
        self.assertIsNone(parsed.resumable)
        self.assertIsNone(parsed.last_session)
        self.assertIsNone(parse_state_line("not json"))

    def test_a_missing_record_is_stale_not_failed(self):
        self.assertEqual(recovery_status(ACTED, NOW, 500, None, True), "stale")

    def test_a_record_older_than_two_heartbeats_is_stale(self):
        acted = "2026-10-08T04:29:00Z"
        quiet = record(since="2026-10-08T04:00:00Z", ts="2026-10-08T04:30:00Z")
        self.assertEqual(recovery_status(acted, "2026-10-08T04:50:00Z", 5, quiet, False), "restoring")
        self.assertEqual(recovery_status(acted, "2026-10-08T04:50:01Z", 5, quiet, False), "stale")

    def test_waiting_after_the_action_is_restoring_until_the_wait_runs_out(self):
        old = record(since="2026-10-08T04:00:00Z")
        self.assertEqual(recovery_status(ACTED, NOW, 5, old, False), "restoring")
        self.assertEqual(recovery_status(ACTED, NOW, RESTORE_WAIT_S, old, False), "failed")

    def test_back_to_a_bare_shell_without_a_session_is_failed(self):
        self.assertEqual(recovery_status(ACTED, NOW, 5, record(since="2026-10-08T04:00:00Z"), True), "failed")

    def test_a_new_live_session_is_resumed_or_fresh(self):
        self.assertEqual(recovery_status(ACTED, NOW, 5, record(), False), "resumed")
        self.assertEqual(
            recovery_status(ACTED, NOW, 5, record(), False, "fabric-resume: no transcript, started fresh"),
            "fresh",
        )
        self.assertEqual(recovery_status(ACTED, NOW, 5, record(last="s-new"), False), "resumed")
        self.assertEqual(recovery_status(ACTED, NOW, 5, record(last="s-old"), False), "fresh")


if __name__ == "__main__":
    unittest.main()
