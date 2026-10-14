"""Scenario tests for repo_lookup.py.

Not coverage-driven: each case encodes a real query shape this tool is meant to handle
(a practice-interview debugging prompt, a CamelCase identifier, a cross-app Celery task,
an irrelevant query) and asserts on the one property that actually matters for that
scenario, not on exact rank order (ranking heuristics shift; the invariants below should
not).

Run: python3 -m pytest .ai/scripts/test_repo_lookup.py -q
(plain python3, no Django/Docker needed — this script has no app dependencies)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import repo_lookup as rl

_FILE_LINE = re.compile(r"^\d+\. \[([^\]]+)\]\(", re.MULTILINE)


def _ranked(query: str, max_files: int = 10) -> list[str]:
    output = rl.lookup(query, max_files=max_files, max_snippets=2)
    return _FILE_LINE.findall(output)


class TestNeverLeaksAnswerKey:
    """interview_prep/ holds this repo's own answer key for the practice problems this
    tool is used to explore — it must never appear in results, regardless of query,
    or using /explore as documented spoils the exercise it's meant to support."""

    def test_problem_1_query_excludes_interview_prep(self):
        ranked = _ranked("GET /api/service-tasks/ slow categories ServiceTaskCategory N+1")
        assert not any(r.startswith("interview_prep/") for r in ranked)

    def test_narrow_query_excludes_interview_prep(self):
        ranked = _ranked("ServiceTaskService list select_related category")
        assert not any(r.startswith("interview_prep/") for r in ranked)

    def test_direct_answer_terms_still_exclude_interview_prep(self):
        # Even a query built from words that appear verbatim in the answer key itself
        # must not surface it — the exclusion is path-based, not content-based.
        ranked = _ranked("root cause select_related queryset reassign")
        assert not any(r.startswith("interview_prep/") for r in ranked)


class TestCamelCaseIdentifierMatching:
    """A PascalCase model/class name in the query must resolve to the file defining it,
    not stay an opaque blob that only matches if the exact casing reappears elsewhere."""

    def test_service_task_category_surfaces_maintenance_app(self):
        ranked = _ranked("GET /api/service-tasks/ slow categories ServiceTaskCategory N+1", max_files=5)
        assert "src/maintenance/services.py" in ranked

    def test_vehicle_assignment_service_surfaces_vehicles_app(self):
        ranked = _ranked("VehicleAssignmentService check_availability overlap booking", max_files=6)
        assert any(r.startswith("src/vehicles/") for r in ranked)


class TestDistinctTokenCoverageBeatsGenericRepetition:
    """A file matching several distinct, specific query terms should outrank one that
    only matches a single generic word (e.g. 'service') repeated many times."""

    def test_narrow_service_query_ranks_maintenance_services_in_top_slice(self):
        ranked = _ranked("ServiceTaskService list select_related category", max_files=6)
        assert "src/maintenance/services.py" in ranked


class TestSymbolExtractionMatchesRepoMapFormat:
    """build_repo_map.py writes `.ai/repo-map.md`'s Symbols section; repo_lookup.py's
    extract_symbols_for() parses it back. Found via a format change: when the writer
    switched from backtick-wrapped paths to markdown links, the parser's regex (written
    for the old format) silently stopped matching anything — "Relevant symbols" went
    empty for every query with zero errors raised. A real coupling between two files
    that must stay in sync, not something either file's own tests would catch alone."""

    def test_extract_symbols_for_parses_real_repo_map(self):
        assert rl.REPO_MAP.exists(), "run build_repo_map.py before this test"
        symbols = rl.extract_symbols_for(["src/maintenance/services.py"])
        assert symbols.get("src/maintenance/services.py"), (
            "extract_symbols_for() found no symbols for a file known to have them — "
            "check its regex still matches build_repo_map.py's actual output format"
        )


class TestIsTestPathRecognizesNonDjangoConventions:
    """Found via a JS/Jest sandbox check: the test-path detector only recognized Django's
    nested per-app `tests/` dirs and pytest's `test_*.py` naming, silently missing a
    root-level `tests/` dir (common outside Django) and Jest/Mocha's `*.test.js`/
    `*.spec.ts` naming — meaning 'Nearby tests' came back empty despite real test files
    existing."""

    def test_root_level_tests_dir(self):
        assert rl.is_test_path("tests/orderservice.test.js", "orderservice.test.js")

    def test_jest_spec_naming(self):
        assert rl.is_test_path("src/foo.spec.ts", "foo.spec.ts")

    def test_django_nested_tests_dir_still_recognized(self):
        assert rl.is_test_path("src/maintenance/tests/test_services.py", "test_services.py")

    def test_non_test_file_not_misclassified(self):
        assert not rl.is_test_path("src/maintenance/services.py", "services.py")


class TestGracefulDegradation:
    """A query matching nothing real must not crash and must not fabricate hits."""

    def test_nonsense_query_returns_without_error(self):
        output = rl.lookup("zzqqxx_nonexistent_term_blorf", max_files=5, max_snippets=2)
        assert "Query:" in output
        assert "Note: This is a navigation aid" in output


class TestNotificationsIdempotencyQuery:
    """Problem 2's scenario (duplicate/lost Celery notifications) should resolve to the
    notifications app, not an unrelated one."""

    def test_async_notify_retry_query_surfaces_notifications_app(self):
        ranked = _ranked("async_notify idempotent retry backend duplicate notification", max_files=6)
        assert any(r.startswith("src/notifications/") for r in ranked)
