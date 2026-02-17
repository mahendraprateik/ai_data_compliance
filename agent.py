"""Basic LangGraph agent powered by ChatGPT.

Reads the OpenAI API key from secrets.txt in the same directory.
Persists chat history across sessions in the chat_history/ folder.
"""

import json
import os
from datetime import datetime
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

CHAT_HISTORY_DIR = Path(__file__).parent / "chat_history"
SHORT_TERM_MEMORY_LIMIT = 50  # max past messages to reload as context

llm = ChatOpenAI(model="gpt-4o-mini")


def chatbot(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}


graph = StateGraph(MessagesState)
graph.add_node("chatbot", chatbot)
graph.add_edge(START, "chatbot")
agent = graph.compile()


def load_history() -> list[dict]:
    """Load recent messages from previous session files."""
    if not CHAT_HISTORY_DIR.exists():
        return []

    session_files = sorted(CHAT_HISTORY_DIR.glob("session_*.json"))
    if not session_files:
        return []

    all_messages: list[dict] = []
    for path in session_files:
        with open(path) as f:
            all_messages.extend(json.load(f))

    # Keep only the most recent messages as short-term memory
    return all_messages[-SHORT_TERM_MEMORY_LIMIT:]


def save_session(messages: list[dict]) -> None:
    """Save this session's messages to a new file in chat_history/."""
    CHAT_HISTORY_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = CHAT_HISTORY_DIR / f"session_{timestamp}.json"
    with open(path, "w") as f:
        json.dump(messages, f, indent=2)


def main():
    print("LangGraph Agent (type 'quit' to exit)")
    print("-" * 40)

    past_messages = load_history()
    if past_messages:
        print(f"(Loaded {len(past_messages)} messages from previous sessions)")

    # Convert stored dicts to tuples for LangGraph
    history = [(m["role"], m["content"]) for m in past_messages]
    session_messages: list[dict] = []

    while True:
        user_input = input("\nYou: ").strip()
        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        history.append(("user", user_input))
        result = agent.invoke({"messages": history})

        reply = result["messages"][-1].content
        history.append(("assistant", reply))

        session_messages.append({"role": "user", "content": user_input})
        session_messages.append({"role": "assistant", "content": reply})

        print(f"\nAgent: {reply}")

    if session_messages:
        save_session(session_messages)
        print(f"\nSession saved ({len(session_messages)} messages).")


if __name__ == "__main__":
    main()
