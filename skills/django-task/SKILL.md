---
name: django-task
description: Implements a bounded Django or Django REST Framework change using the target repository's existing conventions. Triggers after relevant files and expected behavior are known.
---

# django-task

## Purpose

Implement a bounded Django/DRF change while following the target repository's existing conventions.

## Rules

- Do not impose external project conventions unless this repo already uses them.
- Inspect nearby models/views/serializers/services/tests before editing.
- Keep views, serializers, services, selectors, permissions, and models aligned with the repo's current layering.
- Consider migrations only when model schema changes.
- Preserve API compatibility unless the task requires a breaking change.

## Risk checks

- List endpoints need queryset scoping; object permissions alone may not filter lists.
- Multi-step writes may need `transaction.atomic()` depending on existing style.
- Model field changes require migration generation and inspection.
- Relation-heavy responses may need `select_related()` / `prefetch_related()` if query behavior changes.
- Avoid inventing fields, statuses, permissions, or business invariants not supported by source or requirements.
