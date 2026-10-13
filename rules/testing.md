# Testing Rules

- First find the nearest existing test and copy its style.
- Prefer focused tests first:
  - one happy path
  - one important edge/permission/validation case when relevant
- For DRF, prefer `APIClient`/`APITestCase`, `format="json"`, auth setup matching existing tests, and `response.data` assertions.
- For Django views, use `self.client` for routing/middleware behavior and `RequestFactory` only for direct view unit tests.
- Run the narrowest meaningful command first, then broaden only if useful.
- Never weaken tests only to make them pass.
