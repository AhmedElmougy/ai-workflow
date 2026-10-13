Run `python3 .ai/scripts/build_repo_map.py` to (re)populate `.ai/repo-map.md`: top-level structure, Django apps, URL modules, tests, per-file symbols, and the `## Static tooling & commands` section (the repo's actual lint/format tool, discovered from `.pre-commit-config.yaml`/`pyproject.toml`/`Makefile`/`package.json`).

Use this once at the start of working in a new or unfamiliar repo — before `repo_lookup` or any exploration — or again later if the tooling section's own drift note says a source config file is now newer than its recorded mtime.

After running it, report in 2-3 lines: how many Django apps were found, and which lint/format tool was identified (or "none detected" if the repo has no config for one).
