#!/usr/bin/env python3
"""Build a compact repository map for coding-agent navigation."""
# ruff: noqa: T201, BLE001 — print is this script's CLI output; the broad except in
# file_symbols() is deliberate (an unparseable file should be skipped, not crash the scan).

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".ai" / "repo-map.md"
IGNORE_PARTS = {".git", ".ai", "__pycache__", ".venv", "venv", "node_modules", "migrations", "_build"}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def skip(path: Path) -> bool:
    return any(part in IGNORE_PARTS for part in path.parts)


def replace_block(text: str, start: str, end: str, body: str) -> str:
    before, marker, rest = text.partition(start)
    if not marker:
        # Marker pair missing entirely (e.g. hand-edited or truncated file) — append
        # it rather than silently skipping the section.
        separator = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return f"{text}{separator}{start}\n{body.rstrip()}\n{end}\n"
    _, marker_end, after = rest.partition(end)
    if not marker_end:
        return text
    return f"{before}{start}\n{body.rstrip()}\n{end}{after}"


def top_level() -> str:
    rows = []
    for path in sorted(ROOT.iterdir()):
        if path.name.startswith(".") and path.name not in {".ai", ".github"}:
            continue
        if path.name == ".ai":
            continue
        kind = "dir" if path.is_dir() else "file"
        rows.append(f"- [{path.name}]({path.name}) — {kind}")
    return "\n".join(rows) or "_No files found._"


def django_apps() -> str:
    src = ROOT / "src"
    rows = []
    if src.exists():
        for apps_py in sorted(src.rglob("apps.py")):
            if skip(apps_py):
                continue
            app_dir = apps_py.parent
            files = [
                name
                for name in [
                    "models.py",
                    "views.py",
                    "serializers.py",
                    "services.py",
                    "selectors.py",
                    "validators.py",
                    "urls.py",
                ]
                if (app_dir / name).exists()
            ]
            if (app_dir / "tests").exists():
                files.append("tests/")
            app_rel = rel(app_dir)
            rows.append(f"- [{app_rel}]({app_rel}) — {', '.join(files) or 'app config only'}")
    return "\n".join(rows) or "_No Django apps detected._"


def urls() -> str:
    rows = [f"- [{rel(path)}]({rel(path)})" for path in sorted(ROOT.rglob("urls.py")) if not skip(path)]
    return "\n".join(rows) or "_No URL modules detected._"


TEST_FILE_PATTERNS = ["test*.py", "*.test.js", "*.test.jsx", "*.test.ts", "*.test.tsx", "*.spec.js", "*.spec.ts"]


def tests() -> str:
    found = {path for pattern in TEST_FILE_PATTERNS for path in ROOT.rglob(pattern) if not skip(path)}
    rows = [f"- [{rel(path)}]({rel(path)})" for path in sorted(found)]
    return "\n".join(rows) or "_No tests detected._"


def file_symbols(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols.append((node.lineno, f"class `{node.name}`"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            symbols.append((node.lineno, f"function `{node.name}`"))
    return [f"{label} L{line}" for line, label in sorted(symbols)[:20]]


_JS_CLASS_RE = re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", re.MULTILINE)
_JS_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|"
    r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(",
    re.MULTILINE,
)


def js_file_symbols(path: Path) -> list[str]:
    # Regex, not a real parser (no tree-sitter/esprima dependency) — best-effort only,
    # mirrors the Python ast walk closely enough to be useful, not exhaustive.
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    symbols = []
    for match in _JS_CLASS_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        symbols.append((line, f"class `{match.group(1)}`"))
    for match in _JS_FUNCTION_RE.finditer(text):
        name = match.group(1) or match.group(2)
        line = text.count("\n", 0, match.start()) + 1
        symbols.append((line, f"function `{name}`"))
    return [f"{label} L{line}" for line, label in sorted(symbols)[:20]]


def symbols() -> str:
    rows = []
    for path in sorted(ROOT.rglob("*.py")):
        if skip(path):
            continue
        syms = file_symbols(path)
        if syms:
            path_rel = rel(path)
            rows.append(f"- [{path_rel}]({path_rel}) — " + "; ".join(syms))
    for ext in (".js", ".jsx", ".ts", ".tsx"):
        for path in sorted(ROOT.rglob(f"*{ext}")):
            if skip(path) or "node_modules" in path.parts:
                continue
            syms = js_file_symbols(path)
            if syms:
                path_rel = rel(path)
                rows.append(f"- [{path_rel}]({path_rel}) — " + "; ".join(syms))
    return "\n".join(rows) or "_No Python/JS/TS symbols detected._"


def _pre_commit_tools(text: str) -> list[str]:
    names = []
    for match in re.finditer(r"repo:\s*(\S+)", text):
        name = match.group(1).rstrip("/").rsplit("/", 1)[-1]
        if name and name not in names:
            names.append(name)
    return names


def _pyproject_tool_sections(text: str) -> list[str]:
    return re.findall(r"^\[tool\.(\w+)\]", text, flags=re.MULTILINE)


def _makefile_targets(text: str) -> list[str]:
    targets = []
    for line in text.splitlines():
        match = re.match(r"^([a-zA-Z][\w-]*)\s*:", line)
        if match:
            targets.append(match.group(1))
    return targets


def _package_json_scripts(text: str) -> dict[str, str]:
    try:
        return json.loads(text).get("scripts", {})
    except Exception:
        return {}


NPM_SCRIPT_HINTS = {
    "dev": "run in dev mode (watch/reload)",
    "start": "run once",
    "build": "build for production",
    "test": "run test suite",
    "lint": "lint",
    "lint:fix": "lint, auto-fixing what it can",
    "format": "format code",
}


def _pre_commit_row(text: str) -> str | None:
    found = _pre_commit_tools(text)
    if not found:
        return None
    tools = ", ".join(found)
    return f"- pre-commit hooks: {tools} — run via `pre-commit run --files <changed files>`"


def _pyproject_row(text: str) -> str | None:
    relevant = [s for s in _pyproject_tool_sections(text) if s in {"ruff", "black", "flake8", "isort", "mypy"}]
    if not relevant:
        return None
    return f"- `pyproject.toml` configures: {', '.join(f'[tool.{s}]' for s in relevant)}"


# Conventional target names this generator recognizes across Docker/Django-style Makefiles,
# in a sensible "how you'd actually use this repo" order. Only the ones present are shown,
# so repo-init hands over runnable commands, not just a name list the agent re-derives.
QUICK_COMMAND_HINTS = {
    "up": "start the stack",
    "upbuild": "build + start the stack",
    "down": "stop the stack",
    "run": "run a one-off command in a fresh container",
    "test": "run full test suite (fresh db)",
    "test-lite": "run tests fast (reuse db, skip migrations) — pass a path/node-id to scope it",
    "test-debug": "run tests, drop into --pdb on failure",
    "migrate": "apply migrations",
    "makemigrations": "create new migrations",
    "showmigrations": "list migrations + applied state",
    "shell": "Django shell (shell_plus if installed)",
    "bash": "shell into the app container",
    "psql": "psql into the project db",
    "logs": "tail container logs",
    "manage": "run any manage.py subcommand",
}


def _quick_commands_rows(found_targets: list[str]) -> list[str]:
    present = [t for t in QUICK_COMMAND_HINTS if t in found_targets]
    if not present:
        return []
    return ["- Quick commands:", *(f"  - `make {t}` — {QUICK_COMMAND_HINTS[t]}" for t in present)]


def _makefile_row(text: str) -> str | None:
    found = _makefile_targets(text)
    if not found:
        return None
    lines = [f"- Makefile targets: {', '.join(found)} — run via `make <target>`"]
    lines.extend(_quick_commands_rows(found))
    return "\n".join(lines)


def _package_json_row(text: str) -> str | None:
    scripts = _package_json_scripts(text)
    if not scripts:
        return None
    lines = ["- package.json scripts: " + ", ".join(f"`{k}`" for k in scripts) + " — run via `npm run <script>`"]
    present = [k for k in NPM_SCRIPT_HINTS if k in scripts]
    if present:
        lines.append("- Quick commands:")
        lines.extend(f"  - `npm run {k}` — {NPM_SCRIPT_HINTS[k]}" for k in present)
    return "\n".join(lines)


# Config sources read here, with mtimes recorded below so a consumer can tell if this section is stale.
TOOLING_SOURCES = {
    ".pre-commit-config.yaml": _pre_commit_row,
    "pyproject.toml": _pyproject_row,
    "Makefile": _makefile_row,
    "package.json": _package_json_row,
}


def tooling() -> str:
    rows: list[str] = []
    source_mtimes: list[str] = []

    for name, row_builder in TOOLING_SOURCES.items():
        path = ROOT / name
        if not path.exists():
            continue
        source_mtimes.append(f"{name}@{int(path.stat().st_mtime)}")
        row = row_builder(path.read_text(encoding="utf-8", errors="ignore"))
        if row:
            rows.append(row)

    if not rows:
        rows.append("_No lint/format/test tooling config detected._")
    rows.append("")
    rows.append(
        f"_Source mtimes for drift check: {', '.join(source_mtimes) or 'none'}. "
        "If any of these files is now newer than its recorded mtime, re-run "
        "`python3 .ai/scripts/build_repo_map.py` before trusting this section._",
    )
    return "\n".join(rows)


SKELETON = """# Repository Map

Generated navigation map. It is not the source of truth.

Regenerate:

```bash
python .ai/scripts/build_repo_map.py
```

## Top-level

<!-- AI-REPO-MAP:TOP START -->
<!-- AI-REPO-MAP:TOP END -->

## Static tooling & commands

<!-- AI-REPO-MAP:TOOLING START -->
<!-- AI-REPO-MAP:TOOLING END -->

## Django apps / modules

<!-- AI-REPO-MAP:APPS START -->
<!-- AI-REPO-MAP:APPS END -->

## URL modules

<!-- AI-REPO-MAP:URLS START -->
<!-- AI-REPO-MAP:URLS END -->

## Tests

<!-- AI-REPO-MAP:TESTS START -->
<!-- AI-REPO-MAP:TESTS END -->

## Symbols

<!-- AI-REPO-MAP:SYMBOLS START -->
<!-- AI-REPO-MAP:SYMBOLS END -->
"""


def main() -> None:
    text = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    if "AI-REPO-MAP" not in text:
        # Missing file or markerless content (e.g. truncated by hand) — reset to the
        # full skeleton rather than silently no-op'ing or appending headless blocks.
        text = SKELETON
    sections = {
        ("<!-- AI-REPO-MAP:TOP START -->", "<!-- AI-REPO-MAP:TOP END -->"): top_level(),
        ("<!-- AI-REPO-MAP:TOOLING START -->", "<!-- AI-REPO-MAP:TOOLING END -->"): tooling(),
        ("<!-- AI-REPO-MAP:APPS START -->", "<!-- AI-REPO-MAP:APPS END -->"): django_apps(),
        ("<!-- AI-REPO-MAP:URLS START -->", "<!-- AI-REPO-MAP:URLS END -->"): urls(),
        ("<!-- AI-REPO-MAP:TESTS START -->", "<!-- AI-REPO-MAP:TESTS END -->"): tests(),
        ("<!-- AI-REPO-MAP:SYMBOLS START -->", "<!-- AI-REPO-MAP:SYMBOLS END -->"): symbols(),
    }
    for (start, end), body in sections.items():
        text = replace_block(text, start, end, body)
    OUT.write_text(text, encoding="utf-8")
    print(f"updated {rel(OUT)}")


if __name__ == "__main__":
    main()
