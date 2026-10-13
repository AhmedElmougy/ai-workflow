**Precedence**: if this repo already has an established pattern for this (check nearby files first), follow the repo's pattern — don't impose this instead. This file is my own default style, used only where no local convention is already set.

- All methods `@staticmethod`. No `self`/`cls` state.
- Writes wrapped in `@transaction.atomic`.
- Always call `instance.full_clean()` before `save()`.
- Use `save(update_fields=[...])` on updates — never bare `save()`.
- Raise `XxxServiceError` (subclass of a shared `ServiceError`) for all business-rule failures.
- Inline imports only to break circular dependencies — see `imports.md`.
- No ORM queries beyond object construction — reads delegate to a selector where this repo has that layer; otherwise follow wherever this repo currently puts reads (e.g. a `list()`/`get()` on the service class itself, as `maintenance/services.py` already does).

Pattern:

```python
class FooService:
    @staticmethod
    @transaction.atomic
    def create(name: str) -> "Foo":
        from src.foo.validators import FooValidator  # avoid circular import
        FooValidator.validate_name_unique(name)
        instance = Foo(name=name)
        instance.full_clean()
        instance.save()
        return instance
```
