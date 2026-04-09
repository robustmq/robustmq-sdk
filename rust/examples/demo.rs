// mq9 Rust demo — connects to nats://localhost:4222 and runs the full scenario.
//
// Run:
//   cd rust && cargo run --example demo
//
//

use robustmq::mq9::{MQ9Client, Priority};
use tokio::time::{sleep, Duration};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = MQ9Client::connect("nats://localhost:4222").await?;
    println!("[rust] connected");

    // 1. Create a private mailbox (TTL 60s)
    let mailbox = client.create(60, false, "", "").await?;
    println!("[rust] private mailbox: {}", mailbox.mail_id);

    // 2. Send 3 messages with different priorities
    client.send(&mailbox.mail_id, b"urgent task", Priority::High).await?;
    client.send(&mailbox.mail_id, b"normal task", Priority::Normal).await?;
    client.send(&mailbox.mail_id, b"background task", Priority::Low).await?;
    println!("[rust] sent 3 messages (high / normal / low)");

    // 3. Subscribe and print received messages
    let _sub = client
        .subscribe(
            &mailbox.mail_id,
            |msg| async move {
                println!(
                    "[rust] received [{}] {}",
                    msg.priority,
                    String::from_utf8_lossy(&msg.payload)
                );
            },
            None,
            "",
        )
        .await?;
    sleep(Duration::from_millis(500)).await;

    // 4. List mailbox metadata
    let metas = client.list(&mailbox.mail_id).await?;
    println!("[rust] list: {} message(s) in mailbox", metas.len());
    for m in &metas {
        println!("  msg_id={}  priority={}  ts={}", m.msg_id, m.priority, m.ts);
    }

    // 5. Delete first message
    if let Some(first) = metas.first() {
        client.delete(&mailbox.mail_id, &first.msg_id).await?;
        println!("[rust] deleted {}", first.msg_id);
    }

    // 6. Create a public mailbox
    let pub_box = client.create(60, true, "demo.queue", "Demo queue").await?;
    println!("[rust] public mailbox: {}", pub_box.mail_id);

    client.close().await?;
    println!("[rust] done");
    Ok(())
}
