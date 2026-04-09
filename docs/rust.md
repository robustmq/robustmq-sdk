# Rust SDK

**Crate:** `robustmq`  
**Requires:** Rust 1.75+, `async-nats`, `tokio`

## Install

```toml
[dependencies]
robustmq = "0.3"
tokio = { version = "1", features = ["full"] }
```

## Quick start

```rust
use robustmq::mq9::{MQ9Client, Priority};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = MQ9Client::connect("nats://demo.robustmq.com:4222").await?;

    // Create mailbox
    let mailbox = client.create(3600, false, "", "").await?;

    // Send
    client.send(&mailbox.mail_id, b"hello", Priority::Normal).await?;

    // Subscribe
    let _sub = client.subscribe(
        &mailbox.mail_id,
        |msg| async move { println!("{}", String::from_utf8_lossy(&msg.payload)); },
        None,   // None = all priorities
        "",     // queue group
    ).await?;

    // List metadata (no payload)
    let metas = client.list(&mailbox.mail_id).await?;
    // metas[i].msg_id, .priority, .ts

    // Delete
    client.delete(&mailbox.mail_id, &metas[0].msg_id).await?;

    client.close().await?;
    Ok(())
}
```

## API

```rust
MQ9Client::connect(server: &str) -> Result<Self, MQ9Error>
client.close(self) -> Result<(), MQ9Error>

client.create(ttl: u64, public: bool, name: &str, desc: &str) -> Result<Mailbox, MQ9Error>

client.send(mail_id: &str, payload: &[u8], priority: Priority) -> Result<(), MQ9Error>

client.subscribe(mail_id, callback, priority: Option<Priority>, queue_group: &str)
    -> Result<Subscription, MQ9Error>
// Subscription::unsubscribe(self) to cancel

client.list(mail_id: &str) -> Result<Vec<MessageMeta>, MQ9Error>
// MessageMeta: msg_id, priority, ts

client.delete(mail_id: &str, msg_id: &str) -> Result<(), MQ9Error>
```

## Priority

```rust
Priority::High    // "high"
Priority::Normal  // "normal"
Priority::Low     // "low"
```

## Public mailbox

```rust
let mailbox = client.create(3600, true, "task.queue", "Tasks").await?;
// mailbox.mail_id == "task.queue"
```

## Queue group

```rust
client.subscribe(mail_id, handler, None, "workers").await?;
```
