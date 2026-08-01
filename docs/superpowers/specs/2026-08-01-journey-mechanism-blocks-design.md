# Journey Mechanism Blocks Design

## Goal

Organize each Self-Guided Rebuild Stage around mechanisms rather than treating
every changed file as an equal teaching chapter.

## Page Structure

The walkthrough section becomes `Mechanism blocks` / `机制板块`. Each block has:

1. one conceptual block heading that appears in the page table of contents;
2. a short explanation of the problem boundary and runtime relationship;
3. one collapsed drawer containing the combined diffs for every file in the
   block;
4. optional explanations for substantive files, rendered with inline file
   labels and inline explanation labels rather than additional headings.

The drawer label is an action, not a duplicate title:
`View block diff (N files)` / `查看本板块差异（N 个文件）`.

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

Supporting blocks render only their block summary and combined diff drawer.
The existing authored per-file prose remains available in the canonical goal
for Agent tutoring and future editing, but the browser page suppresses it.

## Core Changes

Core blocks retain explanations for their member files. File paths are shown as
bold inline labels rather than headings. Existing labels such as `What it is`,
`Runtime role`, `Key code`, and `Statement understanding` are also rendered as
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
- each block has one collapsed combined diff drawer immediately after its
  summary;
- file names and explanation labels do not become table-of-contents headings;
- all 15 bilingual pages render, strict MkDocs builds, and the canonical
  Journey reconstruction remains unchanged.
