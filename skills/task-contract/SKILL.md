---
name: task-contract
description: Converts a coding task into a concise implementation contract with acceptance criteria, assumptions, and blocking questions. Triggers before code exploration when requirements are ambiguous or time-boxed.
---

# task-contract

## Purpose

Clarify what must be true when the task is done without turning the task into a long discovery meeting.

## Procedure

1. Restate the task in one sentence.
2. Identify expected observable behavior.
3. Ask at most 1–3 blocking questions whose answers could materially change implementation.
4. Convert unanswered non-blocking details into explicit assumptions.
5. Define the smallest acceptable verification.

## Output

```text
Task contract:
- Goal: <observable behavior>
- Acceptance: <2-4 bullets>
- Blocking questions: <questions or none>
- Assumptions if unanswered: <bullets or none>
- Verification target: <test/check/manual path>
```
