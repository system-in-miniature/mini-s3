# MiniS3 Journey Browser Diff Lessons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish all 15 MiniS3 Journey stages as bilingual, self-contained mechanism lessons with synchronized per-file diff explanations.

**Architecture:** Keep `goal.md`, `stage.patch`, and `tests.txt` as stage facts. Extend the Python renderer with a lossless per-file patch parser, runtime-responsibility ordering, changed-symbol extraction, and localized file-role/data-flow explanations. Tests remain verification evidence after the mechanism walkthrough rather than the lesson's mandatory opening sequence.

**Tech Stack:** Python 3.12, unittest/pytest, MkDocs Material, Markdown, GitHub Actions, GitHub Pages

---

### Task 1: Lock the per-file renderer contract

**Files:**
- Create: `journey/tools/tests/test_render_pages.py`
- Modify: `journey/tools/render_pages.py`

- [ ] Write tests requiring lossless `stage.patch` splitting, one rendered
  section per patched file, runtime-responsibility ordering, bilingual labels,
  and a final complete-patch audit link.
- [ ] Run `uv run python -m unittest journey.tools.tests.test_render_pages -v`
  and verify it fails because the parser and walkthrough do not exist.
- [ ] Add immutable `FilePatch` parsing, changed-symbol extraction, file-role
  classification, and a separate display-order helper.
- [ ] Re-run the focused parser tests and verify the parser assertions pass.

### Task 2: Author the mechanism overview for all stages

**Files:**
- Modify: `journey/stages/01-scaffold-object-model/goal.md` through
  `journey/stages/15-public-api-parity/goal.md`

- [ ] Add an English `Mechanism walkthrough` and Chinese `机制走读` section to
  every stage, naming the main ownership boundary, input-to-output flow, and
  practical failure/debugging point.
- [ ] Keep crash-only stages explicit as executable proof stages and avoid
  pretending that production code changes there.
- [ ] Keep verification commands and tests after the mechanism explanation.

### Task 3: Render complete independent-browser lessons

**Files:**
- Modify: `journey/tools/render_pages.py`
- Regenerate: `docs/journey/index.md`, `docs/journey/stage-01.md` through
  `stage-15.md`, and their `docs/zh/journey/` counterparts

- [ ] Split each localized goal body so mechanism prose precedes generated
  file-by-file walkthroughs and checks/verification follow them.
- [ ] For each file render its responsibility, changed symbols, connection to
  the stage flow, debugging entry point, and an isolated collapsible diff.
- [ ] Retain GitHub compare/checkout links and add a final canonical patch
  audit link without embedding the same diff twice.
- [ ] Generate pages twice and verify the second render is idempotent.

### Task 4: Align navigation and tutor contracts

**Files:**
- Modify: `JOURNEY-AGENTS.md`
- Modify: `journey/README.md`
- Modify: generated English and Chinese Journey indexes

- [ ] Document independent browser study as a complete path, with the agent as
  an interactive enhancement rather than a requirement.
- [ ] Tell both paths to follow mechanism/data flow, small file slices,
  verification, understanding checks, and interview expression.
- [ ] Keep `journey attempt` experimental without making test-first work the default.

### Task 5: Verify, publish, and inspect

**Files:**
- Verify and commit all scoped changes

- [ ] Run `git diff --check`.
- [ ] Run `uv run pytest -q` and require all tests to pass.
- [ ] Run `uv run python journey/tools/build_journey.py --check` and require all
  15 stages plus final source/test parity to pass.
- [ ] Run `uv run mkdocs build --strict`.
- [ ] Inspect representative Stage 01, 07, 11, and 14 pages in both languages
  at desktop and mobile widths.
- [ ] Commit the implementation, merge it into `main`, push without force, wait
  for CI/Journey/Documentation workflows, and verify the public Pages artifact.
