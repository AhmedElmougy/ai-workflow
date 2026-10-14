# Area Memory — Django/DRF

## Stable facts

- Add repo-specific Django/DRF facts here only after verifying them against source/tests.

## Gotchas

- Authentication/permissions may be enforced globally in DRF settings.
- Existing factories often live near `tests/factories.py`, but verify in the target repo.
- Check URL routing before assuming endpoint names.
- `make test`/`make test-lite` exit non-zero on a narrow test subset purely from the repo's global 95% coverage gate, even when every test in that run passed. Read the `N passed`/`N failed` summary line, don't trust the exit code alone, when running anything less than the full suite.
- `ServiceTaskService.list()` pattern (`src/maintenance/services.py`): a `.select_related(...)` call whose return value isn't reassigned is a silent no-op (QuerySets are immutable) — causes N+1 on the discarded relation. Worth grep'ing for the same copy-pasted shape (a `select_related`/`prefetch_related` call not preceded by `queryset =`) elsewhere before assuming a single occurrence is the whole bug.

## Verification commands that worked

- `make test-lite src/maintenance/tests/test_views.py::TestServiceTaskResourceView::test_list_service_tasks_view_query_count` — pytest node-id path segment needs real `/` separators, not dotted module path, or pytest reports "file or directory not found" with 0 collected.
- Query-count regression test pattern: `CaptureQueriesContext(connection)` around the view call, assert `len(ctx.captured_queries) <= N`, with the failure message joining `q["sql"]` so a failure shows the actual generated SQL inline.
