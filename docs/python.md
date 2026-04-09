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
