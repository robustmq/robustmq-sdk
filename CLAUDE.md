# RobustMQ SDK — Project Guide

## What this repo is

Multi-language client SDK for RobustMQ, a unified messaging broker that supports MQTT, Kafka,
NATS, AMQP, and mq9 on a shared storage layer. This SDK focuses on **mq9** — the AI-native
async communication protocol built on top of NATS.

The owner does not intervene in implementation details. Claude makes all technical decisions
and drives the project forward autonomously.

---

## Version management

Source of truth: root `VERSION` file (currently `1.0.0`).

When bumping the version, update `VERSION` and all 6 build files in one commit:

- Python: `python/pyproject.toml` + `python/robustmq/__init__.py`
- Rust: `rust/Cargo.toml`
- Go: git tag only (e.g. `v1.0.0`) — no file to update
- JavaScript: `javascript/package.json`
- Java: `java/pom.xml`
- C#: `csharp/RobustMQ.Mq9/RobustMQ.Mq9.csproj`

---

## SDK implementation status

| Language   | Package/Import    | Class       | NATS lib     | Status         |
| ---------- | ----------------- | ----------- | ------------ | -------------- |
| Python     | `robustmq.mq9`    | `MQ9Client` | `nats-py`    | Implemented    |
| Rust       | `robustmq_mq9`    | `MQ9Client` | `async-nats` | Scaffolded     |
| Go         | `mq9` (pkg)       | `MQ9Client` | `nats.go`    | Scaffolded     |
| JavaScript | `@robustmq/mq9`   | `MQ9Client` | `nats` v2    | Scaffolded     |
| Java       | `io.robustmq.mq9` | `MQ9Client` | `jnats`      | Scaffolded     |
| C#         | `RobustMQ.Mq9`    | `MQ9Client` | `NATS.Net`   | Scaffolded     |

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
demo/            # End-to-end demo scripts, one per language
```

---

## mq9 protocol

mq9 gives AI agents a durable mailbox. Messages persist until TTL expires; senders and
receivers do not need to be online simultaneously.

### Subject structure

```
$mq9.AI.MAILBOX.CREATE                              PUB+reply  create mailbox
$mq9.AI.MAILBOX.MSG.{mail_id}.{priority}            PUB        send message
$mq9.AI.MAILBOX.MSG.{mail_id}.*                     SUB        subscribe (all priorities)
$mq9.AI.MAILBOX.MSG.{mail_id}.{priority}            SUB        subscribe (one priority)
$mq9.AI.MAILBOX.LIST.{mail_id}                      PUB+reply  list messages snapshot (no payload)
$mq9.AI.MAILBOX.DELETE.{mail_id}.{msg_id}           PUB+reply  delete one message
```

Priority values: `high` / `normal` / `low`

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
- Use `request/reply` for CREATE, LIST, DELETE, PUBLIC.LIST
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
One script per language, all running the same scenario:

1. Connect to `nats://localhost:4222`
2. Create a private mailbox (TTL 60s)
3. Send 3 messages (high / normal / low priority)
4. Subscribe and print received messages
5. List mailbox, delete one message
6. Create a public mailbox and discover it via PUBLIC.LIST
7. Close connection

Demo scripts are standalone — they import the SDK from the local source tree, not a published package.
