import subprocess
import unittest

import install_fleetdeck as install
from install_fleetdeck import Server, plan, run_steps

FLEETDECK = "/home/op/.local/bin/agent-fabric-fleetdeck"
HERDR = "/home/op/.local/bin/herdr"


def steps_for(fleetdeck=None, legacy=None, configs=()):
    return plan(root="/src/fd", bin_dir="/home/op/.local/bin", jobs=4, new_version="0.10.0",
                fleetdeck=fleetdeck, legacy=legacy, config_home="/home/op/.config",
                config_exists=lambda path: path in configs)


def commands(steps):
    return [step.argv for step in steps if step.argv]


class PlanTest(unittest.TestCase):
    def test_build_is_bounded_and_install_is_a_rename(self):
        argvs = commands(steps_for())
        self.assertEqual(argvs[0][:3], ("cargo", "build", "--release"))
        self.assertIn("--jobs", argvs[0])
        self.assertEqual(argvs[2], ("mv", "-f", "/home/op/.local/bin/.agent-fabric-fleetdeck.new", FLEETDECK))
        self.assertIn(("ln", "-sfn", "/src/fd/fleet-deck/fleet-deck", "/home/op/.local/bin/fleet-deck"), argvs)

    def test_a_running_herdr_server_is_handed_to_fleetdeck_by_its_own_cli(self):
        legacy = Server(HERDR, True, "0.9.3", True, "/home/op/.config/herdr/herdr.sock")
        argvs = commands(steps_for(legacy=legacy))
        self.assertEqual(argvs[-1], (HERDR, "server", "live-handoff", "--import-exe", FLEETDECK,
                                     "--expected-version", "0.10.0"))

    def test_a_running_fleetdeck_server_is_handed_off_before_any_herdr_one(self):
        fleetdeck = Server(FLEETDECK, True, "0.10.0", True, "s")
        legacy = Server(HERDR, True, "0.9.3", True, "h")
        argvs = commands(steps_for(fleetdeck=fleetdeck, legacy=legacy))
        self.assertEqual(argvs[-1][0], FLEETDECK)
        self.assertFalse(any(argv[0] == HERDR for argv in argvs))

    def test_nothing_stops_a_server(self):
        legacy = Server(HERDR, True, "0.9.3", False, "h")
        steps = steps_for(legacy=legacy)
        for argv in commands(steps):
            self.assertNotIn("stop", argv)
        self.assertFalse(any("live-handoff" in argv for argv in commands(steps)))
        self.assertIn("no live handoff", steps[-1].say)

    def test_no_server_means_no_handoff(self):
        self.assertFalse(any("live-handoff" in argv for argv in commands(steps_for())))

    def test_herdr_config_is_copied_only_when_fleetdeck_has_none(self):
        legacy_config = "/home/op/.config/herdr/config.toml"
        fleetdeck_config = "/home/op/.config/agent-fabric-fleetdeck/config.toml"
        copy = ("cp", "-n", "-p", legacy_config, fleetdeck_config)
        self.assertIn(copy, commands(steps_for(configs={legacy_config})))
        self.assertNotIn(copy, commands(steps_for(configs={legacy_config, fleetdeck_config})))
        self.assertNotIn(copy, commands(steps_for()))


class RunTest(unittest.TestCase):
    def test_dry_run_executes_nothing(self):
        ran = []
        said = []
        legacy = Server(HERDR, True, "0.9.3", True, "h")
        code = run_steps(steps_for(legacy=legacy), dry_run=True, cwd="/src/fd",
                         run=lambda *a, **k: ran.append(a), say=said.append)
        self.assertEqual(code, 0)
        self.assertEqual(ran, [])
        self.assertTrue(any("would hand the running herdr server" in line for line in said))

    def test_a_refused_handoff_says_nothing_was_stopped(self):
        legacy = Server(HERDR, True, "0.9.3", True, "h")
        said = []

        def run(argv, **_):
            return subprocess.CompletedProcess(argv, 1 if "live-handoff" in argv else 0)

        code = run_steps(steps_for(legacy=legacy), dry_run=False, cwd="/src/fd", run=run, say=said.append)
        self.assertEqual(code, 1)
        self.assertIn("nothing was stopped", said[-1])

    def test_status_of_an_absent_cli_is_none(self):
        self.assertIsNone(install.server_status("/nonexistent/herdr-like", subprocess.run))


if __name__ == "__main__":
    unittest.main()
