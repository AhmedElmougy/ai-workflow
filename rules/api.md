**Precedence**: if this repo already has an established pattern for this (check nearby files first), follow the repo's pattern — don't impose this instead. This file is my own default style, used only where no local convention is already set.

Layer responsibilities:

- View: HTTP in/out only. No ORM. No business logic.
- Serializer: shape data, validate format. No DB calls. No service calls in `to_representation`.
- Service: all business logic and writes.
- Selector: read-only queries + annotations. No writes. (Only in apps that have this layer — see `services.md`.)
- Validator: reusable cross-field/cross-model rules. Raise Django's `ValidationError` (not DRF's).

View rules:

- `queryset = Foo.objects.none()` always; the real queryset comes from the service/selector.
- Declare `output_fields`/`input_fields` explicitly in every action.
- Catch only `XxxServiceError` → return `{"detail": e.message}` with 400.
- Status codes: 201 create, 202 side-effect, 204 delete, 200 everything else.

Serializer rules:

- All serializers inherit `SelectiveFieldsMixin` first, then the DRF base — this repo already has it at `src/core/serializers/fields.py`, reuse it, don't reinvent.
- Input: `serializers.Serializer` — explicit fields only.
- Output: `ModelSerializer`, full canonical field list in `Meta.fields`; the caller selects the subset per call-site via the `fields=` kwarg (not `fields = "__all__"` with no selection).

Selector rules (only in apps that have this layer):

- Inherit the repo's base selector if one exists. Return a `QuerySet` — never evaluate inside the selector.

Validator rules:

- All methods `@staticmethod`.
- Define a `validate(instance)` entry point that calls all instance-level rules.
- One validator class per domain model.
