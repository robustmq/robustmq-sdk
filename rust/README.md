# robustmq-rust

Rust SDK for [RobustMQ](https://github.com/robustmq/robustmq) — mq9 AI-native async messaging.

**Status: not yet implemented.** Directory structure and dependencies are scaffolded.

## Planned dependencies

- [`async-nats`](https://crates.io/crates/async-nats) — NATS client
- [`tokio`](https://crates.io/crates/tokio) — async runtime
- [`serde_json`](https://crates.io/crates/serde_json) — JSON serialization

## Planned API

```rust
use robustmq::mq9::Client;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::connect("nats://localhost:4222").await?;

    let mailbox = client.create(3600).await?;
    client.send(&mailbox.mail_id, b"hello", "normal").await?;

    client.subscribe(&mailbox.mail_id, |msg| async move {
        println!("{:?}", msg.payload);
    }).await?;

    Ok(())
}
```

See [docs/mq9-protocol.md](../docs/mq9-protocol.md) for the full protocol reference.
