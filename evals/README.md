# Evals (Phase 3)

The quality story of the talk: the same pure code that the agent calls as a tool
(`src/agent/clash_checker.py`) scores the agent's answers, so the metric and the tool can never
disagree. Nothing here talks to the optimizer (it is out of the talk, the talk's write-up (D-04)).

| Piece | What |
| --- | --- |
| `golden.jsonl` | 14 Slovene questions with the constraints the scorers need (see the row schema below) |
| `evaluators/ntk_*.py` | **Generated** code-based Foundry evaluators (`uv run build-evaluators`): one self-contained `grade(sample, item)` each, built from `src/agent/{clash_checker,metrics,contract}.py` plus the program fixture. Do not edit by hand. |
| `evaluators/ntk_*.prompt.md` | The two LLM-judge prompts (completeness, Slovene register) for the cached full run |
| `registered.json` | Name → version of the evaluators last registered in the Foundry project (runs pin these versions) |
| `eval-full.yaml` | The recipe with the LLM judges (cached run) |
| `results/<label>.json` | Output of `uv run eval-local` (git-tracked for the labels used on stage) |
| `../eval.yaml` | The azd eval recipe written by `azd ai agent eval generate` (repo root, because `azure.yaml` has `project: .`) |

## Row schema (`golden.jsonl`)

| Field | Used by | Meaning |
| --- | --- | --- |
| `id` | harness | stable row id (`g01` …) |
| `query` | agent | the user message, Slovene |
| `attendee` | context | persona id (`maja`, `tomaz`, `nina`) |
| `day` | preferences, break coverage | requested day, ISO date |
| `earliest_start` | preferences | `HH:MM`; talks starting earlier are violations |
| `min_break_minutes` | break coverage | required free stretch between 10:00–14:00 (0 = default 30) |
| `tracks`, `note` | humans | what the row exercises |

For agent-target runs Foundry passes the answer as `item.sample.output_text`; for
query/response datasets it is `item.response`. The generated evaluators accept both.

## Metrics (scenario spec §Eval metrics)

| Evaluator | Type | Score |
| --- | --- | --- |
| `ntk_clash_free` | code | 1.0 clash-free · 1/(1+clashes) · ≤ 0.5 when an id is not in the program · 0 without an agenda |
| `ntk_preferences` | code | 1/(1+violations): talks before `earliest_start`, talks off the requested day |
| `ntk_break_coverage` | code | 1.0 with a ≥ `min_break_minutes` gap between 10:00–14:00, partial credit below |
| `ntk_completeness` | prompt (judge) | 1–5, requested day-parts and interests covered |
| `ntk_language` | prompt (judge) | 1–5, narrative in friendly-formal Slovene |

The live-run set on stage is the three code-based ones (fast, indisputable). Scores are
continuous 0–1 as the platform requires; the raw clash *count* (the headline number for the
chart) comes from `uv run eval-local`, which records both.

## Commands

```bash
uv run build-evaluators                # regenerate evals/evaluators/ from src/agent (deterministic)
uv run build-evaluators --register     # + register new versions in the Foundry project → registered.json
uv run eval-local --label v3-baseline  # local run against the hosted agent, same scorers (~4 min)
uv run eval-cloud --version 3          # the platform run: agent target + registered evaluators
uv run eval-cloud --version 3 --full   # + the two LLM judges (cached run, slower)
uv run eval-chart evals/results/v3-baseline.json evals/results/v4-improved.json   # → notebooks/assets/eval-clashes.svg
```

**`azd ai agent eval run` cannot drive these evaluators** — it references custom evaluators
without the initialization parameters and data mapping the service demands, so the run is rejected
(the talk's write-up, D-20/D-20b). `eval.yaml` is kept because `eval generate` wrote it and it documents the
recipe, but the working path is `uv run eval-cloud`, which builds the same run through the OpenAI
evals API. Cloud runs additionally need the App Insights ingestion role assignment from D-21;
without it every run fails with "Failed to export evaluation results to App Insights".

`eval-local` targets whatever version the endpoint serves; pin with `uv run rollback <n>` first
when you need a specific one. It runs four conversations at a time and does not pace itself
(`--concurrency 4 --delay 0`), which the deployment's 200,000 TPM / 200 RPM absorbs easily.

Until 2026-09-06 it ran strictly sequentially with a 45 s gap per row, because the deployment sat
at capacity 5 — 5,000 TPM *and* 5 requests/minute — where two concurrent conversations were enough
to make the agent return **empty answers with HTTP 200** (the talk's write-up, D-22/D-22b). The retry and the
`response.error` reporting stay in `_ask`: they are what tells a throttled row apart from a bad
answer, and `summarize()` still rates quality over answered rows only so a throttled run can never
masquerade as a quality regression.
