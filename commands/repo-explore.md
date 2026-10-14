Find the relevant implementation, patterns, and tests for this task: $ARGUMENTS

Return evidence, not a generic repository summary. Do not edit anything yet.

Procedure:
1. Extract named symbols, domain terms, routes, fields, error messages, and expected behavior.
2. Use the `repo_lookup` tool for ranked likely files, symbols, tests, and verification. If unavailable, run `python3 .ai/scripts/repo_lookup.py "<task terms>"`.
3. If results are thin, widen scope before concluding — broader/alternate terms, `.ai/repo-map.md`, or exact search.
4. If the tool and script both fail to run at all (not just thin results — missing `python3`/`rg`, no `.ai/` in this environment), stop retrying and fall back to manual inspection: `grep`/`Read` directly, no `.ai/` tooling assumed.
5. Read likely source files and closest tests returned.
6. Use Graphify only if cross-file relationships remain unclear.
7. Verify any map/memory claim against source before relying on it.

Summarize the request path for this feature: name the entry point, the three most relevant files, and the existing tests, in this format:

```text
Likely entrypoints:
- <file>: <why>

Relevant implementation:
- <file/class/function>: <evidence>

Nearby tests:
- <file/test>: <behavior covered>

Open questions:
- <blocking question or none>

Suggested verification:
- `<command>`
```

`repo_lookup.py`'s output already prints every file reference as a markdown link and the verification command as a fenced code block — keep that formatting when relaying/summarizing instead of flattening it back to plain text.
