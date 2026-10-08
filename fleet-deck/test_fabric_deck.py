import unittest

from fabric_deck import (
    ENTRY_GRACE_S,
    RESTORE_WAIT_S,
    DeckError,
    Session,
    baselines_from_snapshot,
    snapshot_then_act,
    StateRecord,
    poll,
    printable,
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
    """`since` is when each session entered its state; `ts` is when the stream
    posted the record."""
    return StateRecord(
        "ui", state, tuple(Session(sid, state, since) for sid in sessions), ts, last_session=last
    )


class Statuses(unittest.TestCase):
    def test_parses_a_stream_line_of_today(self):
        line = (
            '{"address":"develop-qzapp/ui","ts":"2026-10-08T05:00:31Z","role":"rust-ui-dev",'
            '"sessions":[{"session":"s1","state":"idle","since":"2026-10-08T05:00:30Z"}],'
            '"state":"idle","since":"2026-10-08T05:00:30Z"}'
        )
        parsed = parse_state_line(line)
        self.assertEqual(
            (parsed.login, parsed.state, [x.session for x in parsed.sessions]), ("ui", "idle", ["s1"])
        )
        self.assertIsNone(parsed.resumable)
        self.assertIsNone(parsed.last_session)
        self.assertIsNone(parse_state_line("not json"))

    def test_the_streams_no_record_row_is_no_record(self):
        # ctl.mjs stateRow for an account with nothing on the channel: no ts.
        row = ('{"address":"develop-qzapp/ui","role":"rust-ui-dev","state":"unknown",'
               '"sessions":[],"why":"no state record on the channel"}')
        self.assertIsNone(parse_state_line(row))
        self.assertIsNone(parse_state_line('{"address":"develop-qzapp/ui","ts":"yesterday"}'))
        self.assertIsNone(parse_state_line('{"address":"develop-qzapp/ui","ts":"2026-10-08T05:00:00"}'))
        with_null_since = ('{"address":"develop-qzapp/ui","ts":"2026-10-08T05:00:00Z","state":"idle",'
                           '"sessions":[{"session":"s1","state":"idle","since":null}]}')
        self.assertEqual(recovery_status(ACTED, NOW, 5, parse_state_line(with_null_since), False), "restoring")

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

    def test_a_bare_pane_is_failed_whatever_another_session_does(self):
        # Another live session of the account changed state after the action:
        # the deck's own re-entry still ended.
        self.assertEqual(recovery_status(ACTED, NOW, 30, record(), True), "failed")

    def test_a_bare_pane_just_after_typing_is_still_restoring(self):
        self.assertEqual(
            recovery_status(ACTED, NOW, ENTRY_GRACE_S - 1, record(since="2026-10-08T04:00:00Z"), True),
            "restoring",
        )

    def test_a_new_live_session_is_resumed_or_fresh(self):
        self.assertEqual(recovery_status(ACTED, NOW, 5, record(), False), "resumed")
        self.assertEqual(
            recovery_status(ACTED, NOW, 5, record(), False, "fabric-resume: no transcript, started fresh"),
            "fresh",
        )
        self.assertEqual(recovery_status(ACTED, NOW, 5, record(last="s-new"), False), "resumed")
        self.assertEqual(recovery_status(ACTED, NOW, 5, record(last="s-old"), False), "fresh")


class StubHerdr:
    """Just enough of Herdr for poll(): pane processes and pane text."""

    def __init__(self, processes, texts, gone=()):
        self.processes, self.texts, self.gone = processes, texts, set(gone)

    def process(self, pane):
        if pane in self.gone:
            raise DeckError(f"herdr pane process-info --pane {pane}: exit 1: pane not found")
        return self.processes[pane]

    def text(self, *args):
        return self.texts[args[2]]


class Poll(unittest.TestCase):
    def test_reads_fresh_from_the_pane_while_the_new_session_runs(self):
        # The agent's screen fills the bottom of the pane; fabric-resume's line
        # is above it.
        screen = "\n".join(["fabric-resume: no transcript; starting fresh in /home/ui/projects"]
                           + [f"agent screen row {i}" for i in range(30)])
        herdr = StubHerdr({"p1": IN_MOVETO}, {"p1": screen})
        result = poll(herdr, {"ui": "p1"}, {"ui": record()}, ACTED, NOW, 10)
        self.assertEqual(result["ui"][0], "fresh")
        self.assertIn("starting fresh", result["ui"][1])

    def test_a_herdr_error_is_retried_then_failed_not_a_crash(self):
        herdr = StubHerdr({}, {}, gone={"p1"})
        self.assertEqual(poll(herdr, {"ui": "p1"}, {"ui": record()}, ACTED, NOW, 10)["ui"][0], "restoring")
        self.assertEqual(
            poll(herdr, {"ui": "p1"}, {"ui": record()}, ACTED, NOW, RESTORE_WAIT_S)["ui"][0], "failed"
        )

    def test_another_session_turning_working_is_not_the_decks(self):
        # The snapshot before the action lists s-other live; it turns working
        # just after the action, before the stream's first row is read.
        snapshot = [
            '{"address":"develop-qzapp/ui","ts":"2026-10-08T04:59:00Z","state":"idle",'
            '"sessions":[{"session":"s-other","state":"idle","since":"2026-10-08T04:00:00Z"}],'
            '"last_session":"s-last"}'
        ]
        after = StateRecord("ui", "working", (Session("s-other", "working", "2026-10-08T05:00:20Z"),),
                            "2026-10-08T05:00:20Z", last_session="s-last")
        herdr = StubHerdr({"p1": IN_MOVETO}, {"p1": ""})
        result = poll(herdr, {"ui": "p1"}, {"ui": after}, ACTED, NOW, 10,
                      baselines_from_snapshot(snapshot))
        self.assertEqual(result["ui"][0], "restoring")

    def test_last_session_listed_live_before_the_restart_can_still_resume(self):
        # A record from before the restart still lists last_session live.
        snapshot = [
            '{"address":"develop-qzapp/ui","ts":"2026-10-08T04:59:00Z","state":"idle",'
            '"sessions":[{"session":"s-last","state":"idle","since":"2026-10-08T04:00:00Z"}],'
            '"last_session":"s-last"}'
        ]
        resumed = StateRecord("ui", "idle", (Session("s-last", "idle", "2026-10-08T05:00:30Z"),),
                              "2026-10-08T05:00:30Z", last_session="s-last")
        herdr = StubHerdr({"p1": IN_MOVETO}, {"p1": ""})
        result = poll(herdr, {"ui": "p1"}, {"ui": resumed}, ACTED, NOW, 10,
                      baselines_from_snapshot(snapshot))
        self.assertEqual(result["ui"][0], "resumed")

    def test_pane_text_is_printed_without_control_characters(self):
        self.assertEqual(printable("ok\x1b]0;title\x07\x9bdone\tend"), "ok]0;titledone\tend")


class Order(unittest.TestCase):
    def test_the_snapshot_is_read_before_any_pane_is_touched(self):
        calls = []
        snapshot_then_act(lambda: calls.append("snapshot") or [], lambda: calls.append("act") or {})
        self.assertEqual(calls, ["snapshot", "act"])


class SplitTab(unittest.TestCase):
    def test_a_split_account_tab_is_not_typed_into(self):
        tabs = [AccountTab("coord", "t1", "w1", "p1", pane_count=2)]
        actions = plan([Account("coord", "fabric-coordinator")], tabs, {"p1": BARE}, set(), CATALOG)
        self.assertEqual(actions, [Undetermined("coord", "p1")])


if __name__ == "__main__":
    unittest.main()
