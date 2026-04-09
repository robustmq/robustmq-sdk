# LangGraph + mq9 Demo

Two LangGraph Agent nodes communicate asynchronously via mq9 mailboxes.

## Scenario

```
node_writer   →  generates a draft paragraph (gpt-4o-mini)
              →  sends draft to node_reviewer's mailbox via mq9
node_reviewer →  receives draft from mq9
              →  produces a review comment
              →  sends review back to node_writer's mailbox
node_writer   →  receives review from mq9
              →  produces the final revised paragraph
```

mq9 acts as the async transport layer between nodes: each node has its own private mailbox;
messages are durable and priority-aware. Nodes do not need to be running at the same time.

## Prerequisites

- Python 3.10+
- Access to `nats://demo.robustmq.com:4222` (public RobustMQ service), or run your own RobustMQ instance
- OpenAI API key

## Install

```bash
cd demo/demo-langgraph
pip install robustmq langchain-core langgraph langchain-openai
```

## Run

```bash
export OPENAI_API_KEY=sk-...
python langgraph_mq9_demo.py
```

## Expected output

```
[node_reviewer] mailbox: m-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
[node_writer] mailbox: m-yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
[node_writer] draft:
AI agents are increasingly capable of communicating across distributed systems ...

[node_writer] sent draft to reviewer (m-xxxxxxxx-...)
[node_reviewer] review:
Consider adding a concrete example of how store-first semantics enable ...

[node_reviewer] sent review to writer (m-yyyyyyyy-...)
[node_writer] final:
AI agents are increasingly capable of communicating across distributed systems.
For instance, store-first semantics allow an agent to publish a task and shut down ...

============================================================
DRAFT:
 AI agents are increasingly capable of communicating across distributed systems ...

REVIEW:
 Consider adding a concrete example of how store-first semantics enable ...

FINAL:
 AI agents are increasingly capable of communicating across distributed systems.
 For instance, store-first semantics allow an agent to publish a task and shut down ...
============================================================
```

## What this demo shows

| Concept | Where |
|---------|-------|
| Each LangGraph node owns a private mq9 mailbox | `node_writer` and `node_reviewer` each call `client.create()` |
| Async handoff between nodes via mq9 | writer sends draft; reviewer subscribes, reads, replies |
| Store-first semantics | reviewer can start after writer has already published |
| Priority-ordered delivery | draft sent as `NORMAL`, review sent back as `HIGH` |
| LangChain LLM inside a LangGraph node | `ChatOpenAI(model="gpt-4o-mini")` called inside each node |

## Using `langchain-mq9` tools instead

If you prefer LangChain tool wrappers rather than calling the mq9 client directly,
the `langchain-mq9` package provides drop-in tools for all protocol operations:

```bash
pip install langchain-mq9
```

See [docs/langchain-mq9.md](../../docs/langchain-mq9.md) and [demo/demo-langchain-mq9/](../demo-langchain-mq9/).
