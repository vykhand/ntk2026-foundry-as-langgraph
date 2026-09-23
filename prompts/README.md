# Prompts

Tracked system prompts. The graph reads one of them at startup (`src/agent/prompt.py`):

| Precedence | Source |
| --- | --- |
| 1 | `NTK_SYSTEM_PROMPT` — full prompt text in an env var (env vars are immutable per hosted version) |
| 2 | `NTK_PROMPT_FILE` — path relative to the repo root |
| 3 | `prompts/baseline_v1.md` |

All three files below share the **same output contract** (the ```json block plus a short Slovene
explanation). That is deliberate: if the "before" prompt did not specify the format, its answers
would not parse and every metric would score zero for the wrong reason — a formatting failure
dressed up as a quality failure. Only the *behavioural* guidance differs between them.

## `baseline_v0.md` — the naive prompt (candidate version N)

What anyone writes in five minutes: who you are, which tools exist, what the answer should look
like. No procedure, no rules, no mention of constraints. Added 2026-09-06 when `baseline_v1`
turned out not to be mediocre enough to fail anything (the talk's write-up, S-08).

## `baseline_v1.md` — the engineered baseline

Deliberately mediocre *by construction*: it does not require calling `clash_checker` before
answering and never mentions coffee breaks or the attendee's earliest hour. It scores
**1.00 / 1.00 / 1.00 on every golden row anyway** — see S-08. Kept because versions 1–3 of the
hosted agent run it, so it is what the rollback demo rolls back to.

## `improved_v2.md` — the fix (version N+1)

Mandatory `clash_checker` before every answer, explicit rules for the earliest hour, the coffee
gap, the attendee's `latest_end`, and — rule 7 — **always call `preferences`, even when the user
names the day and the topics themselves**, because the constraints live in the profile and real
users do not repeat them.

## Why the golden set matters more than the prompt

Measured 2026-09-06: the original 14 golden questions all **stated their constraints inline**
("nič pred deveto", "ob štirih grem domov", "brez prekrivanj"). A prompt cannot make a difference
to a request that already contains the answer, which is why every prompt scored the same. Rows
g15–g22 name the attendee but say nothing about their constraints, so the agent has to fetch the
profile — that is the first version of this eval where prompt quality can actually show up.
