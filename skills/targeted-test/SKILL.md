---
name: targeted-test
description: Selects and runs the smallest meaningful verification command for a code change, then triages failures honestly. Triggers before reporting completion.
---

# targeted-test

## Purpose

Find and run the smallest meaningful verification for a change.

## Procedure

1. Identify the closest existing test file or module.
2. Prefer one focused test or test file before a full suite.
3. For DRF, prefer `APIClient`/`APITestCase`, `format="json"`, auth setup matching existing tests, and `response.data` assertions.
4. If a test fails, classify the failure:
   - implementation bug
   - bad expectation
   - fixture/environment issue
   - unrelated existing failure
5. Report actual command and result.

## Output

```text
Verification selected:
- `<command>` because <reason>

Result:
- passed/failed/not run
- key failure line or blocker if any
```
