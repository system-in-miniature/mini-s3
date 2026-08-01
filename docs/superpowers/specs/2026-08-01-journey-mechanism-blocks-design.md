# Journey Mechanism Blocks Design

## Goal

Organize each Self-Guided Rebuild Stage around mechanisms rather than treating
every changed file as an equal teaching chapter.

## Page Structure

The walkthrough section becomes `Mechanism blocks` / `机制板块`. Each block has:

1. one conceptual block heading that appears in the page table of contents;
2. a short explanation of the problem boundary and runtime relationship;
3. one collapsed diff drawer per file, in authored block order;
4. the substantive file's explanation immediately after its drawer, without a
   second file-path or `Explanation` label.

The drawer itself is the file-level separator:
`File diff: path` / `文件差异：path`. This keeps the conceptual block as the
only Markdown heading while making each file boundary visible without a
duplicated `Explanation: path` / `讲解：path` line.

## Authored Layout Contract

Every Stage gains `layout.toml`. Its `[[blocks]]` entries define:

- stable block ID;
- English and Chinese titles;
- English and Chinese summaries;
- exact patch files owned by the block;
- whether the block is supporting material.

The renderer rejects missing files, extra files, and duplicate ownership. The
classification is authored per Stage rather than inferred globally from a file
extension. For example, `src/minis3/__init__.py` is supporting wiring in Stage
01 but the core public-API artifact in Stage 15.

## Supporting Changes

A supporting block covers files that are necessary for the repository but do
not deserve a separate conceptual explanation in that Stage, such as an early
README, lockfile, packaging configuration, or a routine export update.

Supporting blocks render only their block summary and per-file diff drawers.
The existing authored per-file prose remains available in the canonical goal
for Agent tutoring and future editing, but the browser page suppresses it.

## Core Changes

Core blocks retain explanations for their member files. Each explanation
follows its own file diff drawer directly. Existing labels such as `What it
is`, `Runtime role`, `Key code`, and `Statement understanding` are rendered as
bold labels, so the table of contents reflects mechanisms rather than file
structure.

## Stage Layout

| Stage | Core blocks | Supporting block |
|---:|---|---|
| 01 | Object value vocabulary | Package and tooling scaffold |
| 02 | Bucket aggregate and deterministic identity | — |
| 03 | Durable publication and recovery | Storage package wiring |
| 04 | Object service boundary | Public export wiring |
| 05 | Version-history projection | Public export wiring |
| 06 | Directory-like listing projection | Public export wiring |
| 07 | Publication failure matrix | — |
| 08 | Directory durability and startup cleanup | — |
| 09 | Multipart completion rules | — |
| 10 | Multipart state; durable staging orchestration | Public export wiring |
| 11 | Atomic multipart completion | — |
| 12 | Multipart publication recovery | — |
| 13 | Conditional matching; guarded service mutation | Public export wiring |
| 14 | Lifecycle policy; clocked lifecycle application | Public export wiring |
| 15 | Explicit public API and parity boundary | — |

## Verification

Automated contracts prove:

- every Stage patch file belongs to exactly one block;
- supporting files have no browser per-file explanation;
- core files remain explained and retain their key-code slices;
- each patch file has one collapsed diff drawer in its owning block;
- each core explanation immediately follows its file drawer without a repeated
  path label;
- file names and explanation labels do not become table-of-contents headings;
- all 15 bilingual pages render, strict MkDocs builds, and the canonical
  Journey reconstruction remains unchanged.
