# Python SDK

**Package:** `robustmq.mq9`  
**Requires:** Python 3.10+, `nats-py`

## Install

```bash
pip install robustmq
```

## Quick start

```python
import asyncio
from robustmq.mq9 import Client, Priority

async def main():
    async with Client(server="nats://demo.robustmq.com:4222") as client:

        # Create mailbox
        mailbox = await client.create(ttl=3600)

        # Send
        await client.send(mailbox.mail_id, b"hello", priority=Priority.NORMAL)

        # Subscribe
        async def handler(msg):
            print(msg.payload)

        sub = await client.subscribe(mailbox.mail_id, handler)

        # List metadata (no payload)
        metas = await client.list(mailbox.mail_id)
        # metas[i].msg_id, .priority, .ts

        # Delete
        await client.delete(mailbox.mail_id, metas[0].msg_id)

        await sub.unsubscribe()

asyncio.run(main())
```

## API

```python
Client(server="nats://demo.robustmq.com:4222", *, max_reconnect_attempts=10,
       reconnect_time_wait=2.0, request_timeout=5.0)

await client.connect()
await client.close()
# also: async with Client(...) as client

mailbox = await client.create(ttl, *, public=False, name="", desc="")
# → Mailbox(mail_id, public, name, desc)

await client.send(mail_id, payload, *, priority=Priority.NORMAL)
# payload: bytes | str | dict

sub = await client.subscribe(mail_id, async_cb, *, priority="*", queue_group="")
# → nats Subscription; call sub.unsubscribe() to cancel

metas = await client.list(mail_id)
# → list[MessageMeta(msg_id, priority, ts)]

await client.delete(mail_id, msg_id)
```

## Priority

```python
Priority.HIGH    # "high"
Priority.NORMAL  # "normal"
Priority.LOW     # "low"
```

## Public mailbox

```python
mailbox = await client.create(ttl=3600, public=True, name="task.queue", desc="Tasks")
# mail_id == "task.queue"
```

## Queue group (competitive consumption)

```python
await client.subscribe(mail_id, handler, queue_group="workers")
# Each message delivered to exactly one subscriber in the group
```

## Error handling

```python
import asyncio
from robustmq.mq9 import Client, Priority
from robustmq.mq9.client import Mq9Error
import nats.errors

async def main():
    # ── Connection failure ────────────────────────────────────────────────────
    # Raised when the NATS server is unreachable.
    try:
        client = Client(server="nats://unreachable-host:4222")
        await client.connect()
    except Exception as e:
        print(f"Connection failed: {e}")

    # ── Normal operation with mailbox / request errors ─────────────────────────
    async with Client(server="nats://demo.robustmq.com:4222") as client:

        # Mailbox not found (404) — raised as Mq9Error with .code == 404
        try:
            await client.list("m-does-not-exist")
        except Mq9Error as e:
            print(f"mq9 error {e.code}: {e}")   # mq9 error 404: mailbox not found

        # Request timeout — raised as Mq9Error wrapping asyncio.TimeoutError
        try:
            await client.list("m-some-mailbox")
        except Mq9Error as e:
            print(f"Timed out: {e}")

        # No responders — server not running or subject invalid
        try:
            mailbox = await client.create(ttl=3600)
        except Mq9Error as e:
            if isinstance(e.__cause__, nats.errors.NoRespondersError):
                print("No mq9 server is listening on this subject")

asyncio.run(main())
```

## Usage in AI Agent

Typical pattern: Agent creates its mailbox on startup, runs a message loop, and forwards results to another Agent.

```python
import asyncio
from robustmq.mq9 import Client, Priority

SERVER = "nats://demo.robustmq.com:4222"
DOWNSTREAM_MAIL_ID = "agent-b.inbox"   # well-known address of the next Agent


async def process(payload: bytes) -> bytes:
    """Business logic: transform the incoming task into a result."""
    task = payload.decode()
    return f"result:{task}".encode()


async def run_agent() -> None:
    async with Client(server=SERVER) as client:
        # 1. Create this Agent's own mailbox on startup
        mailbox = await client.create(ttl=3600)
        print(f"[agent] started, mail_id={mailbox.mail_id}")

        # 2. Main loop: subscribe and process messages
        async def handler(msg):
            print(f"[agent] received [{msg.priority.value}] {msg.payload.decode()}")
            result = await process(msg.payload)

            # 3. Send result to the downstream Agent
            await client.send(DOWNSTREAM_MAIL_ID, result, priority=Priority.NORMAL)
            print(f"[agent] forwarded result to {DOWNSTREAM_MAIL_ID}")

        sub = await client.subscribe(mailbox.mail_id, handler)

        # Keep the Agent running
        try:
            await asyncio.Future()   # run forever
        except asyncio.CancelledError:
            pass
        finally:
            await sub.unsubscribe()


if __name__ == "__main__":
    asyncio.run(run_agent())

## LangGraph Integration

The `langchain-mq9` tools work directly inside LangGraph nodes — each node can create a
mailbox, send messages, and receive replies without any extra wiring.

See the full working example in [demo/demo-langgraph/](../demo/demo-langgraph/) and the
tool reference in [docs/langchain-mq9.md](langchain-mq9.md).

```python
from langchain_mq9 import CreateMailboxTool, SendMessageTool, GetMessagesTool
from langgraph.graph import StateGraph, END
from typing import TypedDict

SERVER = "nats://demo.robustmq.com:4222"

class State(TypedDict):
    mail_id: str
    messages: str

async def node_inbox(state: State) -> State:
    create = CreateMailboxTool(server=SERVER)
    state["mail_id"] = await create._arun(ttl=120)
    return state

async def node_read(state: State) -> State:
    get = GetMessagesTool(server=SERVER)
    state["messages"] = await get._arun(mail_id=state["mail_id"], limit=10)
    return state

g = StateGraph(State)
g.add_node("inbox", node_inbox)
g.add_node("read", node_read)
g.set_entry_point("inbox")
g.add_edge("inbox", "read")
g.add_edge("read", END)
graph = g.compile()
```
