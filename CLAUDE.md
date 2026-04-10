# RobustMQ SDK — Project Guide

## What is RobustMQ

RobustMQ is a **unified messaging platform written in Rust** — one binary, one broker, zero external dependencies.
It natively runs MQTT, Kafka, NATS, AMQP, and mq9 on a **shared pluggable storage layer**.

Core architecture (3-tier, fully decoupled):
- **Broker** (stateless compute): protocol parsing, TCP/TLS/WebSocket/WSS/QUIC
- **Meta Service**: Raft-based cluster coordination, replaces ZooKeeper
- **Storage Engine**: pluggable — Memory / RocksDB / File Segment, S3 tiering

Key differentiators vs Kafka/NATS:
- Multi-protocol on one deployment (no bridging, no data silos)
- Compute-storage separation → scale independently in seconds (not hours)
- Rust: no GC pauses, predictable latency
- mq9: AI-native async mailbox protocol (see below)

## What this SDK is

Multi-language client SDK for RobustMQ. Currently implements **mq9** — more protocols (MQTT, Kafka, AMQP)
will be added as RobustMQ matures.

**Package naming strategy (Method A — single SDK per language):**
Each language ships one package that grows to cover all protocols via sub-modules.
Users install one package and import the protocol they need.

| Language   | Published package            | mq9 import/usage                              |
| ---------- | ---------------------------- | --------------------------------------------- |
| Python     | `robustmq` (PyPI)            | `from robustmq.mq9 import Client`             |
| Go         | `robustmq-sdk/go` (git tag)  | `import "github.com/robustmq/robustmq-sdk/go/mq9"` |
| JavaScript | `@robustmq/sdk` (npm)        | `import { MQ9Client } from '@robustmq/sdk/mq9'` |
| Java       | `com.robustmq:robustmq`  | `import com.robustmq.mq9.*`                   |
| Rust       | `robustmq` (crates.io)       | `use robustmq::mq9::MQ9Client`                |
| C#         | `RobustMQ` (NuGet)           | `using RobustMQ.Mq9`                          |

When new protocols are added (e.g. MQTT, Kafka), they live in sub-modules of the same package:
`robustmq.mqtt`, `@robustmq/sdk/mqtt`, `com.robustmq.mqtt`, `robustmq::mqtt`, etc.

The owner does not intervene in implementation details. Claude makes all technical decisions
and drives the project forward autonomously.

---

## Version management

Source of truth: root `VERSION` file (currently `0.3.5`).

When bumping the version, update `VERSION` and all 6 build files in one commit:

- Python: `python/pyproject.toml` + `python/robustmq/__init__.py`
- Rust: `rust/Cargo.toml`
- Go: git tag only (e.g. `v0.3.5`) — no file to update
- JavaScript: `javascript/package.json`
- Java: `java/pom.xml`
- C#: `csharp/RobustMQ.Mq9/RobustMQ.Mq9.csproj`

Also update version references in `demo/`, `docs/`, and `README.md`.

---

## SDK implementation status

| Language   | Package/Import          | Class       | NATS lib     | Status         |
| ---------- | ----------------------- | ----------- | ------------ | -------------- |
| Python     | `robustmq.mq9`          | `MQ9Client` | `nats-py`    | Implemented    |
| Rust       | `robustmq::mq9`         | `MQ9Client` | `async-nats` | Scaffolded     |
| Go         | `mq9` (pkg)             | `MQ9Client` | `nats.go`    | Scaffolded     |
| JavaScript | `@robustmq/sdk/mq9`     | `MQ9Client` | `nats` v2    | Scaffolded     |
| Java       | `com.robustmq.mq9`      | `MQ9Client` | `jnats`      | Scaffolded     |
| C#         | `RobustMQ.Mq9` (ns)     | `MQ9Client` | `NATS.Net`   | Scaffolded     |

Go constructor convention: `NewMQ9Client(...)` (struct, not class).

When a new protocol operation is added, **all 6 languages must be updated together**.

---

## Repository layout

```
python/          # ✅ Fully implemented
rust/            # 🚧 Scaffolded only
go/              # 🚧 Scaffolded only
javascript/      # 🚧 Scaffolded only
java/            # 🚧 Scaffolded only
csharp/          # 🚧 Scaffolded only
docs/
  mq9-protocol.md   # Authoritative protocol spec — read before implementing
demo/
  demo-python/   # Standalone Python demo project
  demo-go/       # Standalone Go demo project
  demo-javascript/ # Standalone JavaScript demo project
  demo-java/     # Standalone Java demo project (Maven)
  demo-rust/     # Standalone Rust demo project
  demo-csharp/   # Standalone C# demo project
```

---

## mq9 protocol

mq9 is RobustMQ's AI-native async communication protocol. It gives AI agents a durable mailbox —
messages persist until TTL expires; senders and receivers do not need to be online simultaneously.

Built on top of NATS (transport layer), mq9 adds store-first semantics and priority queuing.

### Subject structure

```
$mq9.AI.MAILBOX.CREATE                              PUB+reply  create mailbox
$mq9.AI.MAILBOX.MSG.{mail_id}                       PUB/SUB    send/receive default (normal) message
$mq9.AI.MAILBOX.MSG.{mail_id}.{priority}            PUB        send urgent or critical message
$mq9.AI.MAILBOX.MSG.{mail_id}.*                     SUB        subscribe urgent+critical (excludes default normal)
$mq9.AI.MAILBOX.MSG.{mail_id}.{priority}            SUB        subscribe one non-default priority
$mq9.AI.MAILBOX.LIST.{mail_id}                      PUB+reply  list messages snapshot (no payload)
$mq9.AI.MAILBOX.DELETE.{mail_id}.{msg_id}           PUB+reply  delete one message
```

Priority values: `critical` (highest) / `urgent` / `normal` (default, no suffix)

### Key semantics

- **Store-first**: messages persist before delivery; subscriber receives all non-expired
  messages immediately on connect, then real-time going forward
- **No consumer state**: server does not track read/unread position
- **Queue groups**: same queue group name → each message delivered to exactly one member
- **Wildcard on mail_id is forbidden**: `$mq9.AI.MAILBOX.MSG.*.*` is rejected (privacy)
- **CREATE is idempotent**: repeating returns success, original TTL preserved
- **Mailbox types**: private (UUID, server-assigned) or public (user-defined name, predictable)
- **No public discovery endpoint**: public mailboxes are found by name agreement, not enumeration
- **LIST returns metadata only**: `msg_id`, `priority`, `ts` — no payload in list response

### Payloads

Create private: `{"ttl": 3600}`
Create public:  `{"ttl": 86400, "public": true, "name": "task.queue", "desc": "..."}`
Create reply:   `{"mail_id": "m-uuid-001"}`
Error reply:    `{"error": "...", "code": 404}`

Message payload: arbitrary bytes (application-defined schema, server does not inspect).

### How to add / change a protocol operation

When the owner says "new operation X" or "change subject Y":

1. Update `docs/mq9-protocol.md` first (source of truth)
2. Update this CLAUDE.md subject table
3. Implement in all 6 languages — **do not skip any**
4. Update demo scripts in `demo/`
5. Update tests for each language

---

## API surface (canonical — all languages mirror this)

```python
client = MQ9Client(server="nats://localhost:4222")
await client.connect()
await client.close()                                            # drain then disconnect
# async with MQ9Client(...) as client: also supported

mailbox = await client.create(ttl=3600)                        # private mailbox → Mailbox
mailbox = await client.create(ttl=3600, public=True, name="q") # public mailbox → Mailbox
await client.send(mail_id, payload, priority="normal")         # bytes|str|dict, fire-and-forget
await client.subscribe(mail_id, async_cb, priority="*", queue_group="")  # → Subscription
messages = await client.list(mail_id)                          # → list[MessageMeta]
await client.delete(mail_id, msg_id)
```

Return types:
- `Mailbox(mail_id, public, name, desc)`
- `MessageMeta(msg_id, priority, ts)` — LIST returns metadata only, no payload

---

## Per-language implementation rules

### All languages

- NATS client is the only required runtime dependency
- Use `request/reply` for CREATE, LIST, DELETE
- Use plain `publish` for SEND (no reply needed)
- Raise a typed `MQ9Error` (with `.code: int`) on server error responses
- Tests mock the NATS connection — no live server required
- All IO is async

### Python

- `nats-py` only, no other runtime deps
- `pytest-asyncio` for tests
- `cd python && pip install -e ".[dev]" && pytest`

### Rust

- `async-nats` + `tokio` + `serde_json`
- `cargo test`

### Go

- `nats.go` only
- Constructor: `NewMQ9Client(server string) *MQ9Client`
- `go test ./...`

### JavaScript

- `nats` v2 only (works in Node.js and browser via WebSocket)
- TypeScript source, compiled to `dist/`
- `npm test`

### Java

- `jnats` + `jackson-databind`
- `CompletableFuture` for async
- `mvn test`

### C\#

- `NATS.Net` only
- `async/await` throughout
- `dotnet test`

---

## Demo module

Location: `demo/`
Each language has a standalone project that imports the published SDK v0.3.5.

All demos run the same scenario:
1. Connect to `nats://localhost:4222`
2. Create a private mailbox (TTL 60s)
3. Send 3 messages (critical / urgent / normal priority)
4. Subscribe and print received messages
5. List mailbox metadata, delete one message
6. Create a public mailbox
7. Close connection
