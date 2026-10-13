**Precedence**: if this repo already has an established pattern for this (check nearby files first), follow the repo's pattern — don't impose this instead. This file is my own default style, used only where no local convention is already set.

All imports go at the TOP of the file. Standard order: stdlib → third-party → first-party.

The ONLY exception is a circular import. In that case, move the import inside the function/method and add a comment:

```python
def clean(self) -> None:
    from src.foo.validators import FooValidator  # avoid circular import
    FooValidator.validate(self)
```

Every other reason for an inline import is rejected.

## Other Python conventions

- Avoid broad exception catches unless the project already uses them at that boundary.
- Do not introduce new dependencies unless explicitly approved.
