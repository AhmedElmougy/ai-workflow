---
name: project-memory
description: Records durable, verified project knowledge outside the critical coding path. Triggers only when a discovery will help future tasks.
---

# project-memory

## Purpose

Maintain durable, verified project knowledge outside the critical coding path.

## Store only

- Non-obvious architecture facts.
- Verified gotchas and workarounds.
- Stable commands that worked.
- Business invariants supported by source/tests.
- Decisions likely to matter in future sessions.

## Do not store

- Routine task summaries.
- Guesses or unverified claims.
- Large code excerpts.
- Facts already obvious from filenames.
- One-off temporary implementation details.

## Required note shape

```md
## <topic>

- Status: verified | hypothesis | stale
- Source: `<path>` / `<test>`
- Fact: <concise durable fact>
- Reconsider when: <condition>
```
