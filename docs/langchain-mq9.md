# langchain-mq9

LangChain tools for the mq9 AI-native async mailbox protocol.

**Package:** `langchain-mq9`  
**Requires:** Python 3.10+, `langchain-core`, `robustmq`

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
tools = toolkit.get_tools()  # all 6 tools

agent = initialize_agent(
    tools,
    ChatOpenAI(model="gpt-4o-mini"),
    agent=AgentType.OPENAI_FUNCTIONS,
    verbose=True,
)

agent.invoke({"input": "Create a mailbox so other agents can send me tasks."})
```

## Toolkit

```python
from langchain_mq9 import Mq9Toolkit

toolkit = Mq9Toolkit(server="nats://demo.robustmq.com:4222")
tools = toolkit.get_tools()
# → [CreateMailboxTool, CreatePublicMailboxTool, SendMessageTool,
#    GetMessagesTool, ListMessagesTool, DeleteMessageTool]
```

## Tools

All 6 tools map 1:1 to the mq9 protocol operations defined in [mq9-protocol.md](mq9-protocol.md).

### `CreateMailboxTool`

Creates a private mailbox with a server-generated UUID as `mail_id`.

```python
from langchain_mq9 import CreateMailboxTool

tool = CreateMailboxTool(server="nats://demo.robustmq.com:4222")
mail_id = tool.run({"ttl": 3600})
# → "m-550e8400-e29b-41d4-a716-446655440000"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ttl` | int | 3600 | Mailbox TTL in seconds |

---

### `CreatePublicMailboxTool`

Creates a public mailbox with a human-readable, predictable name. The `mail_id` equals the name you provide, so other Agents can send to it by name without being told the address.

```python
from langchain_mq9 import CreatePublicMailboxTool

tool = CreatePublicMailboxTool(server="nats://demo.robustmq.com:4222")
result = tool.run({"name": "task.queue", "ttl": 86400, "desc": "Shared task queue"})
# → "Public mailbox created. mail_id='task.queue'"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | — | Mailbox name (used as mail_id) |
| `ttl` | int | 86400 | Mailbox TTL in seconds |
| `desc` | str | `""` | Optional description |

---

### `SendMessageTool`

Sends a message to any mailbox. The recipient does not need to be online — mq9 stores the message until TTL expires.

```python
from langchain_mq9 import SendMessageTool

tool = SendMessageTool(server="nats://demo.robustmq.com:4222")
tool.run({"mail_id": mail_id, "content": "Task complete.", "priority": "critical"})
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mail_id` | str | — | Target mailbox address |
| `content` | str | — | Message content |
| `priority` | str | `"normal"` | `"critical"`, `"urgent"`, or `"normal"` |

---

### `GetMessagesTool`

Subscribes to a mailbox and retrieves pending messages **with full payload**. Messages remain in the mailbox and will be re-delivered on the next subscribe.

```python
from langchain_mq9 import GetMessagesTool

tool = GetMessagesTool(server="nats://demo.robustmq.com:4222")
result = tool.run({"mail_id": mail_id, "limit": 10})
# → "Found 2 message(s) in mailbox 'm-001':
#     [1] priority=critical  content=Urgent: server down
#     [2] priority=normal  content=Daily report ready"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mail_id` | str | — | Mailbox to read from |
| `limit` | int | 10 | Max messages to return |

---

### `ListMessagesTool`

Returns metadata (msg_id, priority, timestamp) for all pending messages — **no payload**. Non-destructive: messages remain in the mailbox. Use this to inspect the queue or find a `msg_id` before deleting.

```python
from langchain_mq9 import ListMessagesTool

tool = ListMessagesTool(server="nats://demo.robustmq.com:4222")
result = tool.run({"mail_id": mail_id})
# → "2 message(s) in mailbox 'm-001':
#     msg_id=msg-001  priority=critical  ts=1234567890
#     msg_id=msg-002  priority=normal  ts=1234567891"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mail_id` | str | — | Mailbox to inspect |

---

### `DeleteMessageTool`

Deletes a specific message by `msg_id`. Use after processing a message to prevent re-delivery.

```python
from langchain_mq9 import DeleteMessageTool

tool = DeleteMessageTool(server="nats://demo.robustmq.com:4222")
tool.run({"mail_id": mail_id, "msg_id": "msg-001"})
# → "Message 'msg-001' deleted from mailbox 'm-001'."
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mail_id` | str | — | Mailbox containing the message |
| `msg_id` | str | — | Message ID to delete |

---

## Protocol coverage

| mq9 operation | Tool |
|---------------|------|
| `MAILBOX.CREATE` (private) | `CreateMailboxTool` |
| `MAILBOX.CREATE` (public) | `CreatePublicMailboxTool` |
| `MAILBOX.MSG.{id}.{priority}` (send) | `SendMessageTool` |
| `MAILBOX.MSG.{id}.*` (subscribe) | `GetMessagesTool` |
| `MAILBOX.LIST.{id}` | `ListMessagesTool` |
| `MAILBOX.DELETE.{id}.{msg_id}` | `DeleteMessageTool` |

## Multi-Agent example

```python
import asyncio
from langchain_mq9 import (
    CreateMailboxTool, SendMessageTool,
    ListMessagesTool, GetMessagesTool, DeleteMessageTool,
)

SERVER = "nats://demo.robustmq.com:4222"

async def main():
    # Agent A: create a private mailbox
    mail_id = await CreateMailboxTool(server=SERVER)._arun(ttl=3600)
    print(f"Agent A mailbox: {mail_id}")

    # Agent B: send messages
    await SendMessageTool(server=SERVER)._arun(
        mail_id=mail_id, content="Urgent: data pipeline failed", priority="critical"
    )
    await SendMessageTool(server=SERVER)._arun(
        mail_id=mail_id, content="Weekly report attached", priority="normal"
    )

    # Agent A: inspect queue (no payload)
    print(await ListMessagesTool(server=SERVER)._arun(mail_id=mail_id))

    # Agent A: read messages with content
    print(await GetMessagesTool(server=SERVER)._arun(mail_id=mail_id))

    # Agent A: delete processed message
    # (get msg_id from list first)

asyncio.run(main())
```

## Why mq9 for Agents?

| Feature | Benefit |
|---------|---------|
| Store-first delivery | Sender and receiver don't need to be online simultaneously |
| Priority queuing | Urgent tasks processed before background work |
| TTL-based cleanup | No manual message management required |
| No consumer state | Stateless protocol — perfect for stateless Agent workflows |
| Public mailboxes | Shared channels with predictable addresses, no service discovery needed |
