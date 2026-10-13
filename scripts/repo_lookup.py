#!/usr/bin/env python3
"""One-call repository lookup for coding agents.

Given task terms, return a compact ranked list of likely files, symbols, tests,
and verification commands. This is a navigation aid; verify against source.
"""
# ruff: noqa: T201, S603, S607, BLE001
# T201 is real output, not debug; S603/S607's rg/grep calls take no shell input.
# BLE001 degrades a timeout (or both rg and grep missing) to "no hits" instead of crashing.

from __future__ import annotations

import argparse
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO_MAP = ROOT / ".ai" / "repo-map.md"
IGNORE_PARTS = {".git", "__pycache__", ".venv", "venv", "node_modules", "migrations", "_build", ".ai"}
CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss", ".yml", ".yaml", ".toml", ".md"}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def skip(path: Path) -> bool:
    return any(part in IGNORE_PARTS for part in path.parts)


def tokens(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9_]+", text)
    out: list[str] = []
    for item in raw:
        out.extend(part.lower() for part in item.split("_") if len(part) > 1)
    return out


def candidate_files() -> list[Path]:
    return sorted(path for path in ROOT.rglob("*") if path.is_file() and not skip(path) and path.suffix in CODE_EXTS)


def score_path(path: Path, query_tokens: list[str]) -> tuple[int, list[str]]:
    r = rel(path).lower()
    name = path.name.lower()
    parts = set(tokens(r))
    score = 0
    reasons: list[str] = []
    for term in query_tokens:
        if term in tokens(name):
            score += 16
            reasons.append(f"filename:{term}")
        elif term in parts:
            score += 7
            reasons.append(f"path:{term}")
        elif term in r:
            score += 2
            reasons.append(f"path-substr:{term}")
    if "/tests/" in r or path.name.startswith("test"):
        score += 1
    if path.name in ("__init__.py", "conftest.py"):
        score -= 8
    return score, reasons[:4]


def _run_rg(pattern: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "rg",
            "-n",
            "--ignore-case",
            "--glob",
            "!.ai/**",
            "--glob",
            "!docs/**",
            "--glob",
            "!locale/**",
            "--glob",
            "!**/migrations/**",
            pattern,
            str(ROOT),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )


def _run_grep(pattern: str) -> subprocess.CompletedProcess[str]:
    # grep fallback for an environment with no real `rg` binary on PATH (only a shell
    # function/alias, invisible to subprocess.run's direct execve/PATH lookup).
    return subprocess.run(
        [
            "grep",
            "-rn",
            "-i",
            "-E",
            "--exclude-dir=.ai",
            "--exclude-dir=docs",
            "--exclude-dir=locale",
            "--exclude-dir=migrations",
            "--exclude-dir=.git",
            "--exclude-dir=node_modules",
            "--exclude-dir=venv",
            "--exclude-dir=.venv",
            "--exclude-dir=__pycache__",
            pattern,
            str(ROOT),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )


def rg_hits(query_tokens: list[str], limit: int = 80) -> dict[str, list[str]]:
    if not query_tokens:
        return {}
    pattern = "|".join(re.escape(t) for t in sorted(set(query_tokens), key=len, reverse=True))
    try:
        proc = _run_rg(pattern)
    except FileNotFoundError:
        try:
            proc = _run_grep(pattern)
        except Exception:
            return {}
    except Exception:
        return {}
    hits: dict[str, list[str]] = defaultdict(list)
    for line in proc.stdout.splitlines()[:limit]:
        try:
            file_part, line_no, snippet = line.split(":", 2)
        except ValueError:
            continue
        try:
            file_rel = rel(Path(file_part))
        except ValueError:
            continue
        hits[file_rel].append(f"L{line_no}: {snippet.strip()[:140]}")
    return hits


def extract_symbols_for(files: list[str]) -> dict[str, list[str]]:
    symbols: dict[str, list[str]] = {}
    if not REPO_MAP.exists():
        return symbols
    text = REPO_MAP.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        if not line.startswith("- `") or " — " not in line:
            continue
        path = line.split("`", 2)[1]
        if path in files:
            syms = line.split(" — ", 1)[1]
            symbols[path] = [s.strip() for s in syms.split(";")[:12]]
    return symbols


def _domains_from_ranked(ranked_files: list[str]) -> set[str]:
    domains: set[str] = set()
    for f in ranked_files:
        parts = f.split("/")
        if "src" in parts and len(parts) > parts.index("src") + 1:
            domains.add(parts[parts.index("src") + 1])
        if len(parts) > 1:
            domains.add(parts[-2])
    return domains


def _test_score(low: str, domains: set[str], query_tokens: list[str]) -> int:
    score = sum(6 for d in domains if d and d.lower() in low)
    return score + sum(4 for t in query_tokens if t in low)


def suggested_tests(ranked_files: list[str], all_files: list[Path], query_tokens: list[str]) -> list[str]:
    domains = _domains_from_ranked(ranked_files)
    tests: list[tuple[int, str]] = []
    for path in all_files:
        r = rel(path)
        low = r.lower()
        if "/tests/" not in low and not path.name.startswith("test"):
            continue
        score = _test_score(low, domains, query_tokens)
        if score:
            tests.append((score, r))
    return [r for _, r in sorted(tests, reverse=True)[:8]]


def verification_command(tests: list[str]) -> str:
    if not tests:
        return "pytest -q  # or project-specific focused test command"
    first = tests[0]
    if (
        Path(ROOT / "pyproject.toml").exists()
        or Path(ROOT / "pytest.ini").exists()
        or Path(ROOT / "setup.cfg").exists()
    ):
        return f"pytest {first} -q"
    if Path(ROOT / "manage.py").exists():
        module = first.removesuffix(".py").replace("/", ".")
        return f"python manage.py test {module}"
    return f"pytest {first} -q"


def lookup(query: str, max_files: int, max_snippets: int) -> str:
    q_tokens = tokens(query)
    files = candidate_files()
    path_scores, reasons = _score_candidates(files, q_tokens)
    hits = rg_hits(q_tokens)
    _apply_text_matches(path_scores, reasons, hits)

    ranked = [r for r, _ in sorted(path_scores.items(), key=lambda item: (-item[1], item[0]))[:max_files]]
    symbols = extract_symbols_for(ranked)
    tests = suggested_tests(ranked, files, q_tokens)

    out: list[str] = [f"Query: {query}", "", "Likely files:"]
    out.extend(_format_likely_files(ranked, reasons, hits, max_snippets))
    out.extend(("", "Relevant symbols:"))
    out.extend(_format_symbols(ranked, symbols))
    out.extend(("", "Nearby tests:"))
    out.extend(_format_tests(tests))
    out.extend(("", "Suggested reads:"))
    out.extend(f"- `{file_rel}`" for file_rel in ranked[:5])
    out.extend(f"- `{test}`" for test in tests[:2] if test not in ranked[:5])
    out.extend(("", "Suggested verification:", f"- `{verification_command(tests)}`", ""))
    out.append("Note: This is a navigation aid. Verify behavior against source and tests before editing.")
    return "\n".join(out)


def _score_candidates(files: list[Path], q_tokens: list[str]) -> tuple[dict[str, int], dict[str, list[str]]]:
    path_scores: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}
    for path in files:
        score, why = score_path(path, q_tokens)
        if score:
            r = rel(path)
            path_scores[r] = score
            reasons[r] = why
    return path_scores, reasons


def _text_match_bonus(file_rel: str, snippet_count: int) -> int:
    bonus = 8 + min(snippet_count, 5) * 2
    if file_rel.startswith(("src/", "config/")):
        bonus += 4
    if "/tests/" in file_rel or Path(file_rel).name.startswith("test"):
        bonus += 3
    if file_rel.startswith(("docs/", "locale/", "fixtures/")) or file_rel.endswith(".md"):
        bonus -= 8
    if file_rel.endswith(("/__init__.py", "/conftest.py")) or file_rel == "src/conftest.py":
        bonus -= 10
    return max(bonus, 1)


def _apply_text_matches(
    path_scores: dict[str, int],
    reasons: dict[str, list[str]],
    hits: dict[str, list[str]],
) -> None:
    for file_rel, snippets in hits.items():
        path_scores[file_rel] = path_scores.get(file_rel, 0) + _text_match_bonus(file_rel, len(snippets))
        reasons.setdefault(file_rel, []).append("text-match")


def _format_likely_files(
    ranked: list[str],
    reasons: dict[str, list[str]],
    hits: dict[str, list[str]],
    max_snippets: int,
) -> list[str]:
    if not ranked:
        return ["- No strong match. Read `.ai/repo-map.md` or broaden exact search."]
    lines: list[str] = []
    for i, file_rel in enumerate(ranked, 1):
        why = ", ".join(dict.fromkeys(reasons.get(file_rel, []))) or "ranked match"
        lines.append(f"{i}. `{file_rel}`")
        lines.append(f"   reason: {why}")
        lines.extend(f"   - {snippet}" for snippet in hits.get(file_rel, [])[:max_snippets])
    return lines


def _format_symbols(ranked: list[str], symbols: dict[str, list[str]]) -> list[str]:
    lines = [f"- `{file_rel}` — {sym}" for file_rel in ranked for sym in symbols.get(file_rel, [])[:8]]
    return lines or ["- No symbols found in repo map for ranked files."]


def _format_tests(tests: list[str]) -> list[str]:
    return [f"- `{t}`" for t in tests] or ["- No nearby tests found from map/path matching."]


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank likely source/tests for a coding task")
    parser.add_argument("query", nargs="+", help="Task/query terms")
    parser.add_argument("--max-files", type=int, default=8)
    parser.add_argument("--max-snippets", type=int, default=2)
    args = parser.parse_args()
    print(lookup(" ".join(args.query), args.max_files, args.max_snippets))


if __name__ == "__main__":
    main()
