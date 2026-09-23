"""The entire Foundry hosting wrapper. Everything above this line is plain LangGraph."""
import os

from langchain_azure_ai.agents.hosting import ResponsesHostServer

from hosting.app import graph


def main() -> None:
    ResponsesHostServer(graph).run(port=int(os.environ.get("PORT", "8088")))


if __name__ == "__main__":
    main()
