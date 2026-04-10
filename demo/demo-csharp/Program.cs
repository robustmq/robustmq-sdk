/**
 * mq9 C# demo — connects to nats://demo.robustmq.com:4222 and runs the full scenario.
 *
 * Run:
 *   cd demo/demo-csharp
 *   dotnet run
 */

using System.Text;
using RobustMQ.Mq9;

// demo.robustmq.com is a public RobustMQ service for testing. Replace with your own server address if needed.
await using var client = new MQ9Client("nats://demo.robustmq.com:4222");
await client.ConnectAsync();
Console.WriteLine("[csharp] connected");

// 1. Create a private mailbox (TTL 60s)
var mailbox = await client.CreateAsync(60);
Console.WriteLine($"[csharp] private mailbox: {mailbox.MailId}");

// 2. Send 3 messages with different priorities
await client.SendAsync(mailbox.MailId, "abort signal"u8.ToArray(), Priority.Critical);
await client.SendAsync(mailbox.MailId, "urgent task"u8.ToArray(), Priority.Urgent);
await client.SendAsync(mailbox.MailId, "normal task"u8.ToArray(), Priority.Normal);
Console.WriteLine("[csharp] sent 3 messages (critical / urgent / normal)");

// 3. Subscribe and print received messages
await using var sub = await client.SubscribeAsync(mailbox.MailId, async msg =>
{
    Console.WriteLine($"[csharp] received [{msg.Priority}] {Encoding.UTF8.GetString(msg.Payload)}");
    await Task.CompletedTask;
});
await Task.Delay(500);

// 4. List mailbox metadata
var metas = await client.ListAsync(mailbox.MailId);
Console.WriteLine($"[csharp] list: {metas.Count} message(s) in mailbox");
foreach (var m in metas)
    Console.WriteLine($"  MsgId={m.MsgId}  Priority={m.Priority}  Ts={m.Ts}");

// 5. Delete first message
if (metas.Count > 0)
{
    await client.DeleteAsync(mailbox.MailId, metas[0].MsgId);
    Console.WriteLine($"[csharp] deleted {metas[0].MsgId}");
}

// 6. Create a public mailbox
var pub = await client.CreateAsync(60, isPublic: true, name: "demo.queue", desc: "Demo queue");
Console.WriteLine($"[csharp] public mailbox: {pub.MailId}");

Console.WriteLine("[csharp] done");
