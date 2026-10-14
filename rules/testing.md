# Testing Rules

- First find the nearest existing test and copy its style.
- Prefer focused tests first:
  - one happy path
  - one important edge/permission/validation case when relevant
- For DRF, prefer `APIClient`/`APITestCase`, `format="json"`, auth setup matching existing tests, and `response.data` assertions.
- For Django views, use `self.client` for routing/middleware behavior and `RequestFactory` only for direct view unit tests.
- Run the narrowest meaningful command first, then broaden only if useful.
- Never weaken tests only to make them pass.
- Always report the exact command you ran, verbatim, so it can be copy-pasted and re-run independently — not a paraphrase or a generic "ran the tests."
- Any literal threshold/count a new assertion depends on (a query count, a retry limit, a page size) must be derived from an actual observed run, not guessed. State how you derived it. Before trusting it, confirm it fails against the pre-fix code and passes against the post-fix code for the stated reason — not by coincidence.
