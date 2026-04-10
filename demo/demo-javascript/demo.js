/**
 * mq9 JavaScript demo — connects to nats://demo.robustmq.com:4222 and runs the full scenario.
 *
 * Run:
 *   cd demo/demo-javascript
 *   npm install
 *   npm start
 */

const { MQ9Client } = require("@robustmq/sdk/mq9");

async function main() {
  // demo.robustmq.com is a public RobustMQ service for testing. Replace with your own server address if needed.
  const client = new MQ9Client({ server: "nats://demo.robustmq.com:4222" });
  await client.connect();
  console.log("[js] connected");

  // 1. Create a private mailbox (TTL 60s)
  const mailbox = await client.create({ ttl: 60 });
  console.log(`[js] private mailbox: ${mailbox.mailId}`);

  // 2. Send 3 messages with different priorities
  await client.send(mailbox.mailId, "abort signal", "critical");
  await client.send(mailbox.mailId, "urgent task", "urgent");
  await client.send(mailbox.mailId, "normal task", "normal");
  console.log("[js] sent 3 messages (critical / urgent / normal)");

  // 3. Subscribe and print received messages
  const sub = await client.subscribe(mailbox.mailId, async (msg) => {
    console.log(`[js] received [${msg.priority}] ${Buffer.from(msg.payload).toString()}`);
  });
  await new Promise((r) => setTimeout(r, 500));
  sub.unsubscribe();

  // 4. List mailbox metadata
  const metas = await client.list(mailbox.mailId);
  console.log(`[js] list: ${metas.length} message(s) in mailbox`);
  for (const m of metas) {
    console.log(`  msgId=${m.msgId}  priority=${m.priority}  ts=${m.ts}`);
  }

  // 5. Delete first message
  if (metas.length > 0) {
    await client.delete(mailbox.mailId, metas[0].msgId);
    console.log(`[js] deleted ${metas[0].msgId}`);
  }

  // 6. Create a public mailbox
  const pub = await client.create({
    ttl: 60,
    public: true,
    name: "demo.queue",
    desc: "Demo queue",
  });
  console.log(`[js] public mailbox: ${pub.mailId}`);

  await client.close();
  console.log("[js] done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
