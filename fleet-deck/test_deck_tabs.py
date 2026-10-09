"""The harness pane's state machine, row by row of agent-fabric's
docs/fleet-deck/tab-states.md (#115, 27452bd6)."""

import unittest

from deck_tabs import (
    ENTRY_GRACE_S,
    QUICK_EXIT_S,
    SAME_SESSION_S,
    SETTLE_S,
    Before,
    at_start,
    lost,
    note_live,
    settle,
    PLAIN,
    RESTORE_WAIT_S,
    RESUME,
    STALE_AFTER_S,
    WAIT,
    WATCH,
    Arm,
    Live,
    Moveto,
    Seen,
    Shown,
    State,
    Track,
    before_live,
    classify,
    display,
    is_harness,
    live_from_record,
    moveto_in,
    SSH,
    restore,
    step,
)

NONE = Live(count=0, state="none", fresh=True)
ONE = Live(count=1, state="working", fresh=True)
HARNESS_HERE = Seen(present=True, moveto=True, harness=True)
NO_HARNESS = Seen(present=True, moveto=True, harness=False)
BARE = Seen(present=True, moveto=False)


class Live_(unittest.TestCase):
    def test_counts_live_sessions_and_picks_the_one_that_most_wants_a_person(self):
        live = live_from_record([("a", "idle"), ("b", "blocked"), ("c", "working"), ("d", "gone")], 10)
        self.assertEqual(live, Live(count=3, state="blocked", fresh=True))
        self.assertEqual(live_from_record([], 10), Live(0, "none", True))

    def test_older_than_two_heartbeats_is_not_fresh_and_no_record_is_none(self):
        self.assertFalse(live_from_record([], STALE_AFTER_S + 1).fresh)
        self.assertIsNone(live_from_record([], None))


class Harness(unittest.TestCase):
    def test_harness_up_from_every_waiting_state_is_running(self):
        for state in (State.IDLE, State.FAILED, State.ELSEWHERE, State.STARTING):
            track, arm = step(Track(state, armed_at=0), HARNESS_HERE, ONE, 1)
            self.assertEqual((track.state, arm), (State.RUNNING, None), state)
            self.assertTrue(track.harness_seen)

    def test_harness_down_leaves_the_shell_idle_or_elsewhere_and_rearms_nothing(self):
        running = Track(State.RUNNING, harness_seen=True)
        track, arm = step(running, NO_HARNESS, NONE, 1)
        self.assertEqual((track.state, track.ended_here, arm), (State.IDLE, True, None))
        self.assertEqual(display(track, NONE), Shown("idle", "shell"))
        track, arm = step(running, NO_HARNESS, ONE, 1)
        self.assertEqual((track.state, arm), (State.RUNNING, None), "the stream may not have caught up")
        ended, _ = step(track, NO_HARNESS, NONE, 2)
        self.assertEqual((ended.state, display(ended, NONE).label), (State.IDLE, "shell"))
        track, arm = step(track, NO_HARNESS, ONE, 1 + SAME_SESSION_S)
        self.assertEqual((track.state, arm), (State.ELSEWHERE, None))


class Sessions(unittest.TestCase):
    def test_a_session_without_a_harness_here_is_elsewhere_and_touches_nothing(self):
        for state in (State.IDLE, State.FAILED, State.STARTING):
            track, arm = step(Track(state, armed_at=0), NO_HARNESS, ONE, 1)
            self.assertEqual((track.state, arm), (state, None), "not before the same-session window")
            track, arm = step(track, NO_HARNESS, ONE, 1 + SAME_SESSION_S)
            self.assertEqual((track.state, arm), (State.ELSEWHERE, None), state)

    def test_a_harness_within_the_window_is_that_session_not_elsewhere(self):
        track, _ = step(Track(State.IDLE), NO_HARNESS, ONE, 1)
        track, _ = step(track, HARNESS_HERE, ONE, 2)
        self.assertEqual(track.state, State.RUNNING)

    def test_session_down_from_elsewhere_is_idle_shown_dormant(self):
        track, arm = step(Track(State.ELSEWHERE, armed_mode=WAIT), NO_HARNESS, NONE, 1)
        self.assertEqual((track.state, arm), (State.IDLE, None))
        self.assertEqual(display(track, NONE), Shown("idle", "dormant"))

    def test_session_down_in_a_pane_holding_a_plain_shell_reads_shell(self):
        track, _ = step(Track(State.ELSEWHERE, armed_mode=PLAIN), NO_HARNESS, NONE, 1)
        self.assertEqual(display(track, NONE), Shown("idle", "shell"), "Enter there activates nothing")

    def test_failed_stays_failed_while_nothing_runs(self):
        track, _ = step(Track(State.FAILED), NO_HARNESS, NONE, 1)
        self.assertEqual(track.state, State.FAILED)

    def test_an_unknown_live_changes_nothing(self):
        for state in (State.IDLE, State.ELSEWHERE, State.FAILED):
            self.assertEqual(step(Track(state), NO_HARNESS, None, 1), (Track(state), None))


class Starting(unittest.TestCase):
    def test_restoring_until_the_wait_then_failed_and_nothing_more_started(self):
        starting = Track(State.STARTING, armed_at=100, armed_mode=RESUME)
        self.assertEqual(step(starting, NO_HARNESS, NONE, 100 + RESTORE_WAIT_S - 1), (starting, None))
        track, arm = step(starting, NO_HARNESS, NONE, 100 + RESTORE_WAIT_S)
        self.assertEqual((track.state, arm), (State.FAILED, None))


class MovetoEnded(unittest.TestCase):
    def test_a_resume_that_ended_before_any_harness_is_failed_and_rearmed_wait(self):
        track, arm = step(Track(State.STARTING, armed_at=0, armed_mode=RESUME), BARE, NONE, ENTRY_GRACE_S)
        self.assertEqual((track.state, arm), (State.FAILED, Arm(WAIT)))
        self.assertEqual(display(track, NONE), Shown("blocked", "failed"))

    def test_a_wait_that_ended_is_idle_never_failed(self):
        track, arm = step(Track(State.IDLE, armed_at=0, armed_mode=WAIT), BARE, NONE, ENTRY_GRACE_S)
        self.assertEqual((track.state, arm), (State.IDLE, Arm(WAIT)))

    def test_with_a_session_on_the_account_it_is_elsewhere_and_rearmed_plain(self):
        track, arm = step(Track(State.STARTING, armed_at=0, armed_mode=RESUME), BARE, ONE, ENTRY_GRACE_S)
        self.assertEqual((track.state, arm), (State.ELSEWHERE, Arm(PLAIN)))

    def test_after_a_harness_it_is_rearmed_wait_or_plain_by_live(self):
        ran = Track(State.RUNNING, armed_at=0, harness_seen=True)
        track, arm = step(ran, BARE, NONE, 50)
        self.assertEqual((track.state, arm), (State.IDLE, Arm(WAIT)))
        self.assertEqual(display(track, NONE).label, "dormant")
        track, arm = step(ran, BARE, ONE, 50)
        self.assertEqual((track.state, arm), (State.ELSEWHERE, Arm(PLAIN)))

    def test_a_pane_just_armed_is_the_shell_not_yet_having_started_moveto(self):
        armed = Track(State.IDLE, armed_at=10)
        self.assertEqual(step(armed, BARE, NONE, 10 + ENTRY_GRACE_S - 1), (armed, None))

    def test_a_pane_the_deck_found_running_is_rearmed_wait_when_moveto_ends(self):
        track, arm = step(Track(State.IDLE), BARE, NONE, 50)
        self.assertEqual((track.state, arm), (State.IDLE, Arm(WAIT)))


class QuickExits(unittest.TestCase):
    def test_a_moveto_that_ends_at_once_twice_in_a_row_is_halted_failed(self):
        track = Track(State.IDLE, armed_at=0, armed_mode=WAIT)
        track, arm = step(track, BARE, NONE, ENTRY_GRACE_S)
        self.assertEqual((track.state, arm, track.quick_ends), (State.IDLE, Arm(WAIT), 1),
                         "the first is re-armed, as the contract says")
        track, arm = step(track, BARE, NONE, 2 * ENTRY_GRACE_S)
        self.assertEqual((track.state, arm, track.halted), (State.FAILED, None, True))
        self.assertEqual(step(track, BARE, NONE, 100), (track, None), "never typed again")
        self.assertEqual(display(track, NONE), Shown("blocked", "failed"))

    def test_an_end_after_the_quick_window_or_a_harness_resets_the_count(self):
        track = Track(State.IDLE, armed_at=0, armed_mode=WAIT, quick_ends=1)
        track, arm = step(track, BARE, NONE, QUICK_EXIT_S)
        self.assertEqual((track.quick_ends, arm), (0, Arm(WAIT)))

    def test_a_person_starting_moveto_in_a_halted_pane_is_followed_again(self):
        halted = Track(State.FAILED, quick_ends=2, halted=True)
        track, _ = step(halted, Seen(present=True, moveto=True, harness=False, mode=WAIT), NONE, 1)
        self.assertEqual((track.state, track.halted), (State.IDLE, False))


class Unknown(unittest.TestCase):
    def test_what_herdr_or_proc_cannot_say_changes_nothing(self):
        track = Track(State.RUNNING, harness_seen=True)
        self.assertEqual(step(track, Seen(present=True), ONE, 1), (track, None))
        self.assertEqual(step(track, Seen(present=True, moveto=True), ONE, 1), (track, None))

    def test_a_pane_that_is_gone_is_absent(self):
        self.assertEqual(step(Track(State.RUNNING), Seen(present=False), ONE, 1), (Track(State.ABSENT), None))


class Restore(unittest.TestCase):
    def test_a_live_session_comes_back_as_a_plain_shell_never_wait(self):
        self.assertEqual(restore(True, ONE, 7),
                         (Track(State.ELSEWHERE, armed_at=7, armed_mode=PLAIN), Arm(PLAIN)))

    def test_what_ran_before_and_died_is_resumed(self):
        self.assertEqual(restore(True, NONE, 7),
                         (Track(State.STARTING, armed_at=7, armed_mode=RESUME), Arm(RESUME)))

    def test_nothing_before_or_no_fresh_record_is_dormant_never_resume(self):
        self.assertEqual(restore(False, NONE, 7)[1], Arm(WAIT))
        self.assertEqual(restore(True, None, 7)[1], Arm(WAIT))
        self.assertEqual(restore(True, Live(0, "none", fresh=False), 7)[1], Arm(WAIT))

    def test_before_is_the_decks_record_or_on_a_first_run_a_fresh_live_record(self):
        self.assertTrue(before_live(Before(running=True), None))
        self.assertFalse(before_live(Before(running=False), ONE), "the deck's own record wins")
        self.assertTrue(before_live(None, ONE))
        self.assertFalse(before_live(None, Live(1, "idle", fresh=False)))
        self.assertFalse(before_live(None, None))


SERVER, OTHER = (100, 5000), (101, 9000)


class BeforeRecord(unittest.TestCase):
    def test_a_rise_is_written_at_once_and_cancels_a_pending_fall(self):
        pending = Before(running=True, fall_at=10, fall_server=SERVER)
        self.assertEqual(note_live(pending, 1, 12, SERVER, True), Before(running=True))
        self.assertEqual(note_live(Before(), 2, 12, SERVER, True), Before(running=True))

    def test_a_fall_settles_only_on_the_same_server_settle_s_after_it(self):
        fell = note_live(Before(running=True), 0, 10, SERVER, True)
        self.assertEqual(fell, Before(running=True, fall_at=10, fall_server=SERVER))
        self.assertEqual(settle(fell, SERVER, 10 + SETTLE_S - 1), fell)
        self.assertEqual(settle(fell, OTHER, 10 + SETTLE_S), fell, "another server proves nothing")
        self.assertEqual(settle(fell, SERVER, 10 + SETTLE_S), Before(running=False))

    def test_a_fall_is_not_noted_while_herdr_is_lost_or_the_restore_undecided(self):
        self.assertEqual(note_live(Before(running=True), 0, 10, SERVER, False), Before(running=True))
        self.assertEqual(note_live(Before(running=True), 0, 10, None, True), Before(running=True))

    def test_a_loss_discards_a_pending_fall(self):
        self.assertEqual(lost(Before(running=True, fall_at=10, fall_server=SERVER)), Before(running=True))

    def test_a_fall_left_by_an_earlier_deck_settles_only_on_the_same_server(self):
        pending = Before(running=True, fall_at=1000, fall_server=SERVER)
        self.assertEqual(at_start(pending, SERVER), Before(running=False))
        self.assertEqual(at_start(pending, OTHER), Before(running=True), "herdr restarted after it")
        self.assertEqual(at_start(pending, (SERVER[0], SERVER[1] + 1)), Before(running=True),
                         "a reused pid is another instance")
        self.assertEqual(at_start(pending, None), Before(running=True))
        self.assertEqual(at_start(Before(running=True), SERVER), Before(running=True))


class Classify(unittest.TestCase):
    def test_a_surviving_pane_is_classified_never_rearmed(self):
        self.assertEqual(classify(HARNESS_HERE, NONE).state, State.RUNNING)
        self.assertEqual(classify(NO_HARNESS, ONE), Track(State.ELSEWHERE))
        self.assertEqual(classify(NO_HARNESS, NONE), Track(State.IDLE))
        plain = Seen(present=True, moveto=True, harness=False, mode=PLAIN)
        self.assertEqual(display(classify(plain, NONE), NONE).label, "shell")
        self.assertIsNone(classify(BARE, NONE))
        self.assertIsNone(classify(Seen(present=True, moveto=True), NONE))


class Display(unittest.TestCase):
    def test_each_state_reads_as_the_contract_says(self):
        self.assertEqual(display(Track(State.RUNNING), Live(2, "blocked", True)), Shown("blocked", ""))
        self.assertEqual(display(Track(State.RUNNING), NONE), Shown("working", ""))
        self.assertEqual(display(Track(State.STARTING), NONE), Shown("working", "restoring"))
        self.assertEqual(display(Track(State.ELSEWHERE), ONE), Shown("unknown", "running elsewhere"))

    def test_stale_overrides_the_display(self):
        stale = Live(1, "working", fresh=False)
        self.assertEqual(display(Track(State.RUNNING), stale), Shown("unknown", "stale"))
        self.assertEqual(display(Track(State.IDLE), None), Shown("unknown", "stale"))


ENTER = "/usr/local/share/moveto/enter"


class Foreground(unittest.TestCase):
    def test_the_mode_is_the_last_argument_of_this_accounts_moveto_hand_off(self):
        sudo = ["sudo", "-n", "-u", "ui", "-H", ENTER, "/home/ui/projects", "ui"]
        self.assertEqual(moveto_in([(5, sudo + ["--wait"])], "ui"), Moveto(5, WAIT))
        self.assertEqual(moveto_in([(5, sudo)], "ui"), Moveto(5, PLAIN))

    def test_moveto_before_its_hand_off_and_enter_without_sudo_count_as_moveto(self):
        script = ["/bin/bash", "/usr/local/bin/moveto", "ui", "--resume"]
        self.assertEqual(moveto_in([(7, script)], "ui"), Moveto(7, RESUME))
        self.assertIsNone(moveto_in([(7, ["/bin/bash", "/usr/local/bin/moveto", "other"])], "ui"))
        self.assertEqual(moveto_in([(8, ["/bin/sh", ENTER, "/home/ui/projects", "ui"])], "ui"), Moveto(8, PLAIN))

    def test_another_accounts_sudo_or_another_command_is_not_this_moveto(self):
        self.assertIsNone(moveto_in([(5, ["sudo", "-n", "-u", "other", "-H", ENTER, "d", "t"])], "ui"))
        self.assertIsNone(moveto_in([(5, ["sudo", "-u", "ui", "vim"])], "ui"))
        self.assertIsNone(moveto_in([(5, ["vim"]), (6, [])], "ui"))

    def test_an_ssh_into_this_accounts_forced_command_is_its_moveto(self):
        key = ["-i", "/home/user/.ssh/fabric_deck", "-o", "IdentitiesOnly=yes"]
        self.assertEqual(moveto_in([(9, ["ssh", "-t", *key, "ui@127.0.0.1", "--", "--wait"])], "ui"),
                         Moveto(9, WAIT, SSH))
        self.assertEqual(moveto_in([(9, ["/usr/bin/ssh", "-tt", "-p2222", "ui@h", "--", "--watch"])], "ui"),
                         Moveto(9, WATCH, SSH))
        self.assertEqual(moveto_in([(9, ["ssh", "-l", "ui", "-p", "22", "h", "shell"])], "ui"), Moveto(9, PLAIN, SSH))
        self.assertEqual(moveto_in([(9, ["ssh", "ssh://ui@h:22", "--", "--resume"])], "ui"), Moveto(9, RESUME, SSH))
        # Options after the destination are ssh's, as OpenSSH re-parses them.
        self.assertEqual(moveto_in([(9, ["ssh", "ui@h", "-t", "--", "--wait"])], "ui"), Moveto(9, WAIT, SSH))
        self.assertEqual(moveto_in([(9, ["ssh", "ui@h", "-l", "other", "--", "--wait"])], "ui"), Moveto(9, WAIT, SSH))

    def test_any_other_ssh_is_not_this_moveto(self):
        for argv in (["ssh", "other@h", "--", "--wait"],          # another account
                     ["ssh", "ui@h"],                              # no word: enter-ssh refuses it
                     ["ssh", "ui@h", "--wait"],                    # ssh refuses --wait as an option
                     ["ssh", "ui@h", "--", "--wait", "x"],         # not the whole command
                     ["ssh", "ui@h", "bash"],                      # not one of the four words
                     ["ssh", "-p", "ui@h", "h2", "--", "--wait"],  # ui@h is -p's value; h2 has no user
                     ["ssh", "-l", "other", "h", "--", "--wait"],
                     # The first user set is the one ssh connects as (ssh -G).
                     ["ssh", "-l", "other", "ui@h", "--", "--wait"],
                     ["ssh", "-o", "User=other", "ui@h", "--", "--wait"],
                     ["ssh", "-oUser=other", "ui@h", "--", "--wait"],
                     ["ssh", "-o", "user other", "ui@h", "--", "--wait"],
                     ["ssh", "ui@h", "-l"]):                       # an option without its value
            self.assertIsNone(moveto_in([(9, argv)], "ui"), argv)

    def test_a_python_option_and_its_value_are_not_the_script(self):
        launch = "/home/ui/projects/agent-fabric/tools/fabric/launch.py"
        self.assertTrue(is_harness(["python3", "-X", "utf8", "-I", launch]))
        self.assertFalse(is_harness(["python3", "other.py", launch]))
        self.assertFalse(is_harness(["python3", "-c", "import x", launch]))

    def test_the_launcher_and_claude_are_the_harness_and_a_shell_is_not(self):
        launch = ["/usr/local/bin/fabric-python", "-I",
                  "/home/ui/projects/agent-fabric/runtime/openrouter/../../tools/fabric/launch.py"]
        self.assertTrue(is_harness(launch + ["--resume"]))
        self.assertTrue(is_harness(["claude", "--model", "x"]))
        self.assertFalse(is_harness(["bash", "--rcfile", "/usr/local/share/moveto/rc", "-i"]))
        self.assertFalse(is_harness(["vim", "notes/tools/fabric/launch.py"]))
        self.assertFalse(is_harness([]))


if __name__ == "__main__":
    unittest.main()
