# langchain-mq9

LangChain tools for the **mq9** AI-native async mailbox protocol.

Give your LangChain Agents a persistent, priority-aware inbox — powered by [RobustMQ](https://github.com/robustmq/robustmq).

## Install

```bash
pip install langchain-mq9
```

## Quick start

```python
from langchain_mq9 import Mq9Toolkit
from langchain.agents import AgentType, initialize_agent
from langchain_openai import ChatOpenAI

toolkit = Mq9Toolkit(server="nats://demo.robustmq.com:4222")
tools = toolkit.get_tools()

agent = initialize_agent(
    tools,
    ChatOpenAI(model="gpt-4o-mini"),
    agent=AgentType.OPENAI_FUNCTIONS,
    verbose=True,
)

agent.invoke({"input": "Create a mailbox for me to receive task results."})
```

## Tools

### `CreateMailboxTool`

Creates a mq9 mailbox and returns its `mail_id`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ttl` | int | 3600 | Mailbox TTL in seconds |

### `SendMessageTool`

Sends an async message to a mailbox.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mail_id` | str | — | Target mailbox address |
| `content` | str | — | Message content |
| `priority` | str | `"normal"` | `"high"`, `"normal"`, or `"low"` |

### `GetMessagesTool`

Retrieves pending messages from a mailbox.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mail_id` | str | — | Mailbox to read from |
| `limit` | int | 10 | Max messages to return |

## Mq9Toolkit

```python
from langchain_mq9 import Mq9Toolkit

toolkit = Mq9Toolkit(server="nats://localhost:4222")
tools = toolkit.get_tools()  # returns [CreateMailboxTool, SendMessageTool, GetMessagesTool]
```

## Multi-Agent example

See [`examples/agent_example.py`](examples/agent_example.py) for a complete example of two Agents communicating asynchronously via mq9.

## Why mq9?

- **Store-first**: messages persist until TTL expires — sender and receiver don't need to be online simultaneously
- **Priority queuing**: route urgent tasks ahead of background work
- **No consumer state**: simple, stateless protocol ideal for Agent workflows
- **Built on NATS**: fast, lightweight, zero broker dependencies
