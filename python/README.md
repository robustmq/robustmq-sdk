# robustmq-python

Python SDK for [RobustMQ](https://github.com/robustmq/robustmq) — mq9 AI-native async messaging.

## Install

```bash
pip install robustmq
```

Requires Python 3.10+. The only runtime dependency is [`nats-py`](https://github.com/nats-io/nats.py).

## Quick start

```python
import asyncio
from robustmq.mq9 import Client, Message

async def main():
    async with Client(server="nats://localhost:4222") as client:
        # Create a private mailbox (TTL 1 hour)
        mailbox = await client.create(ttl=3600)
        print(f"Mailbox: {mailbox.mail_id}")

        # Send a message
        await client.send(mailbox.mail_id, {"task": "summarize", "doc": "abc"})

        # Receive messages
        async def handler(msg: Message) -> None:
            print(f"[{msg.priority}] {msg.payload}")
            await client.delete(msg.mail_id, msg.msg_id)

        sub = await client.subscribe(mailbox.mail_id, handler)
        await asyncio.sleep(5)
        await sub.unsubscribe()

asyncio.run(main())
```

## Worker pool (competitive consumption)

```python
async with Client() as client:
    # Multiple workers share a queue group — each message goes to exactly one worker
    async def worker(msg: Message) -> None:
        print(f"Worker got: {msg.payload}")

    await client.subscribe("task.queue", worker, queue_group="workers")
    await asyncio.Future()  # run forever
```

## Public mailbox discovery

```python
async with Client() as client:
    mailboxes = await client.list_public()
    for mb in mailboxes:
        print(mb.mail_id, mb.desc)
```

## API reference

### `Client(server, *, max_reconnect_attempts, reconnect_time_wait, request_timeout, name)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `server` | `nats://localhost:4222` | NATS server URL |
| `max_reconnect_attempts` | `10` | Auto-reconnect attempts (-1 = unlimited) |
| `reconnect_time_wait` | `2.0` | Seconds between reconnect attempts |
| `request_timeout` | `5.0` | Request/reply timeout in seconds |

### Methods

| Method | Description |
|--------|-------------|
| `await client.connect()` | Connect to server |
| `await client.close()` | Drain and disconnect |
| `await client.create(ttl, *, public, name, desc)` | Create mailbox → `Mailbox` |
| `await client.send(mail_id, payload, *, priority)` | Send message |
| `await client.subscribe(mail_id, callback, *, priority, queue_group)` | Subscribe → `Subscription` |
| `await client.list(mail_id)` | List messages → `list[Message]` |
| `await client.delete(mail_id, msg_id)` | Delete message |
| `await client.list_public()` | Discover public mailboxes → `list[Mailbox]` |

`Client` is also an async context manager (`async with Client(...) as client`).

## Running tests

```bash
cd python
pip install -e ".[dev]"
pytest
```

No live server required — all tests use mocks.
