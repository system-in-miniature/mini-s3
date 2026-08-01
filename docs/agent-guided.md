# Agent-Guided Rebuild

Use this mode when you want Codex to guide one MiniS3 Stage interactively in a
terminal. The command prepares a clean Stage N-1 baseline, installs `AGENTS.md`,
and places the current Stage's agent-only context in `.journey/`.

## 1. Prepare a Stage

From the MiniS3 repository:

```bash
python journey/tools/build_journey.py agent N
```

Replace `N` with a number from 1 to 15. For example:

```bash
python journey/tools/build_journey.py agent 3
```

The default learning repository is `../MiniS3-journey-workspace`. Rebuilding an
existing workspace asks for confirmation; add `--yes` only when you intend to
replace its current Stage work.

## 2. Open the CLI Agent

```bash
cd ../MiniS3-journey-workspace
codex
```

Then send:

```text
开始 Stage 03
```

Use the two-digit Stage number printed by the preparation command.

## 3. Continue and Verify

The agent reads `AGENTS.md` and `.journey/stage.md`, uses quick questions to
calibrate your current understanding, implements the Stage in small slices,
and guides the code walkthrough. Ask `继续` to move on or ask for a direct
explanation whenever a question is not useful.

At the end, the agent runs the exact command stored in
`.journey/check-command.txt`. It verifies both cumulative tests and parity with
the canonical Stage tree.

To use a different workspace:

```bash
python journey/tools/build_journey.py agent 3 --workspace /absolute/path/to/workspace
```
