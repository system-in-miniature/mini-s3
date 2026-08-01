# Journey Teaching Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite all 15 bilingual Journey stages as complete browser-native lessons that establish concepts and necessity before explaining every changed file and its critical statements.

**Architecture:** Keep each stage's `goal.md` as the human-authored bilingual lesson source. Replace renderer-generated teaching prose with a validated parser that binds authored file sections and key code slices to each canonical `stage.patch`, while retaining complete per-file diffs as collapsed audit references.

**Tech Stack:** Python 3.12, `dataclasses`, standard-library `re`/`pathlib`, `unittest`/pytest, MkDocs Material, bilingual Markdown.

---

## File Structure

- Modify `journey/tools/render_pages.py`: parse the richer authored lesson contract, validate file coverage and key slices, and render complete diffs beside authored explanations.
- Modify `journey/tools/tests/test_render_pages.py`: replace generic-prose expectations with required-section, file-binding, key-slice, ordering, and anti-boilerplate contracts.
- Modify `journey/stages/01-scaffold-object-model/goal.md` through `journey/stages/15-public-api-parity/goal.md`: author the English and Chinese lesson content for every stage.
- Modify `journey/README.md`: document the browser lesson order and authoring/source-of-truth boundary.
- Regenerate `docs/journey/stage-01.md` through `docs/journey/stage-15.md` and `docs/zh/journey/stage-01.md` through `docs/zh/journey/stage-15.md`.
- Regenerate `docs/journey/index.md` and `docs/zh/journey/index.md` if renderer wording changes.
- Preserve the existing uncommitted `mkdocs.yml` navigation-folding edit and include it only in the final implementation commit after verification.

## Authored Markdown Contract

Each `## English` and `## 中文` body must contain these headings in order:

```markdown
### Goal / 目标
### Deliverable files / 交付文件
### The problem at this point / 当前遇到的问题
### Basic concepts / 基本概念
### Why this mechanism is necessary / 为什么需要这个机制
### Runtime mental model / 运行时心智模型
### File-by-file walkthrough / 逐文件走读
### Verification evidence / 验证证据
### Durable takeaways / 需要真正记住的内容
### Interview-ready summary / 面试表达
### Textbook / 教材
```

Inside the walkthrough, every canonical patch path is introduced exactly once with a machine-readable comment followed by the visible file heading:

````markdown
<!-- journey-file: src/minis3/model.py -->
#### `src/minis3/model.py`

##### What it is and why it appears / 是什么，为什么现在需要

...

##### Runtime role / 在运行时做什么

...

##### Key code / 关键代码

```python
def content_etag(body: bytes) -> str:
    return f'"{md5(body).hexdigest()}"'
```

##### Statement understanding / 关键语句理解

...
````

Key-code blocks are required for substantive source and test files. They are optional for package exports, documentation, lockfiles, and small configuration-only changes. A key-code block is 1-15 nonblank lines and must match the corresponding stage's post-patch content after diff markers are removed.

## Stage Content Map

The authored lessons must cover these stage-specific mental models and critical statements:

| Stage | Problem and necessity | Critical code focus |
|---:|---|---|
| 01 | Python package plus immutable whole-object values; keys remain opaque rather than directories | quoted content MD5, frozen value objects, delete marker without body |
| 02 | one aggregate must own legal versioning transitions and reproducible IDs | `VersioningState`, injected monotonic sequence, unversioned/enabled/suspended `put` and `delete` branches |
| 03 | memory state disappears on restart; visibility and durability need separate owners | temp write/flush/fsync/replace/parent-fsync order, immutable artifacts, manifest published last, recovery trusts references |
| 04 | domain and storage pieces need one locked public service boundary | lock ownership, bucket lookup, mutate-then-persist orchestration, HEAD reusing GET semantics, delete error paths |
| 05 | current-object reads cannot represent null versions, named versions, and markers | flattening histories, latest calculation, marker/value distinction |
| 06 | flat keys must produce a directory-like projection without becoming directories | prefix/delimiter projection, combined page counting, query-bound opaque continuation token |
| 07 | crash claims require evidence on both sides of the manifest rename | injected crash points and old-state/new-state assertions around the linearization point |
| 08 | file fsync alone does not persist directory entries; restart must remove debris | parent-chain fsync recording, temporary/orphan cleanup, referenced artifact preservation |
| 09 | multipart needs identity, staged part receipts, ordered completion rules, and composite ETag semantics | part-number validation, ordered manifest validation, nonfinal minimum size, binary-MD5 composite ETag |
| 10 | uploaded parts must survive restart but remain invisible to normal object reads | upload directory identity, atomic part replacement, recovery of staging without `ObjectRecord` publication |
| 11 | completion must validate, assemble, and publish one object atomically | ordered receipt validation, concatenation, composite ETag, publish before staging removal |
| 12 | completion crashes require different recovery before and after publish | pre-publish retryable upload versus post-publish visible object and staging cleanup |
| 13 | ETags become HTTP validators and serialized compare-and-swap guards | wildcard/list matching, 304 versus 412 semantics, precondition evaluation inside the service lock |
| 14 | policy evaluation should be pure while mutation happens only on explicit ticks | injected clock, inclusive thresholds, current-to-marker transition, physical noncurrent deletion |
| 15 | a teaching reconstruction is complete only when public exports and stage-built bytes match main | explicit `__all__` surface and byte-for-byte Journey parity boundary |

## Task 1: Lock the richer renderer contract with failing tests

**Files:**
- Modify: `journey/tools/tests/test_render_pages.py`

- [ ] **Step 1: Replace generic mechanism assertions with required authored-section assertions**

Add localized heading tables and assert the headings exist in order for all 15 cards. The English sequence begins with `### The problem at this point`; the Chinese sequence begins with `### 当前遇到的问题`.

- [ ] **Step 2: Add exact authored-file coverage tests**

For both languages, compare the `journey-file` paths parsed from the lesson with `split_file_patches(card.patch)`. Assert equal sets, no duplicates, and one rendered walkthrough per path.

- [ ] **Step 3: Add key-code validation tests**

Create unit fixtures for a matching code slice, a slice longer than 15 nonblank lines, and a slice absent from the corresponding file patch. Assert the latter two raise `ValueError` containing the stage number and file path.

- [ ] **Step 4: Add teaching-order and anti-boilerplate tests**

Assert concepts and necessity precede the first `journey-file`, verification follows the last file, and rendered pages no longer contain generated phrases such as `Supporting project wiring for this stage`, `本阶段所需的项目支撑接线`, or the generic question `Which test would fail first`.

- [ ] **Step 5: Run the renderer tests and confirm RED**

Run:

```bash
uv run pytest -q journey/tools/tests/test_render_pages.py
```

Expected: failures for missing parsing helpers and old stage content.

- [ ] **Step 6: Commit the contract tests**

```bash
git add journey/tools/tests/test_render_pages.py
git commit -m "test: define authored Journey lesson contract"
```

## Task 2: Implement authored lesson parsing and validation

**Files:**
- Modify: `journey/tools/render_pages.py`

- [ ] **Step 1: Add localized lesson and file-section models**

Introduce immutable models equivalent to:

```python
@dataclass(frozen=True)
class FileLesson:
    path: str
    body: str
    code_slices: tuple[str, ...]


@dataclass(frozen=True)
class LocalizedLesson:
    pre_walkthrough: str
    files: tuple[FileLesson, ...]
    post_walkthrough: str
```

- [ ] **Step 2: Parse exact `journey-file` markers**

Use `<!-- journey-file: PATH -->` as the binding source. Reject a marker without the matching immediate visible heading, duplicate paths, an empty body, or no markers.

- [ ] **Step 3: Validate required heading order**

Define exact English and Chinese heading tuples from the authored Markdown contract. Reject missing, duplicate, or out-of-order headings with a stage- and language-specific error.

- [ ] **Step 4: Reconstruct comparable post-patch lines per file**

For each unified diff hunk, retain context lines and added lines, drop deleted lines and diff metadata, and preserve source order. Normalize only trailing whitespace and the final newline for code-slice comparison.

- [ ] **Step 5: Extract and validate key-code blocks**

Only fenced blocks under `##### Key code` or `##### 关键代码` count as authored key slices. Reject slices over 15 nonblank lines or slices that do not occur contiguously in the reconstructed corresponding file content.

- [ ] **Step 6: Replace generic rendering with authored rendering**

Remove `file_role`, `file_flow`, synthesized changed-anchor prose, generated concept questions, and generated code-reading questions. Render the authored body for each file, then append its complete canonical diff in the existing collapsed block.

- [ ] **Step 7: Keep deterministic closeout facts only**

Render the authored verification and takeaways directly. Retain only deterministic link, checkout, patch, and command construction where the stage source intentionally delegates those facts to the renderer.

- [ ] **Step 8: Run focused tests**

```bash
uv run pytest -q journey/tools/tests/test_render_pages.py
```

Expected: parser fixture tests pass; all-stage content tests remain red until Tasks 3-5 author every stage.

- [ ] **Step 9: Commit the renderer implementation**

```bash
git add journey/tools/render_pages.py
git commit -m "feat: render authored Journey explanations"
```

## Task 3: Author foundational stages 01-05

**Files:**
- Modify: `journey/stages/01-scaffold-object-model/goal.md`
- Modify: `journey/stages/02-bucket-state/goal.md`
- Modify: `journey/stages/03-durable-storage-boundary/goal.md`
- Modify: `journey/stages/04-object-service/goal.md`
- Modify: `journey/stages/05-version-history/goal.md`

- [ ] **Step 1: Author Stage 01 in both languages**

Explain bytes versus metadata, content-derived quoted ETags, opaque keys, immutable records, and delete markers before file reading. Walk through every patch file and explain the MD5 expression, frozen dataclasses, body-less marker, public exports, tests, and packaging artifacts.

- [ ] **Step 2: Author Stage 02 in both languages**

Explain aggregate ownership, versioning states, null versus named IDs, and injected sequencing. Walk through the state-transition branches and why deterministic IDs make histories and tests reproducible.

- [ ] **Step 3: Author Stage 03 in both languages**

Separate atomic visibility from crash durability. Explain `flush`, file `fsync`, `os.replace`, parent-directory `fsync`, immutable artifacts, publish-last manifest, and manifest-led recovery using small slices from `atomic.py` and `disk.py`.

- [ ] **Step 4: Author Stage 04 in both languages**

Explain why the service owns locking and orchestration while Bucket and DiskStorage retain their own responsibilities. Cover the public operation flow, mutate/persist order, restart counter restoration, and meaningful failure branches.

- [ ] **Step 5: Author Stage 05 in both languages**

Explain why a current-value API loses history semantics. Walk through projection objects, flattening order, `is_latest`, and the distinction among null versions, named versions, and delete markers.

- [ ] **Step 6: Run focused validation and commit**

```bash
uv run pytest -q journey/tools/tests/test_render_pages.py
git add journey/stages/0{1,2,3,4,5}-*/goal.md
git commit -m "docs: teach Journey foundations before code"
```

Expected test state: stages 01-05 satisfy the new contract; the suite reports remaining stages as incomplete.

## Task 4: Author listing, crash, and multipart foundations 06-10

**Files:**
- Modify: `journey/stages/06-directory-illusion/goal.md`
- Modify: `journey/stages/07-publication-crash-matrix/goal.md`
- Modify: `journey/stages/08-fsync-recovery/goal.md`
- Modify: `journey/stages/09-multipart-domain/goal.md`
- Modify: `journey/stages/10-multipart-staging/goal.md`

- [ ] **Step 1: Author Stage 06 in both languages**

Explain flat-key projection, delimiter-derived common prefixes, page accounting across two result types, and why the continuation token must bind offset, prefix, and delimiter.

- [ ] **Step 2: Author Stage 07 in both languages**

Explain linearization points and crash matrices before the test files. For each crash test, identify setup, injection point, restart observation, and why pre-rename old state and post-rename new state are the only valid outcomes.

- [ ] **Step 3: Author Stage 08 in both languages**

Explain directory entries as durability state, parent-chain fsync, and the difference among temporary, orphaned, and manifest-referenced files. Walk through tests as executable recovery evidence rather than TDD instructions.

- [ ] **Step 4: Author Stage 09 in both languages**

Explain multipart upload identity, staged parts, client completion manifests, part ordering/size rules, and composite ETags. Explain why binary MD5 digests are concatenated before the final hash.

- [ ] **Step 5: Author Stage 10 in both languages**

Explain durable-but-invisible staging, atomic replacement of the same part number, upload directory identity, and restart recovery that does not publish an object record.

- [ ] **Step 6: Run focused validation and commit**

```bash
uv run pytest -q journey/tools/tests/test_render_pages.py
git add journey/stages/{06-directory-illusion,07-publication-crash-matrix,08-fsync-recovery,09-multipart-domain,10-multipart-staging}/goal.md
git commit -m "docs: deepen Journey storage and multipart lessons"
```

Expected test state: stages 01-10 satisfy the authored contract; only stages 11-15 remain incomplete.

## Task 5: Author completion, conditions, lifecycle, and parity 11-15

**Files:**
- Modify: `journey/stages/11-multipart-complete/goal.md`
- Modify: `journey/stages/12-multipart-recovery/goal.md`
- Modify: `journey/stages/13-conditional-cas/goal.md`
- Modify: `journey/stages/14-lifecycle-tick/goal.md`
- Modify: `journey/stages/15-public-api-parity/goal.md`

- [ ] **Step 1: Author Stage 11 in both languages**

Explain ordered completion as validation plus assembly plus one publication. Walk through receipt matching, nonfinal size checks, concatenation, composite ETag, and why staging cleanup occurs only after publication succeeds.

- [ ] **Step 2: Author Stage 12 in both languages**

Explain the two-sided recovery contract. Walk through the pre-publish test that keeps a retryable upload and the post-publish test that recovers the object then removes stale staging.

- [ ] **Step 3: Author Stage 13 in both languages**

Explain validators, preconditions, 304 versus 412, wildcard semantics, and CAS. Highlight that the current ETag lookup and precondition check execute under the same service lock as mutation.

- [ ] **Step 4: Author Stage 14 in both languages**

Explain pure policy versus explicit mutation, injected time, inclusive expiry thresholds, marker creation for current values, physical deletion for noncurrent values, and persistence after a tick.

- [ ] **Step 5: Author Stage 15 in both languages**

Explain public API curation and byte-for-byte reconstruction parity. Walk through exports and parity checks without pretending that a generic README or import success proves behavioral parity.

- [ ] **Step 6: Run the full renderer contract and commit**

```bash
uv run pytest -q journey/tools/tests/test_render_pages.py
git add journey/stages/{11-multipart-complete,12-multipart-recovery,13-conditional-cas,14-lifecycle-tick,15-public-api-parity}/goal.md
git commit -m "docs: complete deep Journey lessons"
```

Expected: all renderer tests pass for all 15 bilingual stages.

## Task 6: Regenerate pages and update Journey authoring documentation

**Files:**
- Modify: `journey/README.md`
- Modify: `docs/journey/index.md`
- Modify: `docs/zh/journey/index.md`
- Modify: `docs/journey/stage-01.md` through `docs/journey/stage-15.md`
- Modify: `docs/zh/journey/stage-01.md` through `docs/zh/journey/stage-15.md`

- [ ] **Step 1: Update the Journey README**

State that each page explains the current problem, concepts, necessity, runtime flow, key file slices, full reference diffs, and verification in that order. Explicitly state that the browser course does not require live Q&A and does not use test-first as its default narrative.

- [ ] **Step 2: Regenerate all browser pages**

```bash
python journey/tools/render_pages.py
```

Expected: `rendered 15 bilingual Journey stages`.

- [ ] **Step 3: Inspect representative generated pages**

Check stages 01, 03, 07, 11, and 15. Confirm that concepts precede files, each key slice has statement-level explanation, each canonical file appears once, and full diffs remain collapsed.

- [ ] **Step 4: Run documentation and renderer checks**

```bash
uv run pytest -q journey/tools/tests/test_render_pages.py tests/test_docs_homepage.py
uv run mkdocs build --strict
git diff --check
```

Expected: all tests pass, MkDocs builds without warnings, and diff check is clean.

- [ ] **Step 5: Commit generated lessons and documentation**

```bash
git add journey/README.md docs/journey docs/zh/journey
git commit -m "docs: publish complete Journey lessons"
```

## Task 7: Full parity, regression, and local browser acceptance

**Files:**
- Verify: `journey/stages/**`
- Verify: `journey/tools/**`
- Verify: `docs/journey/**`
- Verify: `docs/zh/journey/**`
- Include existing change: `mkdocs.yml`

- [ ] **Step 1: Run the complete automated suite**

```bash
uv run pytest -q
python journey/tools/build_journey.py --check
uv run mkdocs build --strict
git diff --check
```

Expected: all pytest tests pass, Journey reports full source/test parity, MkDocs succeeds without warnings, and no whitespace errors are reported.

- [ ] **Step 2: Restart the local preview on the accepted port**

Run the site at `http://127.0.0.1:8123/mini-s3/`, replacing only the existing MiniS3 preview process if necessary. Do not stop unrelated local services.

- [ ] **Step 3: Perform browser acceptance**

Inspect the Chinese Journey index and stages 01, 03, 07, 11, and 15 at desktop width. Confirm the two navigation groups remain collapsible, code/admonition blocks render correctly, long diffs default closed, and no authored content is hidden by malformed Markdown.

- [ ] **Step 4: Check the final worktree and commit the navigation change**

```bash
git status --short
git diff --check
git add mkdocs.yml
git commit -m "docs: keep Journey navigation groups collapsible"
```

Expected: only intentional implementation artifacts are committed; no generated cache, site output, or unrelated user files are staged.

- [ ] **Step 5: Report acceptance evidence**

Report the local URL, exact test/parity/build results, representative pages inspected, commit hashes, and any intentionally preserved process. Do not claim completion if any stage lacks authored bilingual explanations or any parity/build check fails.
