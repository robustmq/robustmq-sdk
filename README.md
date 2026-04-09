# RobustMQ SDK

Multi-language client SDK for [RobustMQ](https://github.com/robustmq/robustmq) — a unified messaging engine built for the AI era.

RobustMQ is a single-binary broker that natively supports MQTT, Kafka, NATS, AMQP, and **mq9** on a shared storage layer.


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

| Language | Package | Version | Install |
|----------|---------|---------|---------|
| Python | `robustmq-mq9` | 1.0.0 | `pip install robustmq-mq9` |
| Go | `github.com/robustmq/robustmq-sdk/go` | v1.0.0 | `go get github.com/robustmq/robustmq-sdk/go` |
| JavaScript | `@robustmq/mq9` | 1.0.0 | `npm install @robustmq/mq9` |
| Java | `com.robustmq:robustmq-sdk` | 1.0.0 | Maven / Gradle (see below) |
| Rust | `robustmq` | 1.0.0 | `cargo add robustmq` |
| C# | `RobustMQ.Mq9` | 1.0.0 | `dotnet add package RobustMQ.Mq9` |

---

## Quick start

**Python**
```bash
pip install robustmq-mq9
```
```python
from robustmq.mq9 import Client, Priority

async with Client("nats://localhost:4222") as client:
    mailbox = await client.create(ttl=3600)
    await client.send(mailbox.mail_id, b"hello", priority=Priority.NORMAL)

    async def handler(msg):
        print(msg.payload)

    await client.subscribe(mailbox.mail_id, handler)
```

**Go**
```bash
go get github.com/robustmq/robustmq-sdk/go
```
```go
import "github.com/robustmq/robustmq-sdk/go/mq9"

c := mq9.NewMQ9Client("nats://localhost:4222")
c.Connect()
mailbox, _ := c.Create(3600)
c.Send(mailbox.MailID, []byte("hello"), mq9.Normal)
```

**JavaScript / TypeScript**
```bash
npm install @robustmq/mq9
```
```typescript
import { MQ9Client } from "@robustmq/mq9";

const client = new MQ9Client({ server: "nats://localhost:4222" });
await client.connect();
const mailbox = await client.create({ ttl: 3600 });
await client.send(mailbox.mailId, "hello", "normal");
```

**Java (Maven)**
```xml
<dependency>
  <groupId>com.robustmq</groupId>
  <artifactId>robustmq-sdk</artifactId>
  <version>1.0.0</version>
</dependency>
```
```java
import com.robustmq.mq9.*;

MQ9Client client = new MQ9Client("nats://localhost:4222");
client.connect();
Mailbox mailbox = client.create(3600).get();
client.send(mailbox.getMailId(), "hello".getBytes(), Priority.NORMAL).get();
```

**Java (Gradle)**
```groovy
implementation 'com.robustmq:robustmq-sdk:1.0.0'
```

**Rust**
```toml
[dependencies]
robustmq = "1.0"
tokio = { version = "1", features = ["full"] }
```
```rust
use robustmq::mq9::{MQ9Client, Priority};

let client = MQ9Client::connect("nats://localhost:4222").await?;
let mailbox = client.create(3600, false, "", "").await?;
client.send(&mailbox.mail_id, b"hello", Priority::Normal).await?;
```

**C#**
```bash
dotnet add package RobustMQ.Mq9
```
```csharp
using RobustMQ.Mq9;

await using var client = new MQ9Client("nats://localhost:4222");
await client.ConnectAsync();
var mailbox = await client.CreateAsync(3600);
await client.SendAsync(mailbox.MailId, "hello"u8.ToArray(), Priority.Normal);
```

---

## SDK documentation

| Language | Docs | Demo |
|----------|------|------|
| Python | [docs/python.md](docs/python.md) | [demo/demo-python/](demo/demo-python/) |
| Go | [docs/go.md](docs/go.md) | [demo/demo-go/](demo/demo-go/) |
| JavaScript | [docs/javascript.md](docs/javascript.md) | [demo/demo-javascript/](demo/demo-javascript/) |
| Java | [docs/java.md](docs/java.md) | [demo/demo-java/](demo/demo-java/) |
| C# | [docs/csharp.md](docs/csharp.md) | [demo/demo-csharp/](demo/demo-csharp/) |
| Rust | [docs/rust.md](docs/rust.md) | [demo/demo-rust/](demo/demo-rust/) |

---

## Running the demo

Each demo is a standalone project that connects to `nats://localhost:4222` and runs the same scenario:
1. Create a private mailbox (TTL 60s)
2. Send 3 messages (high / normal / low priority)
3. Subscribe and print received messages
4. List mailbox metadata, delete one message
5. Create a public mailbox

```bash
# Python
cd demo/demo-python && pip install -r requirements.txt && python demo.py

# Go
cd demo/demo-go && go run .

# JavaScript
cd demo/demo-javascript && npm install && npm start

# Java
cd demo/demo-java && mvn compile exec:java

# Rust
cd demo/demo-rust && cargo run

# C#
cd demo/demo-csharp && dotnet run
```

---

## Repository layout

```
python/            # Python SDK
go/                # Go SDK
javascript/        # JavaScript/TypeScript SDK
java/              # Java SDK
csharp/            # C# SDK
rust/              # Rust SDK
docs/              # SDK docs + protocol spec
demo/
  demo-python/     # Python standalone demo project
  demo-go/         # Go standalone demo project
  demo-javascript/ # JavaScript standalone demo project
  demo-java/       # Java standalone demo project (Maven)
  demo-rust/       # Rust standalone demo project
  demo-csharp/     # C# standalone demo project
VERSION            # Canonical version (currently 1.0.0)
```

---

## Related

- [RobustMQ](https://github.com/robustmq/robustmq) — the broker
- [mq9 Protocol Specification](docs/mq9-protocol.md) — full protocol reference
