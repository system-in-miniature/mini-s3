# Direct Agent-Guided Entry Design

## Goal

Let a learner enter the canonical MiniS3 repository, start Codex, and say
`开始 Agent 带教 Stage NN` without manually preparing a workspace, changing a
branch, or understanding internal tutor files.

## User Experience

The complete documented flow is:

```bash
cd MiniS3
codex
```

```text
开始 Agent 带教 Stage 03
```

The Agent prepares the learning state and begins teaching. Saying the same
request again resumes the existing Stage workspace. Resetting progress is an
explicit action rather than an automatic side effect.

## Architecture

The canonical repository remains the teaching control plane. Its root
`AGENTS.md` recognizes the direct-entry phrase, reads authored material from
`journey/stages/NN-*`, invokes the Journey helper internally, and performs all
learner edits and checks in the returned workspace.

Each Stage gets a dedicated ignored repository under
`.journey-workspaces/stage-NN`. This avoids branch switching, prevents one
Stage from overwriting another, and keeps learner changes out of the canonical
working tree. The helper stores only runtime identity in the learner
repository's Git configuration; authored goals, patches, and test lists remain
in their canonical locations and are not copied into `.journey/`.

## Preparation And Resume Rules

- First entry creates `.journey-workspaces/stage-NN` at the Stage N-1 baseline.
- Re-entering the same Stage returns `RESUME` and preserves learner changes.
- `--yes` is retained as an explicit reset operation for internal/backward
  compatibility, but the Agent must not use it during ordinary startup.
- The helper prints a machine-readable workspace path and exact check command
  so the Agent can continue without asking the learner to change directories.
- Existing `study`, `attempt`, and `check` modes retain their current defaults
  and behavior.

## Teaching Contract

The root `AGENTS.md` has two modes:

1. Normal repository work when no direct Agent-teaching request is present.
2. Agent-Guided Rebuild when the learner asks to start or continue a Stage.

In teaching mode, the Agent reads the canonical goal, patch, and test list,
prepares or resumes the Stage workspace, then follows the existing screening,
concept explanation, implementation, code-reading, and completion contract.
Internal paths may be reported when useful for troubleshooting, but they are
not prerequisites the learner must understand.

## Documentation

The English and Chinese Agent-Guided pages are usage tutorials only. They show
the three user actions, explain that preparation and resume are automatic, and
do not mention `.journey/`, `agent-only`, branch switching, or a manual
`build_journey.py agent N` command.

## Same-Page Language Switching

English is the site's default locale and therefore keeps its established
unprefixed URLs: `/journey/stage-01/`, not `/en/journey/stage-01/`. Chinese
counterparts use `/zh/journey/stage-01/`.

The Material top-level `English` and `简体中文` items are navigation groups, so
their generated links normally point to each group's first page. A small site
script replaces those two links on bilingual pages with the current page's
counterpart:

- `/zh/<relative-page>/` → `/<relative-page>/` for English;
- `/<relative-page>/` → `/zh/<relative-page>/` for Chinese.

The mapping applies only to known bilingual documentation families. English-
only design-history pages retain the normal section links instead of gaining a
counterpart URL that does not exist.

## Verification

Automated tests prove:

- the documented direct-entry flow contains no manual preparation command;
- first entry creates the correct Stage N-1 baseline;
- repeated entry preserves uncommitted learner progress;
- separate Stage numbers use separate workspaces;
- authored Stage sources are read from the canonical repository rather than
  copied into the learner repository;
- all existing Journey parity, project tests, and strict MkDocs build remain
  green.
- a rendered Chinese Stage language link points to the matching English Stage,
  and the English link points back to the matching Chinese Stage.
