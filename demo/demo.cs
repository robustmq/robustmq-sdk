/**
 * mq9 C# demo — connects to nats://localhost:4222 and runs the full scenario.
 *
 * Run:
 *   cd csharp && dotnet run --project Demo
 *
 * Or reference RobustMQ.Mq9 from a standalone project and run this file.
 */

using System.Text;
using RobustMQ.Mq9;

await using var client = new MQ9Client("nats://localhost:4222");
await client.ConnectAsync();
Console.WriteLine("[csharp] connected");

// 1. Create a private mailbox (TTL 60s)
var mailbox = await client.CreateAsync(60);
Console.WriteLine($"[csharp] private mailbox: {mailbox.MailId}");

// 2. Send 3 messages with different priorities
await client.SendAsync(mailbox.MailId, "urgent task"u8.ToArray(), Priority.High);
await client.SendAsync(mailbox.MailId, "normal task"u8.ToArray(), Priority.Normal);
await client.SendAsync(mailbox.MailId, "background task"u8.ToArray(), Priority.Low);
Console.WriteLine("[csharp] sent 3 messages (high / normal / low)");

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
