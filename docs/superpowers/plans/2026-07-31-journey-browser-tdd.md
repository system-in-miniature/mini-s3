# MiniS3 Journey Browser TDD Lessons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish all 15 MiniS3 Journey stages as bilingual, self-contained browser lessons with a real TDD narrative and synchronized per-file diff explanations.

**Architecture:** Keep each `stage.patch` as the code-increment authority and add bilingual Red/Green/Refactor prose to the existing `goal.md`. Extend the renderer to split the canonical patch by file, order tests before implementation, derive changed-symbol context, and render one collapsible diff per file plus a final audit patch. Contract tests prove that every stage contains the lesson fields and that rendered file patches remain byte-for-byte slices of the canonical patch.

**Tech Stack:** Python 3.12, `unittest`, MkDocs Material, Markdown, GitHub Actions, GitHub Pages

---

### Task 1: Lock the renderer contract with failing tests

**Files:**
- Create: `journey/tools/tests/test_render_pages.py`
- Read: `journey/tools/render_pages.py`
- Read: `journey/stages/01-scaffold-object-model/{goal.md,stage.patch}`

- [ ] **Step 1: Write a failing parser-order test**

Add a test that imports `render_pages`, loads Stage 01, and asserts that its
parsed file patches are ordered with `tests/test_model.py` before
`src/minis3/model.py`, that every `diff --git` header appears exactly once,
and that joining the file-patch text reproduces `Card.patch`.

- [ ] **Step 2: Write a failing browser-lesson test**

Assert that rendering Stage 01 in both languages contains the localized TDD
heading, the words Red/Green/Refactor, a `tests/test_model.py` file section, a
`src/minis3/model.py` file section, a collapsible block per file, and the final
full-patch audit block. Assert the first test-file heading precedes the first
source-file heading.

- [ ] **Step 3: Write a failing all-stage content test**

Iterate over `load_cards()` and require each localized source body to contain
all four authored TDD subheadings: behavior, Red, Green, and Refactor.

- [ ] **Step 4: Run the focused tests and record the expected failure**

Run:

```bash
uv run python -m unittest journey.tools.tests.test_render_pages -v
```

Expected: FAIL because the renderer has no per-file parser and the stage goals
do not yet contain TDD walkthrough fields.

### Task 2: Parse canonical patches into explainable file slices

**Files:**
- Modify: `journey/tools/render_pages.py`
- Test: `journey/tools/tests/test_render_pages.py`

- [ ] **Step 1: Add a `FilePatch` value object**

Define an immutable dataclass with `path`, `patch`, `kind`, and
`changed_symbols`. Classify `tests/**` as test contract, `src/minis3/**` as
implementation, and remaining files as project wiring/documentation.

- [ ] **Step 2: Add canonical patch splitting**

Split only at lines beginning with `diff --git a/`. Extract the `b/` path from
the header, retain every byte and newline, and sort slices by kind while
preserving original order within each kind.

- [ ] **Step 3: Add changed-symbol extraction**

Inspect added lines for Python `def`, `class`, and `test_` declarations. Return
their names as local anchors; fall back to the file name when a patch contains
only imports, exports, packaging, or documentation.

- [ ] **Step 4: Run the parser-order test**

Run the focused unittest command from Task 1. Expected: parser assertions pass;
browser and content assertions remain red.

### Task 3: Author the TDD learning chain for every stage

**Files:**
- Modify: `journey/stages/01-scaffold-object-model/goal.md`
- Modify: `journey/stages/02-bucket-state/goal.md`
- Modify: `journey/stages/03-durable-storage-boundary/goal.md`
- Modify: `journey/stages/04-object-service/goal.md`
- Modify: `journey/stages/05-version-history/goal.md`
- Modify: `journey/stages/06-directory-illusion/goal.md`
- Modify: `journey/stages/07-publication-crash-matrix/goal.md`
- Modify: `journey/stages/08-fsync-recovery/goal.md`
- Modify: `journey/stages/09-multipart-domain/goal.md`
- Modify: `journey/stages/10-multipart-staging/goal.md`
- Modify: `journey/stages/11-multipart-complete/goal.md`
- Modify: `journey/stages/12-multipart-recovery/goal.md`
- Modify: `journey/stages/13-conditional-cas/goal.md`
- Modify: `journey/stages/14-lifecycle-tick/goal.md`
- Modify: `journey/stages/15-public-api-parity/goal.md`
- Test: `journey/tools/tests/test_render_pages.py`

- [ ] **Step 1: Add the English TDD section to all 15 stages**

Place `### TDD walkthrough` between Deliverable files and Self-check. For each
stage write four source-specific paragraphs: Behavior under test, Red, Green,
and Refactor. Name the concrete test boundary and implementation mechanism;
do not claim stored command output.

- [ ] **Step 2: Add the equivalent Chinese section to all 15 stages**

Place `### TDD 走读` in the same structural position. Preserve technical names
and express the same behavior/failure/mechanism rather than translating only
the headings.

- [ ] **Step 3: Audit zero-new-test stages**

For Stages 02, 03, 09, and 15, explicitly explain that Red comes from extending
an existing executable contract or import/public-boundary check. Do not claim
that a new test file was added when the patch did not add one.

- [ ] **Step 4: Run the all-stage content test**

Run the focused unittest command. Expected: content assertions pass; rendering
assertions remain red until Task 4.

### Task 4: Render complete browser-native lessons

**Files:**
- Modify: `journey/tools/render_pages.py`
- Regenerate: `docs/journey/index.md`
- Regenerate: `docs/journey/stage-01.md` through `stage-15.md`
- Regenerate: `docs/zh/journey/index.md`
- Regenerate: `docs/zh/journey/stage-01.md` through `stage-15.md`
- Test: `journey/tools/tests/test_render_pages.py`

- [ ] **Step 1: Split authored lesson sections at render time**

Render goal/task/deliverables first, the authored TDD section second, generated
per-file walkthrough third, and existing self-check/verification/textbook
material afterward.

- [ ] **Step 2: Render localized per-file explanations**

For every file, state its boundary role, list the changed symbols, connect the
file to the stage mechanism, and provide a localized “read this diff” prompt.
Use a collapsible diff block containing only that file's canonical patch slice.

- [ ] **Step 3: Keep the full patch as a final audit view**

Rename the existing block to make clear it is the complete reference patch and
place it after the learning checks. Preserve the GitHub compare and checkout
links.

- [ ] **Step 4: Regenerate and run contract tests**

Run:

```bash
uv run python journey/tools/render_pages.py
uv run python -m unittest journey.tools.tests.test_render_pages -v
```

Expected: 15 bilingual stages rendered and all renderer contract tests PASS.

### Task 5: Align tutor and public documentation contracts

**Files:**
- Modify: `JOURNEY-AGENTS.md`
- Modify: `journey/README.md`
- Modify: `docs/journey/index.md`
- Modify: `docs/zh/journey/index.md`
- Test: `journey/tools/tests/test_render_pages.py`

- [ ] **Step 1: Update the tutor contract**

State that the browser lesson and tutor consume the same TDD and file-diff
content. The tutor may branch interactively, but independent browsing is a
complete path rather than a reduced task card.

- [ ] **Step 2: Update Journey entry pages**

Explain the two complete paths: independent browser study and agent-guided
study. Document the test-first/file-by-file reading order and retain the
experimental status of self-implementation mode.

- [ ] **Step 3: Re-render and ensure generated indexes are stable**

Run the renderer twice and assert `git diff` is unchanged after the second run.

### Task 6: Full local acceptance

**Files:**
- Verify: all changed files

- [ ] **Step 1: Run formatting and diff checks**

Run `git diff --check`. Expected: no output.

- [ ] **Step 2: Run the full test suite**

Run `uv run pytest -q`. Expected: all tests PASS.

- [ ] **Step 3: Replay all Journey stages**

Run `uv run python journey/tools/build_journey.py --check`. Expected: all 15
stage patches apply, their selected tests pass, and final source parity passes.

- [ ] **Step 4: Build strict documentation**

Run `uv run mkdocs build --strict`. Expected: exit 0 with no broken links or
navigation entries.

- [ ] **Step 5: Inspect representative pages**

Serve the site locally and inspect Stage 01, 07, 11, and 14 in English and
Chinese at desktop and mobile widths. Confirm ordering, collapsible blocks,
code readability, navigation, and absence of horizontal page overflow.

### Task 7: Publish and verify GitHub Pages

**Files:**
- Commit: the complete scoped change
- External verification: GitHub Actions and public Pages URL

- [ ] **Step 1: Commit the implementation**

Stage only Journey lesson, renderer, generated docs, tests, and contract files.
Inspect the staged diff and commit with `feat: teach Journey stages through TDD diffs`.

- [ ] **Step 2: Push `main`**

Push the existing bilingual-homepage commit, design commit, and implementation
commit to `origin/main`. Expected: push succeeds without force.

- [ ] **Step 3: Verify workflows**

Watch CI, Journey chain, and Documentation workflows for the pushed commit.
Expected: all required jobs conclude successfully and Pages deploy reports a
public URL.

- [ ] **Step 4: Verify the public artifact**

Open the deployed English and Chinese representative Stage pages and confirm
the public HTML contains the TDD section and per-file diff walkthrough. Report
the commit hash, workflow conclusions, and Pages URL.
