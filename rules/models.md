**Precedence**: if this repo already has an established pattern for this (check nearby files first), follow the repo's pattern — don't impose this instead. This file is my own default style, used only where no local convention is already set.

- Use django-lifecycle `@hook` instead of signals for single-model logic.
- Hook methods are private (`_name`). Use `BEFORE_SAVE`/`BEFORE_CREATE` for mutations, `AFTER_SAVE` for side-effects needing a PK.
- Use `when=`/`is_now=`/`has_changed=` conditions instead of `if` guards inside hooks.
- Never add a new `signals.py` for logic that belongs on the model.
- Model `clean()` delegates to `XxxValidator.validate(self)` via local import (circular-import exception, see `imports.md`).
- Choose `on_delete` deliberately, not by habit: `CASCADE` when the row has no meaning without the referenced object, `SET_NULL`/`PROTECT` when it should survive removal — state the reason in a comment or `help_text`.
