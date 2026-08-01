# Direct Agent-Guided Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let learners start any Agent-guided Stage by asking Codex directly from the canonical MiniS3 repository.

**Architecture:** The root Agent contract recognizes the direct-entry prompt and internally prepares a Stage-specific ignored learner repository. The Journey helper resumes an existing Stage workspace by default, while canonical goals, patches, and test lists remain in the source repository.

**Tech Stack:** Python 3.12, `unittest`/pytest, Git, MkDocs Material, Markdown

---

### Task 1: Lock The Direct-Entry Contract

**Files:**
- Modify: `journey/tools/tests/test_learning_workspace.py`
- Modify: `tests/test_docs_homepage.py`

- [ ] **Step 1: Write failing workspace tests**

Add a test that invokes `agent 3` without a workspace override and asserts the
reported path ends in `.journey-workspaces/stage-03`, no copied `.journey/`
directory exists, and a second invocation preserves an uncommitted learner
file while reporting `RESUME`.

- [ ] **Step 2: Write failing documentation tests**

Assert both Agent usage pages contain the direct prompt and omit
`build_journey.py agent N`, `.journey/`, `agent-only`, and branch instructions.

- [ ] **Step 3: Verify RED**

Run:

```bash
uv run pytest -q journey/tools/tests/test_learning_workspace.py tests/test_docs_homepage.py
```

Expected: FAIL because the helper still uses one shared default workspace and
the pages still document manual preparation.

### Task 2: Implement Stage-Specific Preparation And Resume

**Files:**
- Modify: `journey/tools/build_journey.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add the Stage workspace resolver**

Resolve an omitted Agent workspace to
`ROOT / ".journey-workspaces" / stage.label`, while leaving the defaults for
`study`, `attempt`, and `check` unchanged.

- [ ] **Step 2: Make Agent preparation resumable**

Record `journey.agentStage` in learner Git config. If an existing marked
workspace has the requested value and reset was not requested, print `RESUME`
and preserve the tree. Otherwise create the Stage N-1 baseline and record the
Stage identity. Do not copy `AGENTS.md` or create `.journey/` support files.

- [ ] **Step 3: Print the Agent handoff contract**

Print `WORKSPACE: <absolute-path>` and `CHECK: <exact-command>` so the root
Agent can operate there without requiring the learner to `cd`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest -q journey/tools/tests/test_learning_workspace.py tests/test_docs_homepage.py
```

Expected: workspace tests pass; documentation tests remain red until Task 3.

### Task 3: Simplify The Agent Contract And Usage Pages

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/agent-guided.md`
- Modify: `docs/zh/agent-guided.md`
- Modify: `journey/README.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`

- [ ] **Step 1: Teach the root Agent direct startup**

Document prompt recognition, internal `agent N` invocation without `--yes`,
canonical Stage source discovery, returned workspace ownership, resume
behavior, and exact verification using the printed `CHECK` command.

- [ ] **Step 2: Reduce both web pages to usage instructions**

Show only `cd MiniS3`, `codex`, the direct prompt, and how to continue or
explicitly reset. Remove learner-facing internal preparation details.

- [ ] **Step 3: Align repository summaries**

Describe Agent-Guided Rebuild as a direct conversational entry rather than a
manual workspace-preparation workflow.

- [ ] **Step 4: Verify focused tests pass**

Run:

```bash
uv run pytest -q journey/tools/tests/test_learning_workspace.py tests/test_docs_homepage.py
```

Expected: PASS.

### Task 4: Regenerate, Verify, And Commit

**Files:**
- Create: `docs/assets/javascripts/language-switch.js`
- Modify: `mkdocs.yml`
- Modify: `tests/test_docs_homepage.py`

- [ ] **Step 1: Write the failing language-switch contract**

Assert MkDocs loads `assets/javascripts/language-switch.js`, and use Playwright
against a built/served Chinese Stage to prove the English tab targets the same
unprefixed English page rather than the English navigation group's first page.

- [ ] **Step 2: Verify RED**

Run the focused documentation test and browser reproduction. Expected: FAIL
because the rendered link still points from Chinese Stage 01 to `/tutorial/`.

- [ ] **Step 3: Implement counterpart mapping**

On each Material document load, map known bilingual route families between
`/<relative-page>/` and `/zh/<relative-page>/`, then replace the two top-tab
language links. Keep English-only routes on their existing section targets.

- [ ] **Step 4: Verify GREEN**

Build and serve the docs, then assert both directions for Stage 01 and one
tutorial page with Playwright.

### Task 5: Regenerate, Verify, And Commit

**Files:**
- Regenerate only if renderer-owned indexes change: `docs/journey/index.md`, `docs/zh/journey/index.md`

- [ ] **Step 1: Run all project tests**

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Verify the complete Journey chain**

```bash
python -u journey/tools/build_journey.py --check
```

Expected: Stage 01 through Stage 15, guard-chain, and goal-parity all report
`PASS`.

- [ ] **Step 3: Build documentation strictly**

```bash
uv run mkdocs build --strict
git diff --check
```

Expected: build succeeds and diff check is clean.

- [ ] **Step 4: Browser-verify the direct tutorial**

Use Playwright against the local MkDocs server and assert the Agent page shows
the direct prompt without manual preparation or internal `.journey/` content.

- [ ] **Step 5: Commit the implementation**

```bash
git add .gitignore AGENTS.md README.md README.zh-CN.md docs journey tests
git commit -m "feat: make agent-guided learning direct"
```
