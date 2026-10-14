Run `python3 .ai/scripts/build_repo_map.py` to (re)populate `.ai/repo-map.md`: top-level structure, Django apps, URL modules, tests, per-file symbols, and the `## Static tooling & commands` section (the repo's actual lint/format tool, discovered from `.pre-commit-config.yaml`/`pyproject.toml`/`Makefile`/`package.json`).

Use this once at the start of working in a new or unfamiliar repo — before `repo_lookup` or any exploration — or again later if the tooling section's own drift note says a source config file is now newer than its recorded mtime.

After running it, report concisely: how many Django apps were found, which lint/format tool was identified (or "none detected"), and the actual "Quick commands" list from the generated `## Static tooling & commands` section verbatim (not re-summarized) — these are the runnable `make <target>` commands for running the app, the test suite, migrations, and a shell, and the point of this report is to hand them over, not just report counts.
