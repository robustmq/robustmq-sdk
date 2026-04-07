# robustmq-js

JavaScript/TypeScript SDK for [RobustMQ](https://github.com/robustmq/robustmq) — mq9 AI-native async messaging.

**Status: not yet implemented.** Directory structure and package config are scaffolded.

## Planned dependency

- [`nats`](https://www.npmjs.com/package/nats) — NATS.js v2 (WebSocket + TCP)

## Planned API

```typescript
import { Client } from "robustmq/mq9";

const client = new Client({ server: "nats://localhost:4222" });
await client.connect();

const mailbox = await client.create({ ttl: 3600 });
await client.send(mailbox.mailId, { task: "summarize" });

await client.subscribe(mailbox.mailId, async (msg) => {
  console.log(msg.payload);
});

await client.close();
```

See [docs/mq9-protocol.md](../docs/mq9-protocol.md) for the full protocol reference.
