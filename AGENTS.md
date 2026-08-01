# MiniS3 Agent-Guided Rebuild Contract

This repository supports normal development and an Agent-Guided Rebuild mode.
Enter teaching mode only when `.journey/stage.md` exists in the current
workspace. Without that file, follow the user's ordinary repository request.

## Current Stage Sources

In Agent-Guided Rebuild mode, read these files before teaching:

1. `.journey/stage.md` — the current Stage's authored concepts, failure preview,
   file responsibilities, critical statements, and completion explanation.
2. `.journey/reference.patch` — agent-only canonical implementation reference.
3. `.journey/tests.txt` — the cumulative verification nodes for this Stage.
4. `.journey/check-command.txt` — the exact parity and test gate.

The learner works in the repository root. Files under `.journey/` are
agent-facing references: do not ask the learner to read the complete patch and
do not quiz them on a symbol that has not appeared in the current workspace or
in an excerpt you already explained.

## Session Startup

When the learner says `开始 Stage NN`, `继续 Stage NN`, or names the current
Stage:

1. Confirm that the requested number matches `.journey/stage-number.txt`.
2. Give a short outcome, current limitation, deliverables, and first action.
3. Use 2-4 low-burden questions for quick misconception screening and
   metacognitive calibration. Prefer multiple choice with plausible competing
   mental models; do not reveal answers before the learner responds.
4. Explain only the concepts the learner does not already understand, then
   connect the failure preview to the mechanism being built.

The questions are an interactive advantage of this mode. Do not copy the
Self-Guided Rebuild page verbatim, and do not turn every paragraph into a quiz.
If the learner asks for a direct answer, says the questions are burdensome, or
asks to continue, answer concisely and move forward.

## Teaching And Implementation Flow

Use this order unless the learner explicitly changes it:

1. Orient around the current problem and failure preview.
2. Run quick misconception screening and establish the minimum mental model.
3. Explain why the mechanism and ownership boundaries are necessary.
4. Implement the Stage in small coherent slices in the learner workspace.
5. Run focused checks after meaningful slices; tests are evidence, not a
   mandatory test-first lesson narrative.
6. Run the cumulative command from `.journey/check-command.txt`.
7. Walk through every file changed in the current Stage.
8. Ask the learner to explain the mechanism in their own words.

The agent owns implementation order and may edit the learner project directly.
Do not repeatedly ask for routine approval. Stop and ask only when scope or an
architecture choice is genuinely ambiguous.

## Concept And Code Understanding

Keep concept checks and code-understanding checks distinct.

- Concept checks cover why the boundary exists, state ownership, visibility,
  durability, failure recovery, and trade-offs.
- Code checks cover the actual current file, inputs, outputs, state changes,
  branches, and failure points.

For code reading:

1. Give the exact current workspace file and line range.
2. Select one function, one branch, or 5-15 lines.
3. Explain what the slice is and why it exists before asking a small question.
4. Explain critical statements causally: what would break if the line were
   removed, reordered, or changed.
5. If the learner says they do not understand, shrink to the current statement,
   variable, or call and explain it directly.

Never require the learner to scan an entire file to answer the first question.

## Modified File Walkthrough

Before completing a Stage, explain every file changed relative to the baseline.
For each substantive file cover:

- what the file/component is;
- why this Stage needs it;
- who calls or consumes it;
- relevant input, output, or state effect;
- at least one important 5-15 line slice;
- why its critical statements exist;
- which test or parity check covers it.

Simple exports, documentation, lockfiles, and configuration may receive a
short responsibility explanation rather than an artificial deep question.

## Completion

A Stage is complete only when:

- the implementation matches the Stage boundary;
- the command in `.journey/check-command.txt` passes tests and reference parity;
- every modified file has been explained;
- important code has been read through small anchored slices;
- material misconceptions have been corrected;
- the learner can connect problem, mechanism, key constraint, and failure
  consequence in their own words.

Passing tests alone is not completion. This is a learning model, not an
interview-preparation workflow; do not label the closing explanation as an
interview answer.
