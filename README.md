# `.ai` Coding Companion Workflow — Design Rationale

This is the source of truth for *why* this workflow is shaped the way it is. `AGENTS.md` is the operational contract the agent follows every turn; this file is why that contract looks like it does. If a change here would also change agent behavior, change `AGENTS.md`, not this file.

## The one rule everything else follows from

**Context is a budget, not a convenience.** Every token spent on a file the agent didn't need to see, or a rule it already knows this session, is a token not available for the actual task — and in a long session, it's also a token the model has to keep attending to on every subsequent turn. Three independent lines of evidence converge on the same fix, not one vendor's opinion:

- Anthropic's own context-engineering guidance: retrieve-at-runtime over preload.
- The skills ecosystem's loading model: progressive disclosure (small manifest, full content only once a skill actually matches).
- Harness builders' default behavior: offload verbose work into isolated contexts and return only the summary.

A benchmark that makes this concrete: agents given **5K tokens of targeted retrieval outperformed agents given a 100K-token full-codebase summary**. Lean and targeted beats broad and "complete" — not just cheaper, *more accurate*, because the model isn't hunting for the relevant 5% inside the other 95%. This is the design constraint every layer below answers to.

## Layer 1 — `AGENTS.md`: the one always-loaded file

Broad operating principles that every task needs (the clarify → explore → plan → implement → verify → review → report loop, the mode modifiers, the final-response contract) go in the one file guaranteed to be in context every turn. Everything else is loaded conditionally, specifically so this file can stay small.

Why small matters here specifically: `AGENTS.md`/`CLAUDE.md`-style files share the same instruction budget as the system prompt itself — they compete for the same attention window. The more instructions piled in, the less reliably *any individual one* gets followed. So `AGENTS.md` stays an index and a loop, not a knowledge dump — knowledge lives one layer down, loaded only when relevant.

**This file lives at `.ai/AGENTS.md`, not repo root — which means Claude Code's native auto-discovery never found it on its own.** Claude Code only natively reads a root-level `CLAUDE.md`/`AGENTS.md` (or walks up the directory tree for one); it does not search arbitrary subdirectories. For most of this setup's history, the *only* reason this file's content ever reached the agent was the `UserPromptSubmit` hook's thin banner pointing at it — a pointer the agent had to choose to act on, not a guarantee. A documented real-world report describes exactly this failure mode ("Claude ignores `AGENTS.md`... only `CLAUDE.md`, never `AGENTS.md`"). The fix: a root `/CLAUDE.md` containing a single line, `@.ai/AGENTS.md` — Claude Code's own documented import syntax, expanded inline into context at session start exactly as if it were written there. Now the canonical file is actually guaranteed to load, not just pointed at.

## Layer 2 — Retrieval (`repo_lookup`): a cheap pointer before an expensive read

`repo_lookup` (`.ai/scripts/repo_lookup.py`, exposed natively to the Pi harness via `.pi/extensions/repo-lookup.ts`, and to Claude Code as the documented Bash fallback `python3 .ai/scripts/repo_lookup.py "<query>"`) exists to prevent the single most common real-world failure mode in agentic coding: the agent acting like a data hoarder — unbounded `grep` across the repo, or `Read` slurping whole files just to find the one relevant function, paying for 3–5 tool calls and their full output before even confirming relevance.

The fix it implements, validated by the 5K-vs-100K benchmark above: return a **ranked list of likely files + ≤2-line snippets per file, capped at 16K characters** — a pointer, not a payload. It explicitly frames itself as "a navigation aid, verify against source" rather than an authoritative answer, because a ranked guess can be wrong, and treating it as certain would just trade one failure mode (too much context) for another (confidently wrong context).

One deliberate non-change, worth stating since it looks like an obvious "improvement" at first glance: **rule content is not attached at this step.** Rules shape how a *specific* file should be read/edited; `repo_lookup` hasn't committed to a specific file yet, it's still ranking candidates. Attaching full rule text to every one of the 8 ranked candidates would reintroduce exactly the bloat this layer exists to avoid. Rule content is deliberately deferred to Layer 3, which fires only once the agent commits to actually opening a file.

**`repo-map.md` is the index underneath this layer, not a separate thing.** `repo_lookup.py` doesn't parse the codebase live on every query — that would make every call pay an AST-scan cost. Instead, `build_repo_map.py` walks the tree once (Python `ast` module) and writes a static, compact map — top-level structure, Django apps and which layer files each one has, every `urls.py`, and per-file symbols — to `.ai/repo-map.md`. `repo_lookup` then reads that pre-built file internally (`extract_symbols_for()`) purely to attach the "Relevant symbols" section to whichever files it already ranked; it is never used to do the ranking itself. It has a second, manual role too: `repo_lookup`'s own output falls back to *"No strong match. Read `.ai/repo-map.md` or broaden exact search"* when ranking comes back empty, making it the explicit escape hatch for the one case the lean ranked-pointer approach can't handle — a query too broad or too novel to score any file highly. Build the index once, query the index cheaply, fall back to reading it directly only when the query step itself fails — the standard index/query split, not a special case.

**The same index also now carries a `## Static tooling & commands` section** — which lint/format tool this repo actually uses, discovered once by parsing `.pre-commit-config.yaml`/`pyproject.toml`/`Makefile`/`package.json`, not re-derived every time something needs to run it. This is deliberately a script-level fact, not a skill-level one: deciding whether a `[tool.ruff]` block exists is pure parsing with no ambiguity to judge, so it belongs in the same deterministic generator that already does AST-scanning for symbols, not in agent reasoning that could hallucinate or skip a config file. Real precedent for discovery-as-a-generated-artifact rather than a judged skill: Claude Code's own `/init` command is exactly this shape — a one-time scan that populates a file, not an ongoing per-task judgment call. The section records each source file's mtime at generation time specifically so a consumer can tell if it's gone stale (a real, named failure mode: *"agent memory is a cache with no invalidation policy"*) — the standard, lightweight fix confirmed in real implementations is mtime comparison, not re-discovery on every read.

**This capability existed before anything actually triggered it — a real gap, caught the same way the `CLAUDE.md` auto-load gap was.** The script worked; nothing in `AGENTS.md` ever told the agent to run it. The first fix attempt made it a task-loop prose step ("first time touching this repo, check and run it") — which repeats the exact reliability mistake this whole document argues against everywhere else: a prose instruction the agent has to remember and judge is the *least* reliable trigger available, not a neutral default.

**The actual fix is `/repo-init`, a custom slash command, not a task-loop step and not a skill.** The real distinction, confirmed by how Claude Code's own ecosystem splits the two: a skill is for a process that should run the same way every time regardless of whether anyone remembers to invoke it (automatic, description-matched); a slash command is for something context-dependent and one-off, decided by a human in control of the moment ("right now, I want this specific thing to happen") — and Claude Code's own `/init` is exactly that shape, not a skill. "I'm starting fresh in a repo I've never seen" is information only the human has; no amount of agent-side judgment substitutes for it reliably. The task loop now just says: if it looks like `/repo-init` was never run, say so and suggest it — it doesn't try to self-trigger the discovery pass as a guess.

**Correction, found by actually invoking it rather than trusting the design on paper**: this previously claimed `.claude/commands/repo-init.md` could be a one-line `@../../.ai/commands/repo-init.md` pointer, the same `@import` mechanism `CLAUDE.md` uses. That's wrong — invoking it via the `Skill` tool returns the literal unresolved string `@../../.ai/commands/repo-init.md`, not the pointed-to content; `@import` resolution happens for `CLAUDE.md`'s own project-instructions bootstrap, not for an arbitrary command file's body read at invocation time. Same bug hit `/explore`'s `$ARGUMENTS` substitution — it only works when the placeholder is in the directly-loaded file, not through a pointer. Both commands now carry their real content directly under `.claude/commands/`; `.ai/commands/*.md` stays as the portable canonical copy for sharing outside Claude Code, kept in sync by hand — there is no mechanism enforcing that sync, so a future edit to one and not the other silently drifts.

## Layer 3 — Rules: deterministic, path-scoped, zero model judgment

`rules/*.md` (`imports.md`, `models.md`, `services.md`, `api.md`, `testing.md`) are short, concrete, per-layer conventions injected by a `PreToolUse` hook (`on_file_access.sh`) keyed to file-path glob matching — one file per layer, so touching `services.py` doesn't pull in `api.md`'s content and vice versa. Not invoked, not judged, not optional. The guiding principle, stated plainly in current Claude Code guidance: *if it's "always do X when touching Y," that's a hook/rule, not a skill.* A skill requires the model to judge that its description matches the situation; a rule fires deterministically whenever the glob matches, regardless of whether the model thought to ask for it.

**These are deliberately concrete and named, not abstracted into generic "write good code" advice — and that choice is itself backed by real-world evidence, not a style preference.** An earlier pass of this review argued the opposite (cut anything that sounds like textbook advice, since the model "already knows" it) and that argument was wrong: a documented Claude Code issue shows the model using inline imports again *in the same session* after being told explicitly not to, and the pattern across real practitioner reports is that LLMs are literalists — they don't reliably apply a convention they weren't just explicitly, concretely reminded of, especially for an architectural choice (service layer, selector layer, inline vs top-of-file imports) that competes with a strong generic default the model gravitates to otherwise. So these rule files name the exact pattern (decorator, class name convention, a short code snippet), not a principle to infer.

**Each rule file opens with an explicit precedence note**: follow this repo's own established pattern first if one already exists for that layer; these files are a personal default style, used only where this repo hasn't set a convention yet. This isn't hypothetical — `services.md` asks for a selector layer and `@transaction.atomic`, but this repo's actual `maintenance/services.py` puts reads directly on the service class with no selector and no explicit atomic wrapping; `api.md`'s serializer rule was written to match this repo's real `SelectiveFieldsMixin` pattern (explicit field lists chosen per call-site) rather than the more generic `fields = "__all__"` default, specifically because the two didn't match and the repo's version is what's actually there.

This isn't an idiosyncratic choice specific to this repo — glob-scoped, file-triggered rule loading is a pattern independently converged on by other mature tools (Cursor's rules system ships the identical mode as its recommended default for domain-specific guidance, alongside always-on, description-matched, and manually-invoked modes for the cases that actually need those).

**Why the hook fires on `Read`, not just `Edit`/`Write`:** rules shape interpretation, not only edits. `context=research` mode is explicitly "no edits unless asked" — if the hook only fired on write operations, a pure review/explain task would never see the relevant convention at all, which is exactly the case where catching a subtle gotcha matters most. The first `Read` is also where the plan typically forms; arriving only at edit-time is too late relative to the reasoning that already happened.

**Why rule injection is deduped per session:** without it, every matching `Read` re-emits the full rule block — a real, independently documented Claude Code pain point (one reported case: ~165KB of duplicate injected content in a single session from redundant injection paths). The fix is the standard, documented pattern: every hook payload carries a `session_id`; `on_file_access.sh` tracks which rules it has already shown via a `session_id`-keyed marker directory under `/tmp`, and emits a one-line reminder instead of the full block on repeat.

## Layer 4 — Skills: on-demand procedures, not facts

`skills/*/SKILL.md` (`task-contract`, `repo-explore`, `django-task`, `targeted-test`, `diff-review`, `project-memory`, `scale-defense`) are multi-step procedures loaded only when a situation matches — "load at most one at a time." The line between a rule and a skill is really a line between a *fact* and a *procedure*: a rule says "this is true about this codebase"; a skill says "here are the steps for this kind of situation."

**A `lint-check` skill existed briefly and was deleted — a useful case study in a skill with no remaining job.** Its first version re-discovered the repo's lint tool inside the skill itself, duplicating what `build_repo_map.py` now does once (a fact pretending to be a procedure). Once `on_stop.sh` ran the tool's own auto-fix pass unconditionally on every `Stop` event, a second correction tried to narrow the skill to just the judgment calls a script can't make — classify each surviving finding, fix accordingly. But that judgment was already happening without the skill: real research on LLM self-correction confirms agents act on raw, specific tool output (ruff's own messages already say exactly what's wrong and often how) without needing a separate instruction file to interpret it, and in practice, across every real block this session produced, the skill's written procedure was never actually consulted — the agent just reacted directly to the hook's fed-back text, correctly, every time. The one thing worth keeping explicit is the call to *act* ("fix this, or report it as known-failing" — present directly in `on_stop.sh`'s own blocked message), not a wrapping skill elaborating how.

The sharper line — between a *good* skill and a wasted one — comes straight from Anthropic's own skill-authoring guidance: a skill should encode **institutional or domain-specific knowledge the model cannot get anywhere else**, not teach a generic technique the model's training already covers. A skill that says "always structure your analysis as Problem → Root Cause → Recommendation" fights the model's own judgment and goes stale the moment a better model ships. A skill that says "this repo's service layer is the single source of truth for business logic, inspect it before touching a view" gives the model something it has no other way to know. Every skill in this repo is deliberately the second kind — repo-specific procedure, not general capability.

`scale-defense` is a useful edge case of this principle: it points *outward* to detailed reference material (personal, evidence-backed notes living outside this repo) rather than inlining any of it. A skill should be a pointer to knowledge, not a duplicate copy of it — the file that holds the skill's trigger logic stays tiny no matter how deep the material it points to actually is.

## Layer 5 — Memory: a capped index preloaded once, details always on-demand

`memory/MEMORY.md` is a lookup index, not a transcript — area files (`area_django.md`, etc.) hold durable, *verified* facts (architecture, invariants, stable commands, gotchas), and are updated only when something durable and non-obvious is actually learned, never as a running log of what happened.

**The index is preloaded, capped, once per session** — `on_prompt_submit.sh` injects the first 200 lines of `MEMORY.md` on the first turn only (session-marker deduped, same mechanism as Layer 3), then stays silent for the rest of the session. This deliberately mirrors Claude Code's own native Auto Memory behavior (it preloads a 200-line-capped `MEMORY.md` into the system prompt at session start, leaving topic files on-demand). It is **not** the only legitimate pattern, though: cross-tool research found a genuine split, not a single standard — Windsurf's Cascade does pure on-demand/relevance-triggered memory retrieval with no preload at all, while Claude Code and Aider's `CONTEXT.md` variant both preload a small, bounded index. Either end of that split is defensible; the one pattern every source agreed is wrong is Cursor's older behavior of loading its full rules/memory wholesale into every session regardless of relevance — this setup was never close to that regardless of which side of the split it picked.

**Area files stay strictly on-demand** — never preloaded, only read when the index's own "when to read" column says so. This is the same progressive-disclosure logic as Layer 4 applied to accumulated knowledge instead of procedures: preloading accumulated facts wholesale is the data-hoarder failure mode again, just recurring every session.

**Re-reading an unchanged memory file is hard-blocked, not just discouraged.** Once a memory file has been read this session, `on_file_access.sh` denies a repeat `Read` of it outright (`permissionDecision: "deny"`) rather than letting the duplicate through with a reminder — unlike the soft-nudge treatment rules get. This mirrors a real production pattern (`claude-mem`, a Claude Code memory plugin, blocks a whole-file re-read the same way when it already has fresher knowledge of that file). The block is mtime-aware: if the file was edited after the marker was set, the next read is allowed through again and the marker refreshes — otherwise a genuinely stale block would prevent ever picking up a real edit. `Edit`/`Write` on memory files are never blocked, since updating memory must always work.

## Layer 6 — Hooks: the deterministic guardrail layer

Hooks exist because some things must not depend on the model remembering to do them. The underlying principle: *don't put something in `AGENTS.md` that you could express as a hook instead* — a text instruction is probabilistic (competes for attention, can be deprioritized in a long session); a hook runs outside the agent loop entirely and fires unconditionally on the matching event.

This repo's hook surface is deliberately narrow, but it is no longer purely informational — two of five hooks can now actively block, not just remind:

| Hook | Event | Purpose |
| --- | --- | --- |
| `on_prompt_submit.sh` | `UserPromptSubmit` | Compact pointer back to `AGENTS.md`'s loop every turn; `MEMORY.md`'s first 200 lines once per session only. |
| `on_file_access.sh` | `PreToolUse` (`Read\|Edit\|Write`) | Inject the one relevant rule for the touched file's path (deduped to a reminder per session); hard-block a repeat `Read` of an unchanged memory file. |
| `on_file_edit.sh` | `PostToolUse` (`Edit\|Write`) | "Verify before answering" reminder, scoped by extension; flags new comment lines the edit introduced, as a why-vs-what nudge. |
| `on_stop.sh` | `Stop` | Runs this repo's real lint/format tool, scoped to changed files, exactly once per task; blocks finishing if it's still failing after one auto-fix attempt. |

**Why comment-hygiene is a hook, not another `AGENTS.md` instruction**: a documented real-world report shows Claude re-adding unnecessary comments *in the same session*, after being told explicitly not to — "even when reinforced via the memory system." Prose doesn't reliably suppress this specific behavior, no matter how explicit. `on_file_edit.sh` now diffs `old_string`/`new_string` on every `Edit`/`Write`, flags any genuinely new comment line, and asks whether it explains WHY (keep) or just WHAT/this-task-context (remove) — a heuristic nudge, not a parser, deliberately tolerant of false positives/negatives since the cost of a missed or extra nudge is low.

**Why lint enforcement is a `Stop` hook, not a `PostToolUse` one — a real design mistake, caught and fixed before shipping.** The first version of this hook reused `on_file_edit.sh`'s per-edit trigger: lint after every single `Edit`/`Write` call. That's the wrong granularity — a task with 5 edits across 3 files doesn't need 5 lint runs, it needs exactly one, scoped to everything changed by the end. `Stop` fires once, at the point the agent is about to finish its turn, which is the actual granularity an end-of-task gate needs.

**This is also where "hook" stops meaning "nudge" and starts meaning "gate."** A `Stop` hook can return `{"decision": "block", "reason": "..."}` and the agent is *forced* to continue — the failure is fed back automatically, not left to a reminder the model might not act on. The critical safeguard, confirmed in Claude Code's own hook docs: check the event's own `stop_hook_active` flag first. If it's already `true` — meaning this is a forced-continuation re-run from a *previous* block — don't block again, or a genuinely unfixable lint error loops forever. This single flag check is also what implements the bounded-retry judgment without any extra logic: one block, ever, per stop attempt; the second time through, it lets the agent finish regardless of outcome.

**A real, concrete incident from building this hook, left in deliberately**: the first version ran `ruff format` against every staged file with no `--force-exclude`, and since this repo has zero commits (everything is still staged from the initial `git add`), it reformatted Django migration files — which `.pre-commit-config.yaml` explicitly excludes from every other tool in this repo. Ruff ignores its own configured `exclude`/`extend-exclude` list for explicitly-passed file paths unless `--force-exclude` is set. The fix was one flag; the lesson is that "run the repo's real tool" still has to respect the repo's *entire* configuration, not just the part that picks the tool.

So, precisely: `on_file_access.sh`'s memory re-read block and `on_stop.sh`'s lint gate are the two deliberate enforcement points — both exist because the thing they guard against (a wasted duplicate read; a known-broken diff) has no legitimate case for being let through. Everything else stays advisory, matching this setup's framing as a coding *companion*, not a lockdown.

Registration lives in `.claude/settings.json` (project-level, travels with the repo via git) — a hook script sitting in `.ai/hooks/` with no corresponding entry in `settings.json` does nothing at all, regardless of what its own comments say it's for. This was itself a real gap found in this setup: the scripts existed and were documented as active before they were ever actually wired up.

## The resulting shape, end to end

```text
UserPromptSubmit  → cheap workflow banner every turn; MEMORY.md's first 200 lines, once per session only
repo_lookup        → ranked pointer + tiny snippets, ≤16K chars, before any full read; reads repo-map.md's
                      cached tooling facts, never re-discovers them
Read (PreToolUse)  → inject the ONE relevant rule for this path (full once, reminder after);
                      block a repeat Read of an unchanged memory area file outright
Edit/Write (Post)  → verification reminder scoped by extension; flag new comment lines as a why-vs-what nudge
Stop (once)        → run this repo's real lint/format tool on changed files; block finishing if still
                      failing after one fix, never block twice (stop_hook_active guards the loop)
Skills             → loaded only on explicit situation match, never preloaded; hold procedure, not fact
Memory writes      → only for durable, verified, non-obvious discoveries, never routine summaries
```

Small, cheap steps fire on every turn; expensive, specific content is pulled only once the agent has actually committed to needing it. That ordering — cheap-and-broad first, expensive-and-specific only on demand — is the whole design, restated.

## Quick reference

```bash
chmod +x .ai/hooks/*.sh .ai/scripts/*.py .ai/hooks/*.py
python3 .ai/scripts/build_repo_map.py
```

```text
repo_lookup(query="<task terms>")                      # Pi
python3 .ai/scripts/repo_lookup.py "<task terms>"       # Claude Code fallback
```

```text
clarify → explore → plan → implement → verify → review → report
timebox=<minutes> | context=interview|research|maintenance
```

## Sources

- [Steering Claude Code: when to use CLAUDE.md, skills, hooks, and subagents — Claude.com](https://www.claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more)
- [Agent Skills best practices — platform.claude.com](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Claude Code `.claude` directory: CLAUDE.md, rules, hooks, and skills map — mer.vin](https://mer.vin/2026/05/claude-code-claude-directory-claude-md-rules-hooks-and-skills-map/)
- [Cursor Rules Best Practices — morphllm.com](https://www.morphllm.com/cursor-rules-best-practices)
- [JIT-Context: the Just-In-Time Context OS for AI Agents](https://ypbind.de/maus/projects/learning/)
- [Context Engineering for Coding Agents 2026: What Works](https://www.heyuan110.com/posts/ai/2026-06-16-context-engineering-2026/)
- [Claude Code was burning tokens until I put a gate in front of it — HackerNoon](https://hackernoon.com/claude-code-was-burning-tokens-until-i-put-a-gate-in-front-of-it)
- [Feature request: hook surface for dedup before memory injection — claudeissues.com](https://claudeissues.com/issue/55988-feature-request-hook-surface-that-fires-before-memory-injection-so-users-can-ded)
- [How Claude Code Memory Works: CLAUDE.md and Auto Memory — fast.io](https://fast.io/resources/claude-code-memory-context-guide.md)
- [AI coding assistant memory systems compared: Claude vs Gemini vs Codex vs Windsurf vs Cursor — mer.vin](https://mer.vin/2025/12/ai-coding-assistant-memory-systems-compared-claude-vs-gemini-vs-codex-vs-windsurf-vs-cursor/)
- [Windsurf Memories documentation — docs.windsurf.com](https://docs.windsurf.com/windsurf/memories)
- [Repository Map Pattern (Aider): AST + PageRank for Dynamic Code Context](https://agentpatterns.ai/context-engineering/repository-map-pattern/)
- [Claude repeatedly uses inline imports despite being told not to — claudeissues.com](https://claudeissues.com/issue/21813-claude-repeatedly-uses-inline-imports-despite-being-told-not-to)
- [How to teach your coding agent with AGENTS.md — ericmjl.github.io](https://ericmjl.github.io/blog/2025/10/4/how-to-teach-your-coding-agent-with-agentsmd/)
- [Claude Code doesn't read your AGENTS.md — makandracards.com](https://makandracards.com/makandra/626671-claude-code-read-agents-md)
- [Claude Code Stop hooks — amitkoth.com](https://amitkoth.com/claude-code-stop-hooks)
- [Agent Memory Is a Cache With No Invalidation Policy — tianpan.co](https://tianpan.co/blog/2026-05-16-agent-memory-cache-without-invalidation-policy)
- [Delete Redundant Comments — joshka.net](https://www.joshka.net/practice/patterns/delete-redundant-comments/)
- [65961: model Claude verbose code comments by default, ignores instructions to stop — claudeissues.com](https://claudeissues.com/issue/65961-model-claude-verbose-code-comments-by-default-ignores-instructions-to-stop)
- ["Stop writing rules in AGENTS.md: use agent hooks" — evilmartians.com](https://evilmartians.com/chronicles/stop-writing-rules-in-agents-md-use-agent-hooks-and-nano-staged-instead)
- [Junction Panel: one-agent-one-task discipline, scope-creep stats](https://junctionpanel.dev/blog/one-agent-one-task-discipline/)
- [Plan Mode reduces AI coding errors — verdent.ai](https://www.verdent.ai/guides/answers/plan-mode-reduce-ai-coding-errors)
- [Skills vs Slash Commands: One Works, One's a Prayer — medium.com](https://medium.com/@lakshminp/skills-vs-slash-commands-one-works-ones-a-prayer-fa6b065e78e6)
- [Claude Code Skills vs Slash Commands — mindstudio.ai](https://mindstudio.ai/blog/claude-code-skills-vs-slash-commands)
- [Automatically Correcting Large Language Models: a survey of self-correction strategies — arxiv.org](https://arxiv.org/pdf/2308.03188)
