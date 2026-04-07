# RobustMQ SDK

Multi-language client SDK for [RobustMQ](https://github.com/robustmq/robustmq) — a unified messaging engine built for the AI era.

RobustMQ is a single-binary broker that natively supports MQTT, Kafka, NATS, AMQP, and **mq9** on a shared storage layer. One message written once, consumable by any protocol.

---

## Repository structure

```text
robustmq-sdk/
├── docs/
│   └── mq9-protocol.md     # Protocol specification
├── python/                  # ✅ Implemented — AI/Agent ecosystem (LangChain, AutoGen)
├── rust/                    # 🚧 Scaffolded — reference implementation
├── go/                      # 🚧 Scaffolded — cloud-native infrastructure
├── javascript/              # 🚧 Scaffolded — Node.js + frontend agents
├── java/                    # 🚧 Scaffolded — enterprise, Kafka ecosystem
└── csharp/                  # 🚧 Scaffolded — enterprise, Microsoft ecosystem
```

---

## Protocol coverage

### mq9: AI Agent mailbox protocol

mq9 solves a fundamental problem in multi-agent systems: when Agent A sends a message to Agent B and B is offline, the message is gone. mq9 gives every agent a durable mailbox.

**Core concepts:**

- **Mailbox (`mail_id`)** — an agent's communication address, TTL-driven, auto-cleaned
  - Private: system-generated UUID (not guessable, security boundary)
  - Public: user-defined name (e.g. `task.queue`, `analytics.result`)
- **Priority** — `high` / `normal` / `low`; cross-priority ordering guaranteed by storage layer
- **Store-first delivery** — messages persist until TTL expires; subscriber gets all non-expired + future messages on connect

**Protocol operations (NATS subject-based):**

| Operation | Subject |
| --------- | ------- |
| Create mailbox | `$mq9.AI.MAILBOX.CREATE` |
| Send message | `$mq9.AI.MAILBOX.MSG.{mail_id}.{priority}` |
| Subscribe (all priorities) | `$mq9.AI.MAILBOX.MSG.{mail_id}.*` |
| List messages | `$mq9.AI.MAILBOX.LIST.{mail_id}` |
| Delete message | `$mq9.AI.MAILBOX.DELETE.{mail_id}.{msg_id}` |
| Discover public mailboxes | `$mq9.AI.PUBLIC.LIST` |

See [docs/mq9-protocol.md](docs/mq9-protocol.md) for the full protocol specification.

mq9 runs on the NATS text protocol — any NATS client connects directly. The SDKs here provide idiomatic wrappers with mq9-specific semantics.

### MQTT

Full MQTT 3.1 / 3.1.1 / 5.0 support. Features include QoS 0/1/2, shared subscriptions, session persistence, offline messages, retained messages, delayed publishing, exclusive subscriptions, and will messages. MQTT SDKs are planned after mq9 stabilizes.

---

## Quick start — Python

```bash
pip install robustmq
```

```python
import asyncio
from robustmq.mq9 import Client, Message

async def main():
    async with Client(server="nats://localhost:4222") as client:
        # Create a private mailbox (TTL 1 hour)
        mailbox = await client.create(ttl=3600)

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

**Worker pool (competitive consumption):**

```python
async with Client() as client:
    async def worker(msg: Message) -> None:
        print(f"Worker got: {msg.payload}")

    # Each message delivered to exactly one worker
    await client.subscribe("task.queue", worker, queue_group="workers")
    await asyncio.Future()
```

See [python/README.md](python/README.md) for the full Python SDK reference.

---

## Why these SDKs exist

Although mq9 runs over NATS (any NATS client works), idiomatic SDK wrappers provide:

1. **mq9-native API** — `client.create()`, `client.send()`, `client.subscribe()` instead of raw subject construction
2. **Priority routing** — abstracts the `high`/`normal`/`low` subject encoding
3. **Queue group consumer** — simplifies competitive consumption setup
4. **LangChain / AutoGen integration** — mq9 as a native tool or memory backend for AI agents
5. **Type safety** — typed message payloads and structured responses

---

## Related

- [RobustMQ](https://github.com/robustmq/robustmq) — the broker
- [mq9 Protocol Specification](docs/mq9-protocol.md) — full protocol reference
