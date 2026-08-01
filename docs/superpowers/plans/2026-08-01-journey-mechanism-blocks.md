# Journey Mechanism Blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render all 15 Self-Guided Rebuild Stages as conceptual mechanism blocks with per-file core diff separators and compact supporting-file treatment.

**Architecture:** Each Stage owns a `layout.toml` that groups canonical patch files into bilingual core or supporting blocks. The renderer validates complete ownership, emits one diff drawer per core file and one combined drawer per supporting block, suppresses supporting-file prose, and lets each core drawer replace the redundant file-path label.

**Tech Stack:** Python 3.12, `tomllib`, dataclasses, unittest/pytest, MkDocs Material, Markdown

---

### Task 1: Lock The Block Contract

**Files:**
- Modify: `journey/tools/tests/test_render_pages.py`

- [ ] Add failing tests for exact block coverage, duplicate rejection,
  supporting-file suppression, per-file drawer order, absence of repeated
  explanation labels, and absence of per-file headings in rendered pages.
- [ ] Run `uv run pytest -q journey/tools/tests/test_render_pages.py` and verify
  failures identify the missing layout model and current file-centric output.

### Task 2: Add Authored Stage Layouts

**Files:**
- Create: `journey/stages/01-scaffold-object-model/layout.toml`
- Create: `journey/stages/02-bucket-state/layout.toml`
- Create: `journey/stages/03-durable-storage-boundary/layout.toml`
- Create: `journey/stages/04-object-service/layout.toml`
- Create: `journey/stages/05-version-history/layout.toml`
- Create: `journey/stages/06-directory-illusion/layout.toml`
- Create: `journey/stages/07-publication-crash-matrix/layout.toml`
- Create: `journey/stages/08-fsync-recovery/layout.toml`
- Create: `journey/stages/09-multipart-domain/layout.toml`
- Create: `journey/stages/10-multipart-staging/layout.toml`
- Create: `journey/stages/11-multipart-complete/layout.toml`
- Create: `journey/stages/12-multipart-recovery/layout.toml`
- Create: `journey/stages/13-conditional-cas/layout.toml`
- Create: `journey/stages/14-lifecycle-tick/layout.toml`
- Create: `journey/stages/15-public-api-parity/layout.toml`

- [ ] Write the exact bilingual titles, summaries, file lists, and supporting
  flags from the approved Stage layout table.
- [ ] Verify every path from each `stage.patch` appears exactly once across its
  layout blocks.

### Task 3: Parse And Validate Mechanism Blocks

**Files:**
- Modify: `journey/tools/render_pages.py`

- [ ] Add immutable block-layout models and load `layout.toml` with `tomllib`.
- [ ] Validate required strings, non-empty file lists, stable unique IDs, and
  exact one-to-one patch ownership with Stage-specific errors.
- [ ] Run the focused renderer tests and verify the parsing contracts pass.

### Task 4: Render Mechanism Blocks With File Diff Separators

**Files:**
- Modify: `journey/tools/render_pages.py`
- Modify: `journey/tools/tests/test_render_pages.py`

- [ ] Move every changed `tests/` diff and its authored explanation directly
  after `See the failure first` / `先看会坏在哪里`.
- [ ] Exclude test files from the later mechanism block body while retaining
  the block title and summary for test-only Stages.
- [ ] Render one collapsed diff drawer per core file in layout order.
- [ ] Render one combined diff drawer for every supporting block.
- [ ] Place each core explanation immediately after its file drawer without a
  repeated path or `Explanation` label.
- [ ] Render internal explanation labels as bold text instead of Markdown
  headings.
- [ ] Suppress authored per-file prose for supporting blocks.
- [ ] Rename the authored/browser walkthrough headings to `Mechanism blocks`
  and `机制板块` and update the required heading contract.
- [ ] Run focused renderer tests until all block and file-separator contracts
  pass.

### Task 5: Regenerate And Verify

**Files:**
- Modify: all 15 `journey/stages/*/goal.md`
- Regenerate: `docs/journey/stage-01.md` through `stage-15.md`
- Regenerate: `docs/zh/journey/stage-01.md` through `stage-15.md`

- [ ] Regenerate all bilingual Stage pages from the authored goals and layouts.
- [ ] Browser-check a multi-file block, a supporting block, and a single-file
  Stage for drawer placement, default collapse, and table-of-contents shape.
- [ ] Run `uv run pytest -q`.
- [ ] Run `python -u journey/tools/build_journey.py --check`.
- [ ] Run `uv run mkdocs build --strict` and `git diff --check`.
- [ ] Commit with `git commit -m "docs: organize Journey lessons by mechanism"`.
