import unittest

from fabric_deck import (
    Release,
    Report,
    agent_command,
    agent_report,
    Watcher,
    next_backoff,
    PANE_MAP_REFRESH_S,
    RESEND_AFTER_S,
    ENTRY_GRACE_S,
    RESTORE_WAIT_S,
    DeckError,
    Session,
    baselines_from_snapshot,
    for_this_host,
    snapshot_then_act,
    StateRecord,
    poll,
    printable,
    parse_state_line,
    stop_child,
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

    def test_a_field_of_the_wrong_type_is_read_as_absent(self):
        ts = '"ts":"2026-10-08T05:00:00Z"'
        for line in ('[1]', '"x"', '{"address":5,%s}' % ts, '{"address":"h/ui","ts":5}'):
            self.assertIsNone(parse_state_line(line), line)
        odd = parse_state_line(
            '{"address":"h/ui",%s,"state":["working"],"last_session":7,"resumable":"yes",'
            '"sessions":[{"session":3},{"session":"s1","state":{},"since":9},"s2"]}' % ts
        )
        self.assertEqual((odd.state, odd.last_session, odd.resumable), ("unknown", None, None))
        self.assertEqual(odd.sessions, (Session("s1", "unknown", ""),))
        self.assertEqual(parse_state_line('{"address":"h/ui",%s,"sessions":{}}' % ts).sessions, ())

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


class Hosts(unittest.TestCase):
    def test_records_of_the_same_login_on_another_host_are_ignored(self):
        lines = [
            '{"address":"host-a/ui","ts":"2026-10-08T04:59:00Z","state":"idle",'
            '"sessions":[{"session":"s-a","state":"idle","since":"2026-10-08T04:00:00Z"}]}',
            '{"address":"host-b/ui","ts":"2026-10-08T04:59:00Z","state":"idle",'
            '"sessions":[{"session":"s-b","state":"idle","since":"2026-10-08T04:00:00Z"}]}',
        ]
        self.assertEqual(baselines_from_snapshot(lines, "host-a"), {"ui": frozenset({"s-a"})})
        self.assertEqual(parse_state_line(lines[1]).host, "host-b")

    def test_the_stream_filter_keeps_only_this_hosts_records(self):
        here = StateRecord("ui", "idle", (), "2026-10-08T05:00:00Z", host="host-a")
        there = StateRecord("ui", "idle", (), "2026-10-08T05:00:00Z", host="host-b")
        self.assertTrue(for_this_host(here, "host-a"))
        self.assertFalse(for_this_host(there, "host-a"))
        self.assertTrue(for_this_host(there, None), "an unknown host takes every record")
        self.assertFalse(for_this_host(None, "host-a"))


class SameSecond(unittest.TestCase):
    def test_a_session_live_in_the_second_of_the_action_counts(self):
        same = record(since=ACTED)
        self.assertEqual(recovery_status(ACTED, NOW, 10, same, False), "resumed")


def state_row(state):
    return StateRecord("ui", state, (), "2026-10-08T05:00:00Z", host="host-a")


class AgentPanel(unittest.TestCase):
    def test_states_map_one_to_one_and_none_releases(self):
        for state in ("working", "idle", "blocked", "unknown"):
            self.assertEqual(agent_report(state_row(state)), Report(state))
        self.assertEqual(agent_report(state_row("none")), Release())
        self.assertEqual(agent_report(state_row("stopped-answering")), Report("unknown"))



def row_line(login, state, host="host-a"):
    return ('{"address":"%s/%s","ts":"2026-10-08T05:00:00Z","sessions":[],"state":"%s"}'
            % (host, login, state))


class FakeHerdr:
    """account_tabs from a mutable table; every herdr call recorded, and a
    set of panes whose calls fail as a closed tab's would."""

    def __init__(self, tabs):
        self.tabs, self.calls, self.dead = tabs, [], set()

    def account_tabs(self, logins):
        return [t for t in self.tabs if t.login in logins]

    def call(self, *args):
        self.calls.append(args)
        if args[2] in self.dead:
            raise DeckError(f"pane {args[2]} not found")
        return {}


def watcher(herdr, logins=("ui",)):
    return Watcher(herdr=herdr, accounts=lambda: set(logins), host="host-a", log=lambda _: None)


class WatchLoop(unittest.TestCase):
    def test_only_a_change_is_sent_until_the_resend_interval(self):
        herdr = FakeHerdr([AccountTab("ui", "t1", "w1", "p1")])
        w = watcher(herdr)
        w.on_line(row_line("ui", "working"), 0)
        w.on_line(row_line("ui", "working"), 5)
        self.assertEqual(len(herdr.calls), 1, "a heartbeat sends nothing")
        w.on_line(row_line("ui", "working"), RESEND_AFTER_S + 1)
        self.assertEqual(len(herdr.calls), 2, "sent again after the interval")
        w.on_line(row_line("ui", "idle"), RESEND_AFTER_S + 2)
        self.assertEqual(herdr.calls[-1][-1], "idle")

    def test_another_hosts_record_is_ignored(self):
        herdr = FakeHerdr([AccountTab("ui", "t1", "w1", "p1")])
        watcher(herdr).on_line(row_line("ui", "working", host="host-b"), 0)
        self.assertEqual(herdr.calls, [])

    def test_a_tab_that_moved_is_found_again_after_a_failed_report(self):
        herdr = FakeHerdr([AccountTab("ui", "t1", "w1", "p1")])
        w = watcher(herdr)
        w.on_line(row_line("ui", "working"), 0)
        herdr.dead.add("p1")
        herdr.tabs = [AccountTab("ui", "t2", "w2", "p9")]
        w.on_line(row_line("ui", "idle"), 1)   # fails on p1, forces a re-map
        w.on_line(row_line("ui", "idle"), 2)   # goes to the tab's new pane
        self.assertEqual(herdr.calls[-1][2], "p9")

    def test_a_tab_split_after_mapping_is_released_and_no_longer_reported(self):
        herdr = FakeHerdr([AccountTab("ui", "t1", "w1", "p1")])
        w = watcher(herdr)
        w.on_line(row_line("ui", "working"), 0)
        herdr.tabs = [AccountTab("ui", "t1", "w1", "p1", pane_count=2)]
        w.on_line(row_line("ui", "idle"), PANE_MAP_REFRESH_S)
        self.assertEqual(herdr.calls[-1][1], "release-agent")
        self.assertEqual(len(herdr.calls), 2, "nothing reported into the split tab")

    def test_a_malformed_record_does_not_stop_the_watcher(self):
        herdr = FakeHerdr([AccountTab("ui", "t1", "w1", "p1")])
        w = watcher(herdr)
        w.on_line('{"address":5,"ts":"2026-10-08T05:00:00Z"}', 0)
        w.on_line(row_line("ui", "working").replace('"working"', '["working"]', 1), 1)
        self.assertEqual(herdr.calls[-1][-1], "unknown")

    def test_a_herdr_timeout_does_not_stop_the_watcher(self):
        herdr = FakeHerdr([AccountTab("ui", "t1", "w1", "p1")])

        def hung(*args):
            raise __import__("subprocess").TimeoutExpired(args, 30)

        herdr.call = hung
        w = watcher(herdr)
        w.on_line(row_line("ui", "working"), 0)
        self.assertEqual(w.shown, {})


class Backoff(unittest.TestCase):
    def test_waits_grow_and_reset_after_a_healthy_stream(self):
        failures, waits = 0, []
        for _ in range(8):
            failures, wait = next_backoff(failures, 0.5)
            waits.append(wait)
        self.assertEqual(waits, [1, 2, 5, 10, 30, 60, 60, 60])
        self.assertEqual(next_backoff(failures, 61), (1, 1))


class AgentCommand(unittest.TestCase):
    def test_the_pane_id_comes_first_as_herdrs_parser_wants(self):
        self.assertEqual(
            agent_command("w1:p2", Report("working")),
            ("pane", "report-agent", "w1:p2", "--source", "fabric", "--agent", "claude",
             "--state", "working"),
        )
        self.assertEqual(
            agent_command("w1:p3", Release()),
            ("pane", "release-agent", "w1:p3", "--source", "fabric", "--agent", "claude"),
        )


class Order(unittest.TestCase):
    def test_the_snapshot_is_read_before_any_pane_is_touched(self):
        calls = []
        snapshot_then_act(lambda: calls.append("snapshot") or {}, lambda: calls.append("act") or {})
        self.assertEqual(calls, ["snapshot", "act"])


class SplitTab(unittest.TestCase):
    def test_a_split_account_tab_is_not_typed_into(self):
        tabs = [AccountTab("coord", "t1", "w1", "p1", pane_count=2)]
        actions = plan([Account("coord", "fabric-coordinator")], tabs, {"p1": BARE}, set(), CATALOG)
        self.assertEqual(actions, [Undetermined("coord", "p1")])



class StopChild(unittest.TestCase):
    def stubborn_child(self):
        import subprocess
        import sys

        child = subprocess.Popen(
            [sys.executable, "-c",
             "import signal,sys,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
             "print(flush=True); time.sleep(60)"],
            stdout=subprocess.PIPE, text=True,
        )
        child.stdout.readline()  # its SIGTERM handler is in place
        self.addCleanup(child.stdout.close)
        self.addCleanup(lambda: child.poll() is None and child.kill())
        return child

    def stop(self, child, grace=0.5, signal_after=None):
        import os
        import signal
        import threading
        import fabric_deck

        saved = fabric_deck.STOP_CHILD_GRACE_S
        fabric_deck.STOP_CHILD_GRACE_S = grace
        timer = None
        if signal_after is not None:
            timer = threading.Timer(signal_after, os.kill, (os.getpid(), signal.SIGINT))
            timer.start()
        try:
            stop_child(child)
        finally:
            fabric_deck.STOP_CHILD_GRACE_S = saved
            if timer is not None:
                timer.join()

    def test_a_child_that_ignores_terminate_is_killed_and_reaped(self):
        import signal

        child = self.stubborn_child()
        before = signal.getsignal(signal.SIGINT)
        self.stop(child, grace=0.2)
        self.assertEqual(child.returncode, -signal.SIGKILL)
        self.assertIs(signal.getsignal(signal.SIGINT), before, "the handlers are given back")

    def test_a_stop_during_the_grace_is_held_until_the_child_is_reaped(self):
        import signal

        child = self.stubborn_child()
        with self.assertRaises(KeyboardInterrupt):
            self.stop(child, grace=0.5, signal_after=0.1)
        self.assertEqual(child.returncode, -signal.SIGKILL, "reaped before the stop is acted on")


if __name__ == "__main__":
    unittest.main()
