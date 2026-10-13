# Coding Companion Workflow

## Principles

- Source code and passing tests are authoritative.
- Keep context small: load only the map/rule/skill needed now.
- Follow repo conventions before generic preferences.
- Prefer small, reviewable diffs.
- Minimize blast radius: don't touch adjacent code beyond this task. Note other issues as follow-ups, don't expand scope.
- Never claim checks passed unless they ran and passed.
- Ask before significant external side effects.
- **IMPORTANT — hard rule: never run `git commit` (any repo, including outside this project) without explicit permission first.** Staging/showing a diff is fine; committing is not, until the user says so for that specific commit.

## Modes

Default: normal coding companion.

Modifiers:
- `timebox=<minutes>` — compress scope/checks to fit.
- `context=interview` — concise, decision-focused, skip nonessential memory.
- `context=research` — no edits unless asked.
- `context=maintenance` — allow deeper cleanup and broader checks.

## Task loop

1. Clarify goal, constraints, edge cases, acceptance criteria; ask only blocking questions.
2. If `/repo-init` wasn't run yet (no `.ai/repo-map.md`, or an empty tooling section), say so and suggest it — don't self-trigger it.
3. Explore with `repo_lookup` first, or fallback: `python3 .ai/scripts/repo_lookup.py "<task terms>"`.
4. Read returned source/tests; `.ai/repo-map.md`, `rg`, or Graphify only if lookup is insufficient.
5. Plan the smallest useful change and verification target.
6. State that plan in 1-2 sentences before implementing — catches a wrong approach before a diff exists.
7. Implement one coherent diff; copy existing patterns.
8. Verify with the narrowest meaningful check first — lint/format is enforced automatically by the `Stop` hook, not a separate step here.
9. Review the diff: correctness, unintended edits, missing edge cases, unsupported assumptions, and scope — revert anything the stated plan wouldn't predict.
10. Report changes, actual checks, assumptions, and risks.

## Skill triggers

Load at most one skill at a time. Skills are procedures, not source of truth.

| Situation | Load | Skip when |
|---|---|---|
| Requirements unclear | `.ai/skills/task-contract/SKILL.md` | Task is precise |
| Need files/tests | `.ai/skills/repo-explore/SKILL.md` | Exact file/test is known |
| Django/DRF change | `.ai/skills/django-task/SKILL.md` | Not Django/DRF |
| Need verification | `.ai/skills/targeted-test/SKILL.md` | No behavior changed |
| Before final with diff | `.ai/skills/diff-review/SKILL.md` | Research-only/no diff |
| Durable discovery | `.ai/skills/project-memory/SKILL.md` | Interview/timebox/routine summary |
| Scaling/Celery/Redis/system-design question | `.ai/skills/scale-defense/SKILL.md` | Routine CRUD, no scaling angle |

Prefer explicit invocation: "use the `<skill-name>` skill".

## Comments

Default to zero new comments. Deletion test: if removing a comment loses no information, delete it.

- Never: restate code, narrate intent, section banners, step labels, edit markers (`added`/`NEW`), signature-echo docstrings, dead code.
- Keep only: non-obvious WHY (constraint/invariant/workaround/precondition), one short line, scoped to this edit.
- Can't comment it clearly? Rename/restructure instead of explaining.

## Memory

Update `.ai/memory/MEMORY.md` or an area file only for durable, verified, non-obvious facts: architecture, invariants, stable commands, gotchas, decisions. Not transcripts, guesses, duplicates, or routine summaries.

## Final response

- Changed: files/behavior.
- Verified: command/result, or blocker.
- Assumptions/risks.
- Follow-up only if useful.
