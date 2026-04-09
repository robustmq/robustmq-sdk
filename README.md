# RobustMQ SDK

Multi-language client SDK for [RobustMQ](https://github.com/robustmq/robustmq) — a unified messaging engine built for the AI era.

RobustMQ is a single-binary broker that natively supports MQTT, Kafka, NATS, AMQP, and **mq9** on a shared storage layer.

---

## mq9: AI Agent mailbox protocol

mq9 gives every agent a durable mailbox. Messages persist until TTL expires — senders and receivers do not need to be online simultaneously.

| Concept | Description |
|---------|-------------|
| **Mailbox** | Agent's address. Private (UUID) or public (user-defined name). TTL-driven, auto-cleaned. |
| **Priority** | `high` / `normal` / `low`. Cross-priority ordering guaranteed by storage. |
| **Store-first** | Subscriber gets all non-expired messages on connect, then real-time going forward. |
| **Queue group** | Multiple subscribers sharing a group receive each message exactly once. |

**Protocol operations:**

| Operation | Subject |
|-----------|---------|
| Create mailbox | `$mq9.AI.MAILBOX.CREATE` |
| Send message | `$mq9.AI.MAILBOX.MSG.{mail_id}.{priority}` |
| Subscribe | `$mq9.AI.MAILBOX.MSG.{mail_id}.*` |
| List metadata | `$mq9.AI.MAILBOX.LIST.{mail_id}` |
| Delete message | `$mq9.AI.MAILBOX.DELETE.{mail_id}.{msg_id}` |

Full spec: [docs/mq9-protocol.md](docs/mq9-protocol.md)

---

## SDK status

| Language | Package | Status |
|----------|---------|--------|
| Python | `robustmq.mq9` | ✅ Implemented |
| Go | `mq9` | ✅ Implemented |
| JavaScript | `@robustmq/mq9` | ✅ Implemented |
| Java | `io.robustmq.mq9` | ✅ Implemented |
| C# | `RobustMQ.Mq9` | ✅ Implemented |
| Rust | `robustmq::mq9` | ✅ Implemented |

---

## Quick start

```python
# Python
from robustmq.mq9 import Client, Priority

async with Client("nats://localhost:4222") as client:
    mailbox = await client.create(ttl=3600)
    await client.send(mailbox.mail_id, b"hello", priority=Priority.NORMAL)

    async def handler(msg):
        print(msg.payload)

    await client.subscribe(mailbox.mail_id, handler)
```

See language-specific docs below for all SDKs.

---

## SDK documentation

| Language | Docs | Demo |
|----------|------|------|
| Python | [docs/python.md](docs/python.md) | [demo/demo.py](demo/demo.py) |
| Go | [docs/go.md](docs/go.md) | [demo/demo.go](demo/demo.go) |
| JavaScript | [docs/javascript.md](docs/javascript.md) | [demo/demo.ts](demo/demo.ts) |
| Java | [docs/java.md](docs/java.md) | [demo/Demo.java](demo/Demo.java) |
| C# | [docs/csharp.md](docs/csharp.md) | [demo/demo.cs](demo/demo.cs) |
| Rust | [docs/rust.md](docs/rust.md) | [demo/demo.rs](demo/demo.rs) |

---

## Running the demo

Each demo script connects to `nats://localhost:4222` and runs the same scenario:
1. Create a private mailbox (TTL 60s)
2. Send 3 messages (high / normal / low priority)
3. Subscribe and print received messages
4. List mailbox metadata, delete one message
5. Create a public mailbox

```bash
# Python
cd python && pip install -e .
python ../demo/demo.py

# Go
cd go && go run ../demo/demo.go

# JavaScript
cd javascript && npm install && npx ts-node ../demo/demo.ts

# Java
cd java && mvn compile
mvn exec:java -Dexec.mainClass=Demo

# Rust
cd rust && cargo run --example demo

# C#
cd csharp && dotnet run --project Demo
```

---

## Repository layout

```
python/          # Python SDK
go/              # Go SDK
javascript/      # JavaScript/TypeScript SDK
java/            # Java SDK
csharp/          # C# SDK
rust/            # Rust SDK
docs/            # SDK docs + protocol spec
demo/            # End-to-end demo scripts (one per language)
VERSION          # Canonical version (currently 1.0.0)
```

---

## Related

- [RobustMQ](https://github.com/robustmq/robustmq) — the broker
- [mq9 Protocol Specification](docs/mq9-protocol.md) — full protocol reference
