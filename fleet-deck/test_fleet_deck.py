"""fleet-deck against the real fabric-deck process, with herdr, fabric-ctl,
moveto and fabric-whoami replaced by stubs on PATH. A stub herdr server is a
real Unix socket listener, so the deck sees a server instance as it would."""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import fleet_deck
from fabric_deck import lock_holder, lock_path

HERE = os.path.dirname(os.path.realpath(__file__))

STUBS = {
    # The state stream records its pid, then waits to be stopped.
    "fabric-ctl": """
        if [ "$4" = "--follow" ] || [ "$3" = "--follow" ]; then
            echo $$ > "$STUB_DIR/stream.pid"
            exec sleep 3600
        fi
        exit 0
    """,
    "moveto": "exit 0",
    "fabric-whoami": 'echo \'{"address": "testhost/operator"}\'',
    # herdr: `server` listens on STUB_SOCK; `session list` names it; the rest
    # answers nothing, as a server with no workspace would.
    "herdr": """
        case "$1" in
        server)
            echo started >> "$STUB_DIR/servers"
            echo $$ >> "$STUB_DIR/server.pid"
            exec "$PYTHON" -c 'import socket,os,time
s=socket.socket(socket.AF_UNIX); s.bind(os.environ["STUB_SOCK"]); s.listen(8)
while True: c,_=s.accept(); c.close()'
            ;;
        session)
            printf '{"sessions":[{"name":"default","default":true,"socket_path":"%s"}]}\\n' "$STUB_SOCK"
            ;;
        *) echo '{}' ;;
        esac
    """,
}


def alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


def stat_fields(pid: int) -> list[str]:
    with open(f"/proc/{pid}/stat") as handle:
        return handle.read().rsplit(")", 1)[1].split()


def until(probe, seconds=10.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(0.05)
    return probe()


class FleetDeckTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fleet-deck-test-")
        bin_dir = os.path.join(self.dir, "bin")
        os.mkdir(bin_dir)
        for name, body in STUBS.items():
            path = os.path.join(bin_dir, name)
            with open(path, "w") as handle:
                handle.write("#!/bin/sh\n" + textwrap.dedent(body).lstrip())
            os.chmod(path, 0o755)
        # A Unix socket path is limited to 108 bytes: keep it short.
        runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
        self.sock_dir = tempfile.mkdtemp(prefix="fd-", dir=runtime)
        env = {
            "PATH": bin_dir + os.pathsep + os.environ["PATH"],
            "XDG_STATE_HOME": os.path.join(self.dir, "state"),
            "STUB_DIR": self.dir,
            "STUB_SOCK": os.path.join(self.sock_dir, "s"),
            "PYTHON": sys.executable,
        }
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        for name in ("HERDR_ENV", "HERDR_POPUP", "HERDR_SOCKET_PATH", "HERDR_SESSION"):
            os.environ.pop(name, None)
        self.addCleanup(self.clean)
        self.said = []

    def clean(self):
        # Nothing a run started outlives it: the deck, its stream, the server.
        holder = lock_holder(lock_path())
        if holder:
            os.kill(holder, signal.SIGKILL)
        for name in ("stream.pid", "server.pid"):
            try:
                with open(os.path.join(self.dir, name)) as handle:
                    pids = [int(line) for line in handle.read().split()]
            except FileNotFoundError:
                continue
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.sock_dir, ignore_errors=True)

    def say(self, line):
        self.said.append(line)

    def args(self):
        return SimpleNamespace(catalog=None, exclude=[], cwd=self.dir, no_fleet_tab=True)

    def stream_pid(self):
        path = os.path.join(self.dir, "stream.pid")
        if not os.path.exists(path):
            return None
        with open(path) as handle:
            text = handle.read().strip()
        return int(text) if text else None

    def test_start_twice_runs_one_detached_controller(self):
        self.assertTrue(fleet_deck.ensure_controller(self.args(), self.say))
        first = lock_holder(lock_path())
        self.assertTrue(first)
        self.assertTrue(fleet_deck.ensure_controller(self.args(), self.say))
        self.assertEqual(lock_holder(lock_path()), first)
        self.assertEqual(sum("starting the deck controller" in line for line in self.said), 1)
        fields = stat_fields(first)
        ppid, sid, tty = int(fields[1]), int(fields[3]), int(fields[4])
        self.assertNotEqual(ppid, os.getpid(), "the controller is no child of the command")
        # A session of its own, of which it is not the leader (double fork), so
        # it can never acquire a controlling terminal.
        self.assertNotEqual(sid, os.getsid(0), "the controller is in a session of its own")
        self.assertNotEqual(sid, first)
        self.assertEqual(tty, 0, "the controller has no terminal")
        self.assertEqual(os.readlink(f"/proc/{first}/fd/0"), os.devnull)
        self.assertEqual(os.readlink(f"/proc/{first}/fd/2"), fleet_deck.log_path())

    def test_stop_ends_the_controller_and_its_stream_child(self):
        self.assertTrue(fleet_deck.ensure_controller(self.args(), self.say))
        deck = lock_holder(lock_path())
        stream = until(self.stream_pid)
        self.assertTrue(stream and alive(stream), "the deck started its state stream")
        self.assertTrue(fleet_deck.stop_controller(self.say))
        self.assertIsNone(lock_holder(lock_path()))
        self.assertFalse(until(lambda: not alive(deck)) is False)
        self.assertTrue(until(lambda: not alive(stream)), "the stream child went with the deck")

    def test_restart_replaces_the_controller(self):
        self.assertTrue(fleet_deck.ensure_controller(self.args(), self.say))
        first = lock_holder(lock_path())
        self.assertTrue(fleet_deck.stop_controller(self.say))
        self.assertTrue(fleet_deck.ensure_controller(self.args(), self.say))
        second = lock_holder(lock_path())
        self.assertTrue(second)
        self.assertNotEqual(first, second)

    def test_a_second_deck_refuses_to_run(self):
        self.assertTrue(fleet_deck.ensure_controller(self.args(), self.say))
        holder = lock_holder(lock_path())
        second = subprocess.run(
            [fleet_deck.DECK, "--no-fleet-tab", "--cwd", self.dir],
            capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
        )
        self.assertEqual(second.returncode, 1)
        self.assertIn(f"another deck already runs on this login (pid {holder})", second.stderr)
        self.assertEqual(lock_holder(lock_path()), holder)

    def test_the_server_is_started_once(self):
        self.assertIsNone(fleet_deck.server_up())
        self.assertTrue(fleet_deck.ensure_server(self.say))
        self.assertTrue(fleet_deck.server_up())
        self.assertTrue(fleet_deck.ensure_server(self.say))
        with open(os.path.join(self.dir, "servers")) as handle:
            self.assertEqual(handle.read().split(), ["started"])

    def test_status_says_what_runs(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(fleet_deck.status(self.say), 3)
        self.assertTrue(fleet_deck.ensure_server(self.say))
        self.assertTrue(fleet_deck.ensure_controller(self.args(), self.say))
        self.said.clear()
        self.assertEqual(fleet_deck.status(self.say), 0)
        self.assertIn(f"deck controller: running, pid {lock_holder(lock_path())}", self.said)

    def test_start_refuses_inside_a_herdr_pane(self):
        os.environ["HERDR_ENV"] = "1"
        with mock.patch("sys.stderr"):
            self.assertEqual(fleet_deck.main(["start", "--no-fleet-tab"]), 2)
        self.assertIsNone(lock_holder(lock_path()))
        os.environ["HERDR_POPUP"] = "1"
        self.assertFalse(fleet_deck.in_herdr_pane(), "a popup is the operator's own command")

    def test_a_controller_that_dies_at_once_shows_its_log(self):
        with mock.patch.object(fleet_deck, "DECK", "false"), \
             mock.patch.object(fleet_deck, "CONTROLLER_READY_S", 1):
            self.assertFalse(fleet_deck.ensure_controller(self.args(), self.say))
        self.assertTrue(any("did not start" in line for line in self.said))

    def test_the_prefix_is_said_and_a_colliding_one_is_named(self):
        config = os.path.join(self.dir, "config.toml")
        os.environ["HERDR_CONFIG_PATH"] = config
        self.assertEqual(fleet_deck.prefix_line(config), ("prefix: ctrl+6 (herdr's default)", True))
        with open(config, "w") as handle:
            handle.write('[keys]\nprefix = "ctrl+b"\n')
        line, checked = fleet_deck.prefix_line(config)
        self.assertFalse(checked)
        self.assertIn("ctrl+b", line)
        with open(config, "w") as handle:
            handle.write('[keys]\nprefix = ["ctrl+6", "ctrl+^"]\n')
        self.assertTrue(fleet_deck.prefix_line(config)[1])


if __name__ == "__main__":
    unittest.main()
