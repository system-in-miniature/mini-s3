#!/usr/bin/env python3
"""End-to-end tests for the learner-facing Journey workspace commands."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from journey.tools import build_journey


ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "journey" / "tools" / "build_journey.py"


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


class LearningWorkspaceTest(unittest.TestCase):
    def test_final_parity_scope_excludes_site_only_documentation_tests(self) -> None:
        parity_tests = build_journey.parity_tree_bytes(ROOT, "tests")

        self.assertNotIn("test_docs_homepage.py", parity_tests)
        self.assertIn("test_model.py", parity_tests)

    def test_study_check_attempt_state_transition(self) -> None:
        with tempfile.TemporaryDirectory(prefix="minis3-journey-test-") as temporary:
            workspace = Path(temporary) / "learner"
            cli = [sys.executable, str(TOOL)]

            help_output = run([*cli, "--help"]).stdout
            self.assertIn("study N", help_output)
            self.assertIn("attempt N", help_output)
            self.assertIn("agent N", help_output)
            self.assertIn("check N", help_output)

            studied = run(
                [*cli, "study", "2", "--workspace", str(workspace), "--yes"]
            ).stdout
            self.assertIn("[study stage-02] READY", studied)
            self.assertIn("uncommitted reference patch", studied)
            baseline_subject = run(
                ["git", "log", "-1", "--pretty=%s"], cwd=workspace
            ).stdout.strip()
            self.assertEqual(baseline_subject, "journey baseline: stage-01")
            first_status = run(
                ["git", "status", "--short"], cwd=workspace
            ).stdout
            self.assertTrue(first_status.strip())

            checked = run(
                [*cli, "check", "2", "--workspace", str(workspace)]
            ).stdout
            self.assertIn("[check stage-02] PASS", checked)
            self.assertIn("[reference diff --stat]", checked)
            self.assertIn("(no differences)", checked)

            readme = workspace / "README.md"
            readme.write_text(readme.read_text() + "\nlearner drift\n")
            drifted_check = run(
                [*cli, "check", "2", "--workspace", str(workspace)],
                check=False,
            )
            self.assertNotEqual(drifted_check.returncode, 0)
            self.assertIn("[check stage-02] TESTS PASS", drifted_check.stdout)
            self.assertIn("[reference parity] INCOMPLETE", drifted_check.stdout)

            run([*cli, "study", "2", "--workspace", str(workspace), "--yes"])
            second_status = run(
                ["git", "status", "--short"], cwd=workspace
            ).stdout
            self.assertEqual(second_status, first_status)

            attempted = run(
                [*cli, "attempt", "2", "--workspace", str(workspace), "--yes"]
            ).stdout
            self.assertIn("[attempt stage-02] READY", attempted)
            self.assertIn(
                str(
                    ROOT
                    / "journey"
                    / "stages"
                    / "02-bucket-state"
                    / "goal.md"
                ),
                attempted,
            )
            self.assertIn("check 2", attempted)
            self.assertEqual(
                run(["git", "status", "--short"], cwd=workspace).stdout,
                "",
            )

            self.assertEqual(
                run(["git", "log", "-1", "--pretty=%s"], cwd=workspace)
                .stdout.strip(),
                "journey baseline: stage-01",
            )
            attempt_check = run(
                [*cli, "check", "2", "--workspace", str(workspace)],
                check=False,
            )
            self.assertNotEqual(attempt_check.returncode, 0)
            self.assertIn("stage-02 tests failed", attempt_check.stdout)
            self.assertIn("src/minis3/bucket.py", attempt_check.stdout)

    def test_agent_mode_prepares_then_resumes_without_copying_tutor_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="minis3-agent-test-") as temporary:
            workspace = Path(temporary) / "learner"
            cli = [sys.executable, str(TOOL)]

            output = run(
                [*cli, "agent", "3", "--workspace", str(workspace), "--yes"]
            ).stdout

            self.assertIn("[agent stage-03] READY", output)
            self.assertIn(f"WORKSPACE: {workspace.resolve()}", output)
            self.assertIn("CHECK:", output)
            self.assertFalse((workspace / "AGENTS.md").exists())
            self.assertFalse((workspace / ".journey").exists())
            self.assertEqual(
                run(["git", "status", "--short"], cwd=workspace).stdout,
                "",
            )
            self.assertEqual(
                run(
                    ["git", "config", "--local", "--get", "journey.agentStage"],
                    cwd=workspace,
                ).stdout.strip(),
                "03",
            )

            learner_note = workspace / "learner-note.txt"
            learner_note.write_text("keep my progress\n")
            resumed = run(
                [*cli, "agent", "3", "--workspace", str(workspace)]
            ).stdout

            self.assertIn("[agent stage-03] RESUME", resumed)
            self.assertEqual(learner_note.read_text(), "keep my progress\n")

    def test_default_agent_workspace_is_scoped_by_stage(self) -> None:
        stages = build_journey.discover_stages()

        stage_03 = build_journey.select_stage(3, stages)
        stage_04 = build_journey.select_stage(4, stages)

        self.assertEqual(
            build_journey.default_agent_workspace(stage_03),
            ROOT / ".journey-workspaces" / "stage-03",
        )
        self.assertEqual(
            build_journey.default_agent_workspace(stage_04),
            ROOT / ".journey-workspaces" / "stage-04",
        )


if __name__ == "__main__":
    unittest.main()
