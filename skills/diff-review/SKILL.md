---
name: diff-review
description: Reviews the final diff for correctness, unintended changes, missing edge cases, and unsupported claims. Triggers before reporting completion when files changed.
---

# diff-review

## Purpose

Perform a final independent review of the changed files before reporting completion.

## Review checklist

- Does the diff satisfy the stated requirement?
- Are there unintended refactors or formatting-only changes?
- Are edge cases, permissions, validation, and error behavior handled where relevant?
- Are tests aligned with behavior rather than implementation details?
- Does any new assertion depend on a literal threshold/count? If so, was it derived from an observed run (not guessed), and does it fail pre-fix / pass post-fix for the stated reason?
- Were checks actually run and accurately reported, with the exact command stated verbatim?
- Are there unsupported assumptions to disclose?
- Does any new comment restate the code, narrate this specific change ("fixed for X", "per the bug report"), or reference task/PR context? That belongs in the commit message, not the code — remove it. A comment only earns its place if it explains something the code can't: a constraint, invariant, or non-obvious workaround.

## Review style

- Defect-first: prioritize correctness, data boundaries, security, compatibility, and regression risks.
- Avoid style-only comments that should be handled by formatter/linter.
- Findings should be concrete and actionable.
