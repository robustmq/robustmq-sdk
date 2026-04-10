"""
LangGraph + mq9 demo — two Agent nodes communicate asynchronously via mq9 mailboxes.

Workflow:
  node_writer  →  generates a short paragraph
               →  sends it to node_reviewer's mailbox via mq9
  node_reviewer →  receives the paragraph
                →  produces a review comment
                →  sends it back to node_writer's mailbox
  node_writer  →  receives the review, finalises the response

mq9 acts as the async transport layer between nodes:
each node has its own private mailbox; messages are durable and priority-aware.

Run:
    cd demo/demo-langgraph
    pip install robustmq langchain-core langgraph langchain-openai
    export OPENAI_API_KEY=...
    python langgraph_mq9_demo.py
"""

from __future__ import annotations

import asyncio
import json
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from robustmq.mq9 import Client, Priority

# demo.robustmq.com is a public RobustMQ service for testing. Replace with your own server address if needed.
SERVER = "nats://demo.robustmq.com:4222"
LLM = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------


class WorkflowState(TypedDict):
    writer_mail_id: str
    reviewer_mail_id: str
    draft: str
    review: str
    final: str


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def node_writer(state: WorkflowState) -> WorkflowState:
    """Generate a draft paragraph and send it to node_reviewer via mq9."""
    async with Client(server=SERVER) as client:
        # Create writer's mailbox on first call
        if not state.get("writer_mail_id"):
            mb = await client.create(ttl=300)
            state["writer_mail_id"] = mb.mail_id
            print(f"[node_writer] mailbox: {mb.mail_id}")

        # If we already have a review, read it and produce the final version
        if state.get("review"):
            response = LLM.invoke(
                f"You wrote this draft:\n{state['draft']}\n\n"
                f"A reviewer said:\n{state['review']}\n\n"
                "Revise the paragraph incorporating the feedback. "
                "Return only the revised paragraph."
            )
            state["final"] = response.content
            print(f"[node_writer] final:\n{state['final']}")
            return state

        # First pass: generate a draft
        response = LLM.invoke(
            "Write a short paragraph (3–4 sentences) about the future of AI agents "
            "communicating asynchronously."
        )
        state["draft"] = response.content
        print(f"[node_writer] draft:\n{state['draft']}")

        # Send draft to reviewer
        payload = json.dumps({
            "draft": state["draft"],
            "reply_to": state["writer_mail_id"],
        }).encode()

        await client.send(state["reviewer_mail_id"], payload, priority=Priority.NORMAL)
        print(f"[node_writer] sent draft to reviewer ({state['reviewer_mail_id']})")

    return state


async def node_reviewer(state: WorkflowState) -> WorkflowState:
    """Receive the draft from mq9, produce a review, send it back."""
    async with Client(server=SERVER) as client:
        # Create reviewer's mailbox on first call
        if not state.get("reviewer_mail_id"):
            mb = await client.create(ttl=300)
            state["reviewer_mail_id"] = mb.mail_id
            print(f"[node_reviewer] mailbox: {mb.mail_id}")
            # Return immediately so node_writer can send to this mailbox
            return state

        # Receive the draft from mq9
        received: list[dict] = []

        async def on_message(msg):
            received.append(json.loads(msg.payload))

        sub = await client.subscribe(state["reviewer_mail_id"], on_message)
        await asyncio.sleep(1.0)   # drain buffered messages
        await sub.unsubscribe()

        if not received:
            print("[node_reviewer] no messages yet, waiting...")
            return state

        item = received[0]
        draft = item["draft"]
        reply_to = item["reply_to"]

        # Generate review
        response = LLM.invoke(
            f"Review the following paragraph and provide one specific, constructive "
            f"suggestion to improve it:\n\n{draft}"
        )
        review = response.content
        state["review"] = review
        print(f"[node_reviewer] review:\n{review}")

        # Send review back to writer
        await client.send(reply_to, review.encode(), priority=Priority.CRITICAL)
        print(f"[node_reviewer] sent review to writer ({reply_to})")

    return state


async def node_writer_finalise(state: WorkflowState) -> WorkflowState:
    """Read the review from mq9 and produce the final version."""
    async with Client(server=SERVER) as client:
        # Read review from writer's mailbox
        received: list[str] = []

        async def on_review(msg):
            received.append(msg.payload.decode())

        sub = await client.subscribe(state["writer_mail_id"], on_review)
        await asyncio.sleep(1.0)
        await sub.unsubscribe()

        if not received:
            print("[node_writer] no review received yet")
            return state

        state["review"] = received[0]

    return await node_writer(state)


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    g = StateGraph(WorkflowState)

    g.add_node("setup_reviewer", node_reviewer)   # creates reviewer mailbox
    g.add_node("writer_draft", node_writer)        # writes draft, sends to reviewer
    g.add_node("reviewer_review", node_reviewer)   # reads draft, sends review back
    g.add_node("writer_finalise", node_writer_finalise)  # reads review, writes final

    g.set_entry_point("setup_reviewer")
    g.add_edge("setup_reviewer", "writer_draft")
    g.add_edge("writer_draft", "reviewer_review")
    g.add_edge("reviewer_review", "writer_finalise")
    g.add_edge("writer_finalise", END)

    return g.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    graph = build_graph()

    initial: WorkflowState = {
        "writer_mail_id": "",
        "reviewer_mail_id": "",
        "draft": "",
        "review": "",
        "final": "",
    }

    result = await graph.ainvoke(initial)

    print("\n" + "=" * 60)
    print("DRAFT:\n", result["draft"])
    print("\nREVIEW:\n", result["review"])
    print("\nFINAL:\n", result["final"])
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
