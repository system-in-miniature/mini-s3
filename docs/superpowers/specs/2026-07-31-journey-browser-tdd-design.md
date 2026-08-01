# MiniS3 Journey Browser TDD Design

## Goal

Turn every bilingual Journey stage into a self-contained browser lesson. A
reader must be able to understand the stage without an agent: follow the test
first, inspect each changed file separately, connect each implementation hunk
to the behavior it makes pass, verify the stage, and finish with code-reading
and interview checks.

## Scope

The pilot covers all 15 existing MiniS3 stages. It does not redesign the
experimental `journey attempt` command, alter MiniS3 runtime behavior, or split
the canonical stage patches into a second patch chain.

## Content model

Each stage keeps these canonical artifacts:

- `goal.md`: bilingual authored lesson content and stage metadata;
- `stage.patch`: the exact code increment from the preceding stage;
- `tests.txt`: the cumulative verification selection.

`goal.md` gains a bilingual `TDD walkthrough` section with three authored
fields: the behavior placed under test, the expected Red failure before the
implementation hunk exists, and the minimal Green mechanism. A short Refactor
statement says whether the stage contains structural cleanup or deliberately
stops at Green.

The renderer parses `stage.patch` into per-file patches. The file list and diff
blocks are generated from the patch rather than copied into prose. File roles
are derived from their repository boundary (`tests/`, `src/minis3/`, packaging,
or documentation) and paired with the authored stage mechanism. This keeps
the explanation synchronized with the actual increment.

## Browser lesson flow

Each English and Chinese stage page renders in this order:

1. Goal, hands-on task, and deliverable files.
2. TDD cycle:
   - Red: open the changed test files first, state the expected failure, and
     show the exact stage verification command;
   - Green: state the smallest mechanism introduced by the source changes;
   - Refactor: identify the structural cleanup or explicitly state that the
     stage stops at a minimal Green implementation.
3. File-by-file diff walkthrough. Test files appear before source files, then
   packaging/docs. Every file has its role, its connection to the stage's data
   flow, and its own collapsible diff.
4. Verification, self-checks, the real-S3 lesson, and textbook link.
5. A final collapsible full patch for audit and copying only after the lesson.

The page must never claim a historical command output that was not recorded.
“Red” describes the reproducible expected failure against stage N-1; CI proves
the boundary by replaying the stage chain and tests.

## Validation

Automated tests require all 15 stages to provide bilingual TDD fields, require
rendered pages to contain Red/Green/Refactor and one section per patched file,
and verify that concatenating the rendered per-file patches equals the
canonical `stage.patch`. Existing Journey chain verification remains the
runtime/parity authority.

The acceptance sequence is:

- render all bilingual pages;
- run renderer contract tests;
- run the full repository test suite;
- run `build_journey.py --check` across all 15 stages;
- run strict MkDocs build;
- inspect representative early, persistence, multipart, and lifecycle pages at
  desktop and mobile widths;
- push `main` and verify the GitHub Pages deployment and public URL.

## Deployment

The existing GitHub Pages workflow remains the deployment mechanism. The
implementation is committed on `main`, pushed to `origin/main`, and accepted
only after both CI and Documentation workflows complete successfully and the
published page exposes the new lesson structure.
