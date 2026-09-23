# Bring Your Own Agent — LangGraph in production on Foundry Agent Service

The demo code from the NT konferenca 2026 talk *Pripelji svojega agenta* (Portorož, 23 September
2026). A plain LangGraph agent that builds an attendee's personal conference agenda, hosted on
Foundry Agent Service over the Responses protocol — and four
[marimo](https://docs.marimo.io/) notebooks that walk through the four things the talk demonstrates.
The slides are in [`slides/ntk2026-bring-your-own-agent.pdf`](slides/ntk2026-bring-your-own-agent.pdf).

The argument of the talk is in one line of `tests/test_purity.py`: **`src/agent/` imports nothing
from Azure.** The graph that answers on your laptop is the same object that answers in production.
Everything the platform adds — an identity, immutable versions, traces, per-conversation sandboxes
— it adds from the outside, and none of it is in the agent's code.

## What is here

```
src/agent/        the agent: a StateGraph, three deterministic tools, and a guard node
src/hosting/      the only code that knows about Foundry — fourteen lines of it in serve.py
notebooks/        the four demos, as reactive notebooks (see notebooks/README.md)
notebooks/sl/     the same four notebooks in Slovene
fixtures/         the conference programme the agent answers from, scraped from ntk.si
prompts/          the system prompts, one file per version
evals/            the golden set and the recipe used to score answers
scripts/          one command per thing the talk does
tests/            including test_purity.py, the one that makes the claim above checkable
slides/           the talk's slides, as a PDF
```

## Running it

You need [uv](https://docs.astral.sh/uv/) and Python 3.13. For the local demo you also need
[Ollama](https://ollama.com/) with a model pulled (`ollama pull gpt-oss:20b`); for anything cloud
you need an Azure subscription and [azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/overview)
with the `azure.ai.agents` extension.

```bash
uv sync --group demo          # --group demo is what pulls in marimo, for the notebooks
cp .env.example .env          # fill in what you have; nothing here needs a secret to start
uv run pytest -q              # the tests run with no network and no cloud
```

The demos are the notebooks, and they are the best place to start:

```bash
uv run marimo edit notebooks/            # pick one and read it top to bottom
NTK_DEMO_OFFLINE=1 uv run marimo edit notebooks/   # same thing with no network at all
```

`NTK_DEMO_OFFLINE=1` makes every notebook answer from `notebooks/cache/*.json` instead of calling a
model or the cloud. That switch exists because conference wi-fi is conference wi-fi, but it is also
the easiest way to read the notebooks without setting anything up.

To run the agent itself, locally, over the same protocol Foundry serves it with:

```bash
LLM_PROVIDER=ollama PORT=8088 uv run python -m hosting.serve
uv run act1                              # ask it a question and print what it did
```

## Deploying it

`azure.yaml` declares the Foundry project, the model deployment and the hosted agent. With an
Azure subscription and the agent extension installed:

```bash
azd provision                 # creates the Foundry project and the model deployment
azd deploy                    # packs this repo, ships it, waits for the version to go active
uv run rollback --list        # every deploy is an immutable version, with its traffic split
```

`langgraph.json` is the shorter route: it names the graph and lets the platform start the server,
with no hosting code of your own at all.

## The guard

`NTK_ENFORCE_CONSTRAINTS=1` adds one node to the graph. It re-reads the agenda the model produced,
checks it against the attendee's real constraints with ordinary Python, and sends it back to be
fixed when it does not hold. The talk's optional demo (`notebooks/04_guard.py`) is this node
catching the deployed agent putting a talk in someone's schedule after they have already left. It
is not a better prompt — it is a deterministic checker over the model's output.

## Links

<!-- links:start -->

Every link from the talk's speaker notes, grouped by topic.

**The graph**

- [LangChain docs](https://docs.langchain.com/oss/python/langchain/overview)
- [LangChain and LangGraph 1.0 (October 2025)](https://www.langchain.com/blog/langchain-langgraph-1dot0)
- [LangGraph docs](https://docs.langchain.com/oss/python/langgraph/overview)
- [The graph API: state, nodes, edges](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [Workflows and agents in LangGraph](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [LangChain tools (@tool, args schema)](https://docs.langchain.com/oss/python/langchain/tools)
- [The prebuilt agent loop this graph started from](https://docs.langchain.com/oss/python/langchain/agents)
- [langgraph.json — the no-Python hosting route](https://docs.langchain.com/langsmith/cli)
- [LangGraph on GitHub](https://github.com/langchain-ai/langgraph)
- [langgraph on PyPI](https://pypi.org/project/langgraph/)

**The platform**

- [What is Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/what-is-foundry)
- [Foundry model deployment types](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types)
- [Foundry Agent Service overview](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)
- [Hosted agents — what runs your code](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Deploying a hosted agent as code](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code)
- [Hosted agent quickstart](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [LangGraph on hosted agents](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-hosted-agents)
- [The hosted agent contract: Responses and other protocols](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agent-contract)
- [Hosted agent sessions](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-sessions)
- [Agent identity — the agent's own Entra principal](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-identity)
- [Publishing an agent to Teams and Microsoft 365 Copilot](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot)
- [Foundry guardrails — content safety, not the guard in this graph](https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview)
- [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/)
- [Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/overview)
- [azd command reference](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/reference)

**Other ways to run it**

- [Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/overview)
- [LangSmith Deployment (formerly LangGraph Platform)](https://docs.langchain.com/langsmith/deployment)

**Watching it, and knowing whether it got better**

- [Tracing agents in Foundry](https://learn.microsoft.com/en-us/azure/foundry/observability/concepts/trace-agent-concept)
- [Setting up tracing for agents](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-setup)
- [Tracing a hosted agent (quickstart)](https://learn.microsoft.com/en-us/azure/foundry/observability/quickstarts/quickstart-tracing-hosted-agent)
- [OpenTelemetry gen_ai semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [The agent monitoring dashboard (the Monitor tab)](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard)
- [Agent insights (preview)](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/agent-insights)
- [Observability in Foundry: evaluation, monitoring, tracing](https://learn.microsoft.com/en-us/azure/foundry/concepts/observability)
- [Evaluating an agent in the portal](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluate-agent)
- [Evaluating a hosted agent (quickstart)](https://learn.microsoft.com/en-us/azure/foundry/observability/quickstarts/quickstart-evaluate-hosted-agent)
- [Built-in agent evaluators: tool calls, task adherence, intent resolution](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators)
- [Custom evaluators: code or an LLM judge](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators)
- [Human evaluation](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/human-evaluation)

**The demo surface**

- [marimo docs](https://docs.marimo.io/)
- [mo.ui.run_button — every live call sits behind one](https://docs.marimo.io/api/inputs/run_button/)
- [mo.mermaid — how the DAG gets drawn](https://docs.marimo.io/examples/markdown/mermaid/)
- [gpt-oss on Ollama (the model on the laptop)](https://ollama.com/library/gpt-oss)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [ntk.si — where the programme comes from](https://www.ntk.si/en)
- [This talk's repo](https://github.com/vykhand/ntk2026-foundry-as-langgraph)

<!-- links:end -->

## Notes

The conference programme in `fixtures/program.json` is a snapshot from ntk.si, refreshed with
`uv run fetch-program`. Talk ids are positional and change on every refresh, so nothing in the code
looks a talk up by id. One entry is marked `synthetic: true` and is not a real talk — it exists so
the demo has something to be rude about.

Comments in the code sometimes point at "the talk's write-up": that is the private build log for
this project, which is not published. The decisions it records that matter to someone reading this
code are in the comments themselves.

MIT licensed. It was written for a forty-five-minute talk, not for production — but the parts that
claim to be checked really are, and `uv run pytest -q` is how you check them.
