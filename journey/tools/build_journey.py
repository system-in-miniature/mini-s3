#!/usr/bin/env python3
"""Rebuild and verify MiniS3's Journey Mode patch chain."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
STAGES_ROOT = ROOT / "journey" / "stages"
DEFAULT_LEARNING_WORKSPACE = ROOT.parent / "MiniS3-journey-workspace"
STAGE_PATTERN = re.compile(r"^(?P<number>\d{2})-(?P<slug>[a-z0-9-]+)$")
DIFF_HEADER = re.compile(r"^diff --git a/(.+) b/(.+)$")
DELIVERY_HEADING = "### Deliverable files / 交付文件"
DELIVERY_ITEM = re.compile(r"^- `([^`]+)`$")
WORKSPACE_CONFIG_KEY = "journey.learningWorkspace"


class JourneyError(RuntimeError):
    """A stage-chain contract was violated."""


@dataclass(frozen=True)
class Stage:
    number: int
    slug: str
    directory: Path

    @property
    def label(self) -> str:
        return f"stage-{self.number:02d}"

    @property
    def patch(self) -> Path:
        return self.directory / "stage.patch"

    @property
    def goal(self) -> Path:
        return self.directory / "goal.md"

    @property
    def tests(self) -> Path:
        return self.directory / "tests.txt"


def run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=False,
    )
    if result.returncode:
        output = result.stdout or ""
        raise JourneyError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{output}"
        )
    return result


def run_result(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def discover_stages() -> list[Stage]:
    if not STAGES_ROOT.is_dir():
        raise JourneyError(f"missing stages directory: {STAGES_ROOT}")
    stages: list[Stage] = []
    for directory in sorted(path for path in STAGES_ROOT.iterdir() if path.is_dir()):
        match = STAGE_PATTERN.fullmatch(directory.name)
        if match is None:
            raise JourneyError(f"invalid stage directory name: {directory.name}")
        stage = Stage(int(match["number"]), match["slug"], directory)
        missing = [
            path.name for path in (stage.patch, stage.goal, stage.tests) if not path.is_file()
        ]
        if missing:
            raise JourneyError(f"{stage.label} is missing: {', '.join(missing)}")
        stages.append(stage)
    expected = list(range(1, len(stages) + 1))
    actual = [stage.number for stage in stages]
    if actual != expected:
        raise JourneyError(f"stage numbers must be contiguous: expected {expected}, got {actual}")
    if not 12 <= len(stages) <= 16:
        raise JourneyError(f"expected 12-16 stages, found {len(stages)}")
    return stages


def select_stage(number: int, stages: list[Stage]) -> Stage:
    if not 1 <= number <= len(stages):
        raise JourneyError(f"stage must be between 1 and {len(stages)}, got {number}")
    return stages[number - 1]


def patch_files(stage: Stage) -> set[str]:
    files: set[str] = set()
    for line in stage.patch.read_text().splitlines():
        match = DIFF_HEADER.match(line)
        if match:
            old, new = match.groups()
            files.add(new if new != "/dev/null" else old)
    if not files:
        raise JourneyError(f"{stage.label} patch does not touch any files")
    return files


def changed_lines(stage: Stage) -> int:
    count = 0
    for line in stage.patch.read_text().splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            count += 1
    return count


def declared_files(stage: Stage) -> set[str]:
    lines = stage.goal.read_text().splitlines()
    try:
        start = lines.index(DELIVERY_HEADING) + 1
    except ValueError as exc:
        raise JourneyError(f"{stage.label} goal lacks {DELIVERY_HEADING!r}") from exc
    files: set[str] = set()
    for line in lines[start:]:
        if line.startswith("### "):
            break
        match = DELIVERY_ITEM.fullmatch(line)
        if match:
            files.add(match.group(1))
    if not files:
        raise JourneyError(f"{stage.label} goal declares no deliverable files")
    return files


def test_nodes(stage: Stage) -> list[str]:
    nodes = [
        line.strip()
        for line in stage.tests.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not nodes:
        raise JourneyError(f"{stage.label} tests.txt is empty")
    return nodes


def verify_stage_contract(stage: Stage) -> int:
    touched = patch_files(stage)
    declared = declared_files(stage)
    undeclared = touched - declared
    if undeclared:
        raise JourneyError(
            f"{stage.label} patch touches undeclared files: {sorted(undeclared)}"
        )
    line_count = changed_lines(stage)
    if line_count > 400:
        raise JourneyError(f"{stage.label} changes {line_count} lines (limit: 400)")
    return line_count


def tree_bytes(root: Path, relative: str) -> dict[str, bytes]:
    base = root / relative
    if not base.is_dir():
        raise JourneyError(f"missing parity tree: {base}")
    return {
        path.relative_to(base).as_posix(): path.read_bytes()
        for path in sorted(base.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }


def assert_final_parity(worktree: Path) -> None:
    for relative in ("src/minis3", "tests"):
        expected = tree_bytes(ROOT, relative)
        actual = tree_bytes(worktree, relative)
        if actual != expected:
            missing = sorted(expected.keys() - actual.keys())
            extra = sorted(actual.keys() - expected.keys())
            changed = sorted(
                path for path in expected.keys() & actual.keys() if expected[path] != actual[path]
            )
            raise JourneyError(
                f"final parity failed for {relative}: "
                f"missing={missing}, extra={extra}, changed={changed}"
            )


def sync_stage(
    worktree: Path,
    env: dict[str, str],
    has_seed_environment: bool,
    registry_available: bool,
) -> bool:
    if not registry_available:
        run(
            ["uv", "sync", "--quiet", "--no-install-project"],
            cwd=worktree,
            env=env,
        )
        return False
    try:
        run(["uv", "sync", "--quiet"], cwd=worktree, env=env)
        return True
    except JourneyError as exc:
        message = str(exc)
        unavailable_registry = "Failed to fetch" in message or "dns error" in message
        if not has_seed_environment or not unavailable_registry:
            raise
        run(
            ["uv", "sync", "--quiet", "--no-install-project"],
            cwd=worktree,
            env=env,
        )
        return False


def publish_refs(worktree: Path, stages: list[Stage], commits: list[str]) -> None:
    run(
        [
            "git",
            "fetch",
            "--force",
            str(worktree),
            "refs/heads/journey:refs/heads/journey",
        ],
        cwd=ROOT,
    )
    for stage, commit in zip(stages, commits, strict=True):
        run(["git", "tag", "--force", stage.label, commit], cwd=ROOT)


def initialize_learning_workspace(workspace: Path) -> bool:
    workspace = workspace.resolve()
    git_directory = workspace / ".git"
    if git_directory.exists():
        marker = run_result(
            ["git", "config", "--local", "--get", WORKSPACE_CONFIG_KEY],
            cwd=workspace,
        )
        if marker.returncode or marker.stdout.strip() != "true":
            raise JourneyError(
                f"refusing to use an unmarked Git repository: {workspace}"
            )
        return False

    if workspace.exists() and any(workspace.iterdir()):
        raise JourneyError(
            f"refusing to initialize a non-empty directory: {workspace}"
        )
    workspace.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q", "-b", "journey-learning"], cwd=workspace)
    run(["git", "config", "user.name", "MiniS3 Journey Learner"], cwd=workspace)
    run(
        ["git", "config", "user.email", "journey-learner@minis3.invalid"],
        cwd=workspace,
    )
    run(["git", "config", WORKSPACE_CONFIG_KEY, "true"], cwd=workspace)
    (git_directory / "info" / "exclude").write_text(
        ".venv/\n.pytest_cache/\n.ruff_cache/\n__pycache__/\n*.pyc\n"
    )
    print(f"[workspace] initialized dedicated Git repository: {workspace}")
    return True


def confirm_rebuild(workspace: Path, *, yes: bool, newly_created: bool) -> None:
    if newly_created or yes:
        return
    prompt = (
        f"Rebuild {workspace}? This will reset --hard and remove untracked "
        "files in the dedicated learning workspace. [y/N] "
    )
    try:
        answer = input(prompt)
    except EOFError as exc:
        raise JourneyError(
            "confirmation required; rerun with --yes to overwrite the learning workspace"
        ) from exc
    if answer.strip().lower() not in {"y", "yes"}:
        raise JourneyError("learning workspace rebuild cancelled")


def has_head(workspace: Path) -> bool:
    return (
        run_result(["git", "rev-parse", "--verify", "HEAD"], cwd=workspace).returncode
        == 0
    )


def rebuild_baseline(
    workspace: Path,
    stage: Stage,
    stages: list[Stage],
    *,
    yes: bool,
) -> None:
    workspace = workspace.resolve()
    newly_created = initialize_learning_workspace(workspace)
    confirm_rebuild(workspace, yes=yes, newly_created=newly_created)

    if has_head(workspace):
        run(["git", "reset", "--hard", "HEAD"], cwd=workspace)
    run(["git", "clean", "-fd"], cwd=workspace)
    if run(["git", "ls-files"], cwd=workspace).stdout.strip():
        run(["git", "rm", "-r", "-q", "--ignore-unmatch", "--", "."], cwd=workspace)

    for previous in stages[: stage.number - 1]:
        run(["git", "apply", str(previous.patch)], cwd=workspace)
    run(["git", "add", "-A"], cwd=workspace)

    subject = f"journey baseline: stage-{stage.number - 1:02d}"
    same_tree = (
        has_head(workspace)
        and run_result(["git", "diff", "--cached", "--quiet"], cwd=workspace).returncode
        == 0
    )
    current_subject = (
        run(["git", "log", "-1", "--pretty=%s"], cwd=workspace).stdout.strip()
        if has_head(workspace)
        else ""
    )
    if same_tree and current_subject == subject:
        print(f"[baseline] reused {subject}")
    else:
        run(
            ["git", "commit", "-q", "--allow-empty", "-m", subject],
            cwd=workspace,
        )
        print(f"[baseline] committed {subject}")


def study(stage: Stage, stages: list[Stage], workspace: Path, *, yes: bool) -> None:
    rebuild_baseline(workspace, stage, stages, yes=yes)
    run(["git", "apply", "--check", str(stage.patch)], cwd=workspace)
    run(["git", "apply", str(stage.patch)], cwd=workspace)
    changed = run(["git", "status", "--short"], cwd=workspace).stdout.rstrip()
    print(f"[study {stage.label}] READY — uncommitted reference patch applied")
    print(changed or "(no changes)")
    print(f"Open in VSCode: {shlex.join(['code', str(workspace.resolve())])}")


# TODO(CS336): redesign attempt as test-driven assignments — ship stage tests +
# interface stubs, learner implements until green, `check` acts as grader.
# Experimental placeholder until then (see JOURNEY-AGENTS.md "Modes").
def attempt(stage: Stage, stages: list[Stage], workspace: Path, *, yes: bool) -> None:
    rebuild_baseline(workspace, stage, stages, yes=yes)
    print(f"[attempt {stage.label}] READY — implement this stage yourself")
    print(f"Goal: {stage.goal}")
    pass_command = shlex.join(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "check",
            str(stage.number),
            "--workspace",
            str(workspace.resolve()),
        ]
    )
    print(f"Pass: {pass_command}")


def index_tree(
    workspace: Path,
    index: Path,
    *,
    patches: list[Path] | None = None,
    add_worktree: bool = False,
) -> str:
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(index)
    run(["git", "read-tree", "--empty"], cwd=workspace, env=env)
    for patch in patches or []:
        run(["git", "apply", "--cached", str(patch)], cwd=workspace, env=env)
    if add_worktree:
        run(["git", "add", "-A", "--", "."], cwd=workspace, env=env)
    return run(["git", "write-tree"], cwd=workspace, env=env).stdout.strip()


def reference_diff_stat(
    workspace: Path,
    stage: Stage,
    stages: list[Stage],
) -> str:
    with tempfile.TemporaryDirectory(prefix="minis3-journey-index-") as temporary:
        temporary_root = Path(temporary)
        reference_tree = index_tree(
            workspace,
            temporary_root / "reference.index",
            patches=[item.patch for item in stages[: stage.number]],
        )
        learner_tree = index_tree(
            workspace,
            temporary_root / "learner.index",
            add_worktree=True,
        )
        return run(
            ["git", "diff", "--stat", reference_tree, learner_tree],
            cwd=workspace,
        ).stdout.rstrip()


def check_learning_workspace(
    stage: Stage,
    stages: list[Stage],
    workspace: Path,
) -> None:
    workspace = workspace.resolve()
    initialize_learning_workspace(workspace)
    nodes = test_nodes(stage)
    command = [sys.executable, "-m", "pytest", "-q", *nodes]
    print(f"[check {stage.label}] running: {shlex.join(command)}")
    result = run_result(command, cwd=workspace)
    if result.stdout:
        print(result.stdout.rstrip())

    stat = reference_diff_stat(workspace, stage, stages)
    print("[reference diff --stat]")
    print(stat or "(no differences)")
    if result.returncode:
        raise JourneyError(
            f"{stage.label} tests failed with exit code {result.returncode}"
        )
    print(f"[check {stage.label}] PASS")


def build(*, check: bool) -> None:
    stages = discover_stages()
    contracts = {stage.number: verify_stage_contract(stage) for stage in stages}
    with tempfile.TemporaryDirectory(prefix="minis3-journey-") as temporary:
        temporary_root = Path(temporary)
        worktree = temporary_root / "worktree"
        cache = temporary_root / "uv-cache"
        environment = temporary_root / "venv"
        worktree.mkdir()
        cache.mkdir()
        has_seed_environment = (ROOT / ".venv").is_dir()
        if has_seed_environment:
            shutil.copytree(ROOT / ".venv", environment, symlinks=True)
        env = os.environ.copy()
        env["UV_CACHE_DIR"] = str(cache)
        env["UV_PROJECT_ENVIRONMENT"] = str(environment)

        run(["git", "init", "-q", "-b", "journey"], cwd=worktree)
        run(["git", "config", "user.name", "MiniS3 Journey Builder"], cwd=worktree)
        run(
            ["git", "config", "user.email", "journey-builder@minis3.invalid"],
            cwd=worktree,
        )
        (worktree / ".git" / "info" / "exclude").write_text(
            ".venv/\n.pytest_cache/\n.ruff_cache/\n__pycache__/\n*.pyc\n"
        )

        commits: list[str] = []
        previous_nodes: list[str] = []
        registry_available = True
        for stage in stages:
            nodes = test_nodes(stage)
            if nodes[: len(previous_nodes)] != previous_nodes:
                raise JourneyError(f"{stage.label} tests.txt is not cumulative")
            previous_nodes = nodes

            run(["git", "apply", "--check", str(stage.patch)], cwd=worktree)
            run(["git", "apply", str(stage.patch)], cwd=worktree)
            registry_available = sync_stage(
                worktree,
                env,
                has_seed_environment,
                registry_available,
            )
            result = run(
                ["uv", "run", "--no-sync", "pytest", "-q", *nodes],
                cwd=worktree,
                env=env,
            )
            match = re.search(r"(\d+) passed", result.stdout or "")
            if match is None:
                raise JourneyError(
                    f"{stage.label} pytest output lacks a pass count:\n{result.stdout}"
                )
            passed = int(match.group(1))

            run(["git", "add", "-A"], cwd=worktree)
            run(
                [
                    "git",
                    "commit",
                    "-q",
                    "-m",
                    f"journey({stage.label}): {stage.slug.replace('-', ' ')}",
                ],
                cwd=worktree,
            )
            commit = run(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip()
            commits.append(commit)
            print(
                f"[{stage.label}] PASS "
                f"tests={passed} diff_lines={contracts[stage.number]} "
                f"files={len(patch_files(stage))}"
            )

        assert_final_parity(worktree)
        print("[guard-chain] PASS src/minis3 and tests are byte-identical to main")
        print("[goal-parity] PASS every patch file is declared by its goal")
        if check:
            print("[refs] SKIP --check leaves journey branch and stage tags untouched")
        else:
            publish_refs(worktree, stages, commits)
            print(f"[refs] PASS updated journey and {len(stages)} stage tags")


def add_workspace_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_LEARNING_WORKSPACE,
        help=f"dedicated learning repository (default: {DEFAULT_LEARNING_WORKSPACE})",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Learner modes:\n"
            "  study N    show stage N as uncommitted editor-native changes\n"
            "  attempt N  reset to stage N-1 so you can implement stage N\n"
            "  check N    run stage N tests and compare with its reference tree"
        ),
    )
    parser.add_argument(
        "--check",
        dest="build_check",
        action="store_true",
        help="verify the full chain without updating branch or tag references",
    )
    subparsers = parser.add_subparsers(dest="command")

    study_parser = subparsers.add_parser(
        "study",
        help="apply stage N as uncommitted changes in the learning workspace",
    )
    study_parser.add_argument("stage", type=int, metavar="N")
    add_workspace_argument(study_parser)
    study_parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the overwrite confirmation",
    )

    attempt_parser = subparsers.add_parser(
        "attempt",
        help="prepare a clean stage N-1 baseline for your own implementation",
    )
    attempt_parser.add_argument("stage", type=int, metavar="N")
    add_workspace_argument(attempt_parser)
    attempt_parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the overwrite confirmation",
    )

    check_parser = subparsers.add_parser(
        "check",
        help="run stage N tests and show a reference diff stat",
    )
    check_parser.add_argument("stage", type=int, metavar="N")
    add_workspace_argument(check_parser)

    arguments = parser.parse_args()
    try:
        if arguments.command is None:
            build(check=arguments.build_check)
        else:
            stages = discover_stages()
            stage = select_stage(arguments.stage, stages)
            if arguments.command == "study":
                study(stage, stages, arguments.workspace, yes=arguments.yes)
            elif arguments.command == "attempt":
                attempt(stage, stages, arguments.workspace, yes=arguments.yes)
            else:
                check_learning_workspace(stage, stages, arguments.workspace)
    except JourneyError as exc:
        parser.exit(1, f"journey failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
