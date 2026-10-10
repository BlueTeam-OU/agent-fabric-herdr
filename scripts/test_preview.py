import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import scripts.conventional_commits as conventional_commits
import scripts.preview as preview


class PreviewNotesTests(unittest.TestCase):
    def test_notes_contain_only_build_and_comparison_link(self):
        self.assertEqual(
            preview.build_notes("previous-sha", "current-sha", "2026-09-16-abcdef123456", "BlueTeam-OU/agent-fabric-fleetdeck"),
            "Preview build 2026-09-16-abcdef123456\n\n"
            "[View changes](https://github.com/BlueTeam-OU/agent-fabric-fleetdeck/compare/previous-sha...current-sha)\n",
        )

    def test_build_manifest_archives_assets_with_selected_source_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "preview.json"
            notes = "Preview notes\n"
            content = preview.build_manifest(
                output=output,
                repo="BlueTeam-OU/agent-fabric-fleetdeck",
                tag="preview-2026-06-02-abcdef123456",
                build_id="2026-06-02-abcdef123456",
                commit="abcdef1234567890",
                built_at="2026-06-02T03:00:00Z",
                base_version="0.6.6",
                protocol=12,
                notes=notes,
                shas={
                    "linux-x86_64": "deadbeef",
                    "windows-x86_64": "a" * 64,
                },
                retain=30,
                endpoint_generation=77,
            )
            data = json.loads(content)
            self.assertEqual(data["channel"], "preview")
            self.assertEqual(data["build_id"], "2026-06-02-abcdef123456")
            self.assertEqual(
                data["endpoint_generation"],
                77,
            )
            self.assertEqual(
                data["assets"]["linux-x86_64"]["sha256"],
                "deadbeef",
            )
            self.assertEqual(
                data["assets"]["windows-x86_64"]["url"],
                "https://github.com/BlueTeam-OU/agent-fabric-fleetdeck/releases/download/preview-2026-06-02-abcdef123456/agent-fabric-fleetdeck-windows-x86_64.zip",
            )
            self.assertEqual(
                data["assets"]["windows-x86_64"]["sha256"],
                "a" * 64,
            )
            self.assertEqual(data["assets"]["windows-x86_64"]["format"], "zip")
            self.assertIn("2026-06-02-abcdef123456", data["builds"])
            self.assertEqual(
                data["builds"]["2026-06-02-abcdef123456"]["endpoint_generation"],
                77,
            )

    def test_windows_preview_asset_requires_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "windows-x86_64 requires"):
                preview.build_manifest(
                    output=Path(tmp) / "preview.json",
                    repo="BlueTeam-OU/agent-fabric-fleetdeck",
                    tag="preview-test",
                    build_id="test",
                    commit="abcdef",
                    built_at="2026-06-02T03:00:00Z",
                    base_version="0.6.6",
                    protocol=12,
                    notes="test",
                    shas={},
                    retain=1,
                )

    def test_preview_range_base_advances_to_stable_tag(self):
        with (
            mock.patch.object(preview, "latest_stable_tag", return_value="v0.7.0"),
            mock.patch.object(preview, "git_is_ancestor", return_value=True),
        ):
            self.assertEqual(
                preview.preview_range_base("previous-preview", "release"),
                "v0.7.0",
            )

    def test_preview_range_base_keeps_previous_preview_for_unreleased_work(self):
        def is_ancestor(ancestor: str, descendant: str) -> bool:
            return (ancestor, descendant) in {
                ("v0.7.0", "new-feature"),
                ("previous-preview", "new-feature"),
            }

        with (
            mock.patch.object(preview, "latest_stable_tag", return_value="v0.7.0"),
            mock.patch.object(preview, "git_is_ancestor", side_effect=is_ancestor),
        ):
            self.assertEqual(
                preview.preview_range_base("previous-preview", "new-feature"),
                "previous-preview",
            )

    def test_hotfix_preview_uses_stable_base_instead_of_newer_master_preview(self):
        with (
            mock.patch.object(preview, "latest_stable_tag", return_value="v0.7.0"),
            mock.patch.object(preview, "git_is_ancestor", return_value=False),
        ):
            self.assertEqual(preview.preview_range_base("newer-master", "hotfix"), "v0.7.0")

    def test_post_stable_history_bases_range_on_stable_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args: str) -> str:
                return subprocess.check_output(
                    ["git", *args],
                    cwd=repo,
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()

            git("init")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Test User")

            (repo / "Cargo.toml").write_text(
                '[package]\nname = "agent-fabric-fleetdeck"\n', encoding="utf-8"
            )
            marker = repo / "marker.txt"
            marker.write_text("preview\n", encoding="utf-8")
            git("add", "marker.txt", "Cargo.toml")
            git("commit", "-m", "feat: previous preview")
            previous_preview = git("rev-parse", "HEAD")

            marker.write_text("release\n", encoding="utf-8")
            git("commit", "-am", "release: v0.7.0")
            release = git("rev-parse", "HEAD")
            git("tag", "v0.7.0")

            original_cwd = os.getcwd()
            try:
                os.chdir(repo)
                self.assertEqual(
                    preview.preview_range_base(previous_preview, release),
                    "v0.7.0",
                )
            finally:
                os.chdir(original_cwd)

class StableTagTests(unittest.TestCase):
    def test_inherited_herdr_tags_are_not_fleetdeck_stable_releases(self):
        with tempfile.TemporaryDirectory(prefix="fleetdeck-preview-") as root:
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

            def commit(name, version):
                Path(root, "Cargo.toml").write_text(
                    f'[package]\nname = "{name}"\nversion = "{version}"\n', encoding="utf-8"
                )
                git("add", ".")
                git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", version)

            git("init", "-q", "-b", "master")
            commit("herdr", "0.9.3")
            git("-c", "tag.gpgsign=false", "tag", "v0.9.3")
            previous_cwd = Path.cwd()
            os.chdir(root)
            try:
                with self.assertRaises(subprocess.CalledProcessError):
                    preview.latest_stable_tag()
                commit("agent-fabric-fleetdeck", "0.10.0")
                git("-c", "tag.gpgsign=false", "tag", "v0.10.0")
                commit("herdr", "0.11.0")
                git("-c", "tag.gpgsign=false", "tag", "v0.11.0")
                self.assertEqual(preview.latest_stable_tag(), "v0.10.0")
            finally:
                os.chdir(previous_cwd)


class ConventionalCommitTests(unittest.TestCase):
    def test_valid_subjects_allow_scopes_and_bang(self):
        self.assertTrue(conventional_commits.valid_subject("fix(update): handle preview"))
        self.assertTrue(conventional_commits.valid_subject("feat!: change config"))
        self.assertFalse(conventional_commits.valid_subject("update preview channel"))

    def test_commit_message_subject_skips_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "COMMIT_EDITMSG"
            path.write_text(
                "\n# Please enter the commit message\n\nfix(update): switch channel\n",
                encoding="utf-8",
            )
            self.assertEqual(
                conventional_commits.commit_message_subject(path),
                "fix(update): switch channel",
            )


if __name__ == "__main__":
    unittest.main()
