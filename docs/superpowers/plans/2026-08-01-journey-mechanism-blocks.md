# Journey Mechanism Blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render all 15 Self-Guided Rebuild Stages as conceptual mechanism blocks with grouped diffs and compact supporting-file treatment.

**Architecture:** Each Stage owns a `layout.toml` that groups canonical patch files into bilingual core or supporting blocks. The renderer validates complete ownership, emits one combined diff drawer per block, suppresses supporting-file prose, and converts core file labels to non-heading text.

**Tech Stack:** Python 3.12, `tomllib`, dataclasses, unittest/pytest, MkDocs Material, Markdown

---

### Task 1: Lock The Block Contract

**Files:**
- Modify: `journey/tools/tests/test_render_pages.py`

- [ ] Add failing tests for exact block coverage, duplicate rejection,
  supporting-file suppression, grouped diff order, and absence of per-file
  headings in rendered pages.
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

### Task 4: Render Grouped Blocks

**Files:**
- Modify: `journey/tools/render_pages.py`
- Modify: `journey/tools/tests/test_render_pages.py`

- [ ] Replace per-file diff rendering with one block diff drawer containing
  path-labelled diff fences in layout order.
- [ ] Render core file paths and their internal explanation labels as bold text
  instead of Markdown headings.
- [ ] Suppress authored per-file prose for supporting blocks.
- [ ] Rename the authored/browser walkthrough headings to `Mechanism blocks`
  and `机制板块` and update the required heading contract.
- [ ] Run focused renderer tests until all grouped-layout contracts pass.

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
