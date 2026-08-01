# Journey Teaching Depth Design

Date: 2026-07-31

## Purpose

Turn all 15 MiniS3 Journey stages from generated diff indexes into complete browser-native lessons. A learner must understand the problem, minimum concepts, necessity, runtime flow, and important statements before using the full patch as a reference.

The browser lesson does not have a live tutor performing MCQ screening or adapting questions. It therefore must establish the learner's mental model directly in the authored explanation instead of asking the learner to infer missing concepts.

## Three Learning Modes

MiniS3 presents three distinct paths:

1. **Mechanism Tutorial** teaches the system by topic through the original tutorial chapters.
2. **Self-Guided Rebuild** is the 15-Stage browser Journey defined by this design.
3. **Agent-Guided Rebuild** prepares a Stage N-1 CLI workspace with `AGENTS.md` and agent-only Stage N context for adaptive questions, implementation, guided code reading, and parity verification.

The Agent-Guided web page is only a usage tutorial. It must not duplicate Stage explanations or become a fourth source of course content. Interactive behavior belongs to `AGENTS.md`; Stage-specific facts remain in `goal.md`, `stage.patch`, and `tests.txt`.

## Scope

This redesign applies to every English and Chinese Journey page from Stage 01 through Stage 15.

It changes:

- the authored lesson content in every stage `goal.md`;
- the rendering contract in `journey/tools/render_pages.py`;
- renderer tests and generated Journey pages;
- Journey authoring documentation when needed to describe the new contract.

It preserves:

- the 15-stage sequence and existing stage boundaries;
- canonical `stage.patch` and `tests.txt` artifacts;
- cumulative source and test parity;
- bilingual output;
- the complete per-file diff as a collapsible reference;
- the existing local navigation-folding change in `mkdocs.yml`.

It does not introduce test-first teaching as the page narrative. Tests appear after the mechanism and code walkthrough as verification evidence.

## Evidence From Existing Teaching Sessions

The Oncall Agent and Gulimall teaching sessions use interaction to establish understanding before broad code reading:

- state the day's concrete problem and boundary;
- establish a minimum mental model before asking for implementation details;
- distinguish concept and design understanding from code understanding;
- give an exact file and a small code slice before discussing code;
- explain the slice first, then use a low-cost check when interaction is available;
- shrink the slice to the current statement or variable when the learner is confused;
- explain every modified file by responsibility, dependency, and verification evidence.

The Journey has no adaptive conversation. It must encode the explanatory half of that teaching flow directly and omit mandatory live-question loops.

## Rejected Approaches

### More renderer heuristics

Deriving prose from a path or changed symbol is useful for navigation but cannot explain why a branch, ordering constraint, field, or API call exists. It would preserve the current generic quality.

### Separate YAML or JSON lesson manifests

A structured manifest would make validation straightforward, but long bilingual explanations and code commentary would be difficult to author and review. It would also split each lesson across more artifacts without improving the learner experience.

## Selected Content Model

Each stage keeps `goal.md` as its human-authored bilingual lesson source. The renderer combines that source with the canonical per-file sections from `stage.patch`.

The renderer may automate deterministic facts such as file ordering, complete diff inclusion, test names, links, and commands. It must not generate conceptual explanations or key-statement meaning from file names and symbols.

Every localized stage lesson uses this order:

1. Goal and deliverable files.
2. The problem at this point in the journey.
3. One high-signal failure preview from the stage's executable contracts.
4. Basic concepts.
5. Why the mechanism is necessary.
6. Runtime mental model and failure path.
7. File-by-file walkthrough.
8. Verification evidence.
9. Durable takeaways and an explanation in the learner's own words.

## Section Contract

### The problem at this point

Explain what the previous stage can already do, the concrete limitation now encountered, and the capability this stage adds. The explanation must be specific enough that the learner knows why these files appear today.

### Basic concepts

Define each new term in project language. For each important concept, state what it is, what it is not when a likely misconception exists, and give a small MiniS3-specific example.

The section is explanatory, not a hidden quiz. It cannot depend on the learner opening the patch first.

### Failure preview

Select one stage-owned test scenario that makes the current limitation concrete. Show the input, failure, crash boundary, or conflicting outcomes in a small excerpt or compact scenario, then explain which behavior the contract locks down.

This is executable motivation, not a full RED-GREEN tutorial. Do not move the entire test suite ahead of the lesson or teach testing-framework mechanics here. The complete evidence remains in the verification section after the walkthrough.

### Why this mechanism is necessary

Explain the failure or semantic gap that exists without the mechanism, why a simpler-looking alternative is insufficient, and how the mechanism corresponds to real S3 or storage-system behavior.

### Runtime mental model

Trace one representative operation from its public entry through the owning components. Identify inputs, outputs, state changes, the visibility or durability point, and the first useful debugging boundary.

Use a compact textual flow or Mermaid diagram only when it materially clarifies a flow involving at least three boundaries.

### File-by-file walkthrough

Read files in runtime-responsibility order, not patch-storage order. Every changed file appears exactly once.

For each substantive source or test file, the authored explanation includes:

- what the file or component is;
- why it is introduced or changed in this stage;
- who calls or consumes it;
- its relevant inputs, outputs, or state effects;
- one or more meaningful 5-15 line slices when the file contains key behavior;
- an explanation of the important statements in those slices;
- the failure or debugging point when relevant;
- the verification evidence that covers it.

Key-statement explanations must address causality. Examples include why an operation must occur before another one, why a field is preserved, why a branch exists, or which invariant an exception protects. Merely restating syntax is insufficient.

Simple exports, package metadata, lockfiles, and short configuration files may use a concise responsibility explanation. They do not require an artificial code-reading exercise.

After the authored walkthrough, the complete canonical file diff remains in a collapsed block. The diff is an audit and comparison artifact, not the primary lesson.

### Verification and closeout

Verification appears after the walkthrough. It states what the stage tests prove and any important property they do not prove. It does not frame the stage as a TDD exercise.

The lesson then closes with:

- the mechanism and invariant the learner should retain;
- likely confusions already answered in prose;
- a concise explanation the learner can reproduce in their own words, organized as problem, mechanism, constraint, and failure consequence.

This closing structure may reuse the compression discipline of interview practice, but the Journey is a learning model rather than an interview-preparation product. Learner-facing headings and prose must not frame the lesson as interview training.

Static optional reveal blocks may summarize an answer, but the page must not rely on an unanswered MCQ or open question to introduce required knowledge.

## Rendering Responsibilities

`render_pages.py` remains responsible for:

- loading and validating stage metadata;
- rendering bilingual pages;
- ordering canonical file diffs by runtime responsibility;
- including every changed file exactly once;
- rendering canonical commands, links, and complete diffs;
- rejecting missing required authored sections.

It is no longer responsible for synthesizing file roles, file flows, conceptual checks, or key-code meaning from generic mappings.

The stage source must bind each authored file walkthrough to an exact path. Renderer validation fails when a canonical changed file has no walkthrough or a walkthrough names a file absent from the patch.

Authored code slices must be traceable to the corresponding stage patch. Validation should normalize diff markers and verify that each quoted slice exists in that stage's resulting file content or changed hunk. This prevents explanations from drifting away from the canonical stage.

## Content Quality Rules

Across all 15 stages:

- explanations must be stage-specific rather than reusable boilerplate;
- required concepts appear before the first file walkthrough;
- code slices remain small enough to understand without reading the whole file;
- each critical statement explanation says why it exists;
- tests are explained as evidence after implementation mechanics;
- source-like ownership boundaries remain explicit;
- fake, local, durable, and public-API claims are not collapsed into one proof level;
- English and Chinese pages teach the same mechanism, though wording may be idiomatic rather than line-for-line translation.

## Validation

Automated checks must prove:

- all 15 stages contain every required localized section;
- every canonical changed file has exactly one authored walkthrough;
- no walkthrough refers to a non-stage file;
- every displayed full diff is byte-for-byte sourced from `stage.patch`;
- authored key code slices match the stage patch;
- verification follows the code walkthrough;
- generated pages contain no implementation-first instruction or required unanswered concept quiz;
- Journey build parity and the existing repository test suite remain green.

Manual browser acceptance will inspect representative stages from the beginning, middle, and end of the journey, including a small domain stage and a large persistence or multipart stage. Acceptance focuses on whether a learner can explain why the stage exists and understand its critical statements without opening another document.

## Completion Criteria

The redesign is complete only when all 15 bilingual stages satisfy the new contract. A partially upgraded set of sample stages is not considered complete.
