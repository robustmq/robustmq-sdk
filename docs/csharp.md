# C# SDK

**Package:** `RobustMQ.Mq9`  
**Requires:** .NET 8+, `NATS.Net`

## Install

```bash
dotnet add package RobustMQ.Mq9
```

## Quick start

```csharp
using RobustMQ.Mq9;

await using var client = new MQ9Client("nats://localhost:4222");
await client.ConnectAsync();

// Create mailbox
var mailbox = await client.CreateAsync(3600);

// Send
await client.SendAsync(mailbox.MailId, "hello"u8.ToArray(), Priority.Normal);

// Subscribe
await using var sub = await client.SubscribeAsync(mailbox.MailId, async msg => {
    Console.WriteLine(System.Text.Encoding.UTF8.GetString(msg.Payload));
});

// List metadata (no payload)
var metas = await client.ListAsync(mailbox.MailId);
// metas[i].MsgId, .Priority, .Ts

// Delete
await client.DeleteAsync(mailbox.MailId, metas[0].MsgId);
```

## API

```csharp
MQ9Client(string server = "nats://localhost:4222")  // IAsyncDisposable

Task ConnectAsync()
ValueTask DisposeAsync()

Task<Mailbox> CreateAsync(int ttl, bool isPublic = false, string name = "", string desc = "")

Task SendAsync(string mailId, byte[] payload, Priority priority = Priority.Normal)

Task<IAsyncDisposable> SubscribeAsync(string mailId, Func<Mq9Message, Task> callback,
                                       Priority? priority = null, string queueGroup = "")

Task<List<MessageMeta>> ListAsync(string mailId)
// MessageMeta: MsgId, Priority, Ts

Task DeleteAsync(string mailId, string msgId)
```

## Priority

```csharp
Priority.High    // "high"
Priority.Normal  // "normal"
Priority.Low     // "low"
```

## Public mailbox

```csharp
var pub = await client.CreateAsync(3600, isPublic: true, name: "task.queue", desc: "Tasks");
// pub.MailId == "task.queue"
```

## Queue group

```csharp
await client.SubscribeAsync(mailId, handler, queueGroup: "workers");
```
