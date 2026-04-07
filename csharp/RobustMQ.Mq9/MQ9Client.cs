using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using NATS.Client.Core;

namespace RobustMQ.Mq9;

/// <summary>
/// Async mq9 client for RobustMQ.
/// </summary>
/// <example>
/// <code>
/// await using var client = new MQ9Client("nats://localhost:4222");
/// await client.ConnectAsync();
///
/// var mailbox = await client.CreateAsync(ttl: 3600);
/// await client.SendAsync(mailbox.MailId, "hello"u8.ToArray());
///
/// await client.SubscribeAsync(mailbox.MailId, async msg =>
/// {
///     Console.WriteLine(Encoding.UTF8.GetString(msg.Payload));
/// });
/// </code>
/// </example>
public class MQ9Client : IAsyncDisposable
{
    private const string Prefix = "$mq9.AI";
    private const string MailboxCreate = $"{Prefix}.MAILBOX.CREATE";
    private static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(5);

    private readonly string _server;
    // Internal for testing — allows injecting a mock transport
    internal INatsConnection? _nc;

    public MQ9Client(string server = "nats://localhost:4222")
    {
        _server = server;
    }

    // ── Connection ────────────────────────────────────────────────────────────

    public async Task ConnectAsync()
    {
        var opts = new NatsOpts { Url = _server };
        var nc = new NatsConnection(opts);
        await nc.ConnectAsync();
        _nc = nc;
    }

    public async ValueTask DisposeAsync()
    {
        if (_nc is NatsConnection nc)
            await nc.DisposeAsync();
    }

    // ── Create ────────────────────────────────────────────────────────────────

    public async Task<Mailbox> CreateAsync(int ttl, bool isPublic = false,
        string name = "", string desc = "")
    {
        if (isPublic && string.IsNullOrEmpty(name))
            throw new MQ9Error("name is required when public=true");

        var req = new JsonObject { ["ttl"] = ttl };
        if (isPublic)
        {
            req["public"] = true;
            req["name"] = name;
            if (!string.IsNullOrEmpty(desc)) req["desc"] = desc;
        }

        var resp = await RequestAsync(MailboxCreate, req);
        var mailId = resp["mail_id"]?.GetValue<string>()
                     ?? throw new MQ9Error("invalid response: missing mail_id");
        return new Mailbox(mailId, isPublic, name, desc);
    }

    // ── Send ──────────────────────────────────────────────────────────────────

    public async Task SendAsync(string mailId, byte[] payload,
        Priority priority = Priority.Normal)
    {
        EnsureConnected();
        var subject = $"{Prefix}.MAILBOX.MSG.{mailId}.{priority.ToSubjectString()}";
        await _nc!.PublishAsync(subject, payload);
    }

    // ── Subscribe ─────────────────────────────────────────────────────────────

    public async Task<IAsyncDisposable> SubscribeAsync(
        string mailId,
        Func<Mq9Message, Task> callback,
        Priority? priority = null,
        string queueGroup = "")
    {
        EnsureConnected();
        var subject = priority.HasValue
            ? $"{Prefix}.MAILBOX.MSG.{mailId}.{priority.Value.ToSubjectString()}"
            : $"{Prefix}.MAILBOX.MSG.{mailId}.*";

        var sub = string.IsNullOrEmpty(queueGroup)
            ? await _nc!.SubscribeCoreAsync<byte[]>(subject)
            : await _nc!.SubscribeCoreAsync<byte[]>(subject, queueGroup: queueGroup);

        // Start background consumer
        var cts = new CancellationTokenSource();
        var task = Task.Run(async () =>
        {
            await foreach (var msg in sub.Msgs.ReadAllAsync(cts.Token))
            {
                try
                {
                    var m = ParseIncoming(mailId, msg.Subject, msg.Data ?? Array.Empty<byte>());
                    await callback(m);
                }
                catch
                {
                    // swallow callback exceptions to keep subscription alive
                }
            }
        }, cts.Token);

        return new SubscriptionHandle(sub, cts);
    }

    // ── List ──────────────────────────────────────────────────────────────────

    public async Task<List<MessageMeta>> ListAsync(string mailId)
    {
        var subject = $"{Prefix}.MAILBOX.LIST.{mailId}";
        var resp = await RequestAsync(subject, new JsonObject());
        var metas = new List<MessageMeta>();
        var arr = resp["messages"]?.AsArray();
        if (arr != null)
            foreach (var node in arr)
                if (node != null)
                    metas.Add(new MessageMeta(
                        node["msg_id"]?.GetValue<string>() ?? "",
                        PriorityExtensions.FromString(node["priority"]?.GetValue<string>() ?? "normal"),
                        node["ts"]?.GetValue<long>() ?? 0));
        return metas;
    }

    // ── Delete ────────────────────────────────────────────────────────────────

    public async Task DeleteAsync(string mailId, string msgId)
    {
        var subject = $"{Prefix}.MAILBOX.DELETE.{mailId}.{msgId}";
        await RequestAsync(subject, new JsonObject());
    }

    // ── Internal helpers ─────────────────────────────────────────────────────

    private void EnsureConnected()
    {
        if (_nc == null)
            throw new InvalidOperationException("Not connected. Call ConnectAsync() first.");
    }

    private async Task<JsonNode> RequestAsync(string subject, JsonNode payload)
    {
        EnsureConnected();
        var data = Encoding.UTF8.GetBytes(payload.ToJsonString());

        using var cts = new CancellationTokenSource(RequestTimeout);
        var reply = await _nc!.RequestAsync<byte[], byte[]>(subject, data, cancellationToken: cts.Token);

        if (reply.Data == null)
            throw new MQ9Error($"empty response from {subject}");

        var node = JsonNode.Parse(reply.Data)
                   ?? throw new MQ9Error("invalid JSON response");

        if (node["error"] != null)
        {
            var code = node["code"]?.GetValue<int>() ?? 0;
            throw new MQ9Error(node["error"]!.GetValue<string>(), code);
        }
        return node;
    }

    private static Mq9Message ParseIncoming(string mailId, string subject, byte[] data)
    {
        // Extract priority from last subject token
        var parts = subject.Split('.');
        var priorityStr = parts.Length > 0 ? parts[^1] : "normal";
        var priority = PriorityExtensions.FromString(priorityStr);

        try
        {
            var node = JsonNode.Parse(data);
            if (node?["msg_id"] != null)
                return ParseMessageNode(mailId, node);
        }
        catch { /* fall through */ }

        return new Mq9Message("", mailId, priority, data);
    }

    private static Mq9Message ParseMessageNode(string mailId, JsonNode node)
    {
        var msgId = node["msg_id"]?.GetValue<string>() ?? "";
        var priority = PriorityExtensions.FromString(node["priority"]?.GetValue<string>() ?? "normal");
        var rawPayload = node["payload"]?.GetValue<string>() ?? "";
        var payload = string.IsNullOrEmpty(rawPayload)
            ? Array.Empty<byte>()
            : Convert.FromBase64String(rawPayload);
        return new Mq9Message(msgId, mailId, priority, payload);
    }
}

// ── Subscription handle ───────────────────────────────────────────────────────

file sealed class SubscriptionHandle : IAsyncDisposable
{
    private readonly IDisposable _sub;
    private readonly CancellationTokenSource _cts;

    public SubscriptionHandle(IDisposable sub, CancellationTokenSource cts)
    {
        _sub = sub;
        _cts = cts;
    }

    public ValueTask DisposeAsync()
    {
        _cts.Cancel();
        _sub.Dispose();
        _cts.Dispose();
        return ValueTask.CompletedTask;
    }
}
