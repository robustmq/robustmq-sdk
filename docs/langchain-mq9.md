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
tools = toolkit.get_tools()

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
# → [CreateMailboxTool, SendMessageTool, GetMessagesTool]
```

## Tools

### `CreateMailboxTool`

Creates a mq9 mailbox and returns its `mail_id`. The LLM calls this when an Agent needs a persistent async inbox.

```python
from langchain_mq9 import CreateMailboxTool

tool = CreateMailboxTool(server="nats://demo.robustmq.com:4222")
mail_id = tool.run({"ttl": 3600})
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ttl` | int | 3600 | Mailbox TTL in seconds |

### `SendMessageTool`

Sends a message to another Agent's mailbox. The recipient does not need to be online — mq9 stores the message until TTL expires.

```python
from langchain_mq9 import SendMessageTool

tool = SendMessageTool(server="nats://demo.robustmq.com:4222")
tool.run({"mail_id": mail_id, "content": "Task complete.", "priority": "high"})
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mail_id` | str | — | Target mailbox address |
| `content` | str | — | Message content |
| `priority` | str | `"normal"` | `"high"`, `"normal"`, or `"low"` |

### `GetMessagesTool`

Retrieves pending messages from a mailbox. The LLM calls this when an Agent needs to check its inbox.

```python
from langchain_mq9 import GetMessagesTool

tool = GetMessagesTool(server="nats://demo.robustmq.com:4222")
result = tool.run({"mail_id": mail_id, "limit": 10})
print(result)
# Found 1 message(s) in mailbox m-abc-001:
#   [1] priority=high  content=Task complete.
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mail_id` | str | — | Mailbox to read from |
| `limit` | int | 10 | Max messages to return |

## Multi-Agent communication

```python
import asyncio
from langchain_mq9 import CreateMailboxTool, SendMessageTool, GetMessagesTool

SERVER = "nats://demo.robustmq.com:4222"

async def main():
    # Agent A creates a mailbox
    create = CreateMailboxTool(server=SERVER)
    mail_id = await create._arun(ttl=3600)
    print(f"Agent A mailbox: {mail_id}")

    # Agent B sends a message to Agent A
    send = SendMessageTool(server=SERVER)
    await send._arun(mail_id=mail_id, content="Analysis complete.", priority="high")

    # Agent A reads its inbox
    get = GetMessagesTool(server=SERVER)
    result = await get._arun(mail_id=mail_id)
    print(result)

asyncio.run(main())
```

## Why mq9 for Agents?

| Feature | Benefit |
|---------|---------|
| Store-first delivery | Sender and receiver don't need to be online at the same time |
| Priority queuing | Urgent tasks are processed before background work |
| TTL-based cleanup | No manual message management required |
| No consumer state | Stateless protocol — perfect for stateless Agent workflows |
