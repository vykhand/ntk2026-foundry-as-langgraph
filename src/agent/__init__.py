"""NTK asistent — the agent proper.

Everything in this package is plain LangGraph / LangChain: a graph, three tools,
a prompt and a handful of pure functions. There is deliberately no Foundry,
Azure or hosting code here; that lives in ``src/hosting`` (see
``tests/test_purity.py`` for the enforced rule).
"""
