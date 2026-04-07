# robustmq-csharp

C# / .NET SDK for [RobustMQ](https://github.com/robustmq/robustmq) — mq9 AI-native async messaging.

**Status: not yet implemented.** Solution file is scaffolded.

## Planned dependency

- [`NATS.Net`](https://www.nuget.org/packages/NATS.Net) — official NATS .NET client

## Planned API

```csharp
using RobustMQ.Mq9;

await using var client = new Client("nats://localhost:4222");
await client.ConnectAsync();

var mailbox = await client.CreateAsync(ttl: 3600);
await client.SendAsync(mailbox.MailId, "hello"u8.ToArray());

await client.SubscribeAsync(mailbox.MailId, async msg => {
    Console.WriteLine(Encoding.UTF8.GetString(msg.Payload));
});
```

See [docs/mq9-protocol.md](../docs/mq9-protocol.md) for the full protocol reference.
