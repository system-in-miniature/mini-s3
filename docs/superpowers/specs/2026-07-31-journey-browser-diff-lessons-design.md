# MiniS3 Journey Browser Diff Lessons Design

## Goal

Turn every bilingual Journey stage into a self-contained browser lesson whose
main line is the S3 mechanism being built. Readers should understand the stage
through its problem, data flow, and actual code increment without requiring an
agent or reading one undifferentiated patch.

## Lesson shape

Each stage page renders in this order:

1. the concrete S3 problem and stage outcome;
2. a compact mechanism/data-flow explanation;
3. a file map ordered by runtime responsibility;
4. one section per changed file with its role, changed symbols, caller/callee
   relationship, failure/debugging point, and a collapsible canonical diff;
5. verification commands and what the tests prove;
6. concept, code-understanding, and interview checks;
7. a final link to the complete canonical patch for audit without duplicating
   every diff in the rendered page.

Tests are evidence at the end of the mechanism walkthrough, not a compulsory
test-first teaching sequence. A stage may naturally be test-heavy (for example
crash characterization), but the site does not force every stage into a
Red/Green/Refactor story.

## Content and rendering

`journey/stages/NN-*/goal.md`, `stage.patch`, and `tests.txt` remain the only
stage facts. The renderer splits `stage.patch` losslessly by file and derives
file roles and changed-symbol anchors from the actual diff. Authored stage
content supplies the source-specific mechanism explanation; generated diff
blocks never duplicate or rewrite code.

Display order follows understanding rather than patch storage order:

- domain values and errors;
- core aggregate/policy;
- persistence and projections;
- application service and public API;
- executable tests;
- packaging/documentation support.

The parser retains canonical order separately, so automated checks can prove
that the generated file slices reconstruct `stage.patch` byte for byte.

## Acceptance

All 15 English and Chinese pages must contain a mechanism overview and exactly
one walkthrough section per patched file. Renderer tests verify lossless patch
splitting, stable ordering, localization, and generated-page parity. Final
acceptance also requires the full repository suite, all-stage Journey chain,
strict MkDocs build, representative desktop/mobile browser inspection, and a
successful public GitHub Pages deployment. Final test parity covers tests owned
by the source-rebuild Journey; site-only documentation tests are verified by
the repository suite but are not injected into the learner tree.
