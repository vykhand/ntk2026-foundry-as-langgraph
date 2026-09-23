"""The Foundry hosting layer — the only place Azure/Foundry code is allowed.

* ``llm.py``   — builds the chat model (Foundry deployment or a local Ollama
                 model, switched by environment variables).
* ``app.py``   — exports the compiled graph that ``langgraph.json`` points at.
* ``serve.py`` — the explicit ~10-line ``ResponsesHostServer`` wrapper (the
                 one that goes on a slide).
"""
