# JavaScript / TypeScript SDK

**Package:** `@robustmq/sdk`  
**Requires:** Node.js 18+, `nats` v2

## Install

```bash
npm install @robustmq/sdk
```

## Quick start

```typescript
import { MQ9Client } from "@robustmq/sdk/mq9";

const client = new MQ9Client({ server: "nats://demo.robustmq.com:4222" });
await client.connect();

// Create mailbox
const mailbox = await client.create({ ttl: 3600 });

// Send
await client.send(mailbox.mailId, "hello", "normal");

// Subscribe
const sub = await client.subscribe(mailbox.mailId, async (msg) => {
  console.log(Buffer.from(msg.payload).toString());
});

// List metadata (no payload)
const metas = await client.list(mailbox.mailId);
// metas[i].msgId, .priority, .ts

// Delete
await client.delete(mailbox.mailId, metas[0].msgId);

sub.unsubscribe();
await client.close();
```

## API

```typescript
new MQ9Client({ server?: string, requestTimeout?: number })

client.connect(): Promise<void>
client.close(): Promise<void>

client.create(opts: { ttl: number, public?: boolean, name?: string, desc?: string }): Promise<Mailbox>

client.send(mailId, payload: Uint8Array | string | object, priority?: Priority): Promise<void>

client.subscribe(mailId, cb: (msg: Mq9Message) => Promise<void>,
                 opts?: { priority?: Priority | "*", queueGroup?: string }): Promise<{ unsubscribe(): void }>

client.list(mailId): Promise<MessageMeta[]>
// MessageMeta: { msgId, priority, ts }

client.delete(mailId, msgId): Promise<void>
```

## Priority

```typescript
"critical" | "urgent" | "normal"  // "normal" is default (no suffix in subject)
```

## Public mailbox

```typescript
const mailbox = await client.create({ ttl: 3600, public: true, name: "task.queue", desc: "Tasks" });
// mailbox.mailId === "task.queue"
```

## Queue group

```typescript
await client.subscribe(mailId, handler, { queueGroup: "workers" });
```
