"""Basic LangGraph agent powered by ChatGPT.

Reads the OpenAI API key from secrets.txt in the same directory.
"""

import os
from pathlib import Path

from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph

# Load API key from secrets.txt
# Supports both bare key ("sk-...") and "OPENAI_API_KEY=sk-..." formats
SECRETS_FILE = Path(__file__).parent / "secrets.txt"
raw = SECRETS_FILE.read_text().strip()
api_key = raw.split("=", 1)[1] if "=" in raw else raw
if not api_key:
    raise RuntimeError(
        f"No API key found. Add your OpenAI key to: {SECRETS_FILE}"
    )
os.environ["OPENAI_API_KEY"] = api_key

llm = ChatOpenAI(model="gpt-4o-mini")


def chatbot(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}


graph = StateGraph(MessagesState)
graph.add_node("chatbot", chatbot)
graph.add_edge(START, "chatbot")
agent = graph.compile()


def main():
    print("LangGraph Agent (type 'quit' to exit)")
    print("-" * 40)
    while True:
        user_input = input("\nYou: ").strip()
        if not user_input or user_input.lower() in ("quit", "exit"):
            break
        result = agent.invoke({"messages": [("user", user_input)]})
        print(f"\nAgent: {result['messages'][-1].content}")


if __name__ == "__main__":
    main()
