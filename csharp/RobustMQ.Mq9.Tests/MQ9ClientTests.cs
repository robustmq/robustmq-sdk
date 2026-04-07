using System.Text;
using System.Text.Json.Nodes;
using NATS.Client.Core;
using NSubstitute;
using RobustMQ.Mq9;
using Xunit;

namespace RobustMQ.Mq9.Tests;

public class MQ9ClientTests
{
    // ── helpers ───────────────────────────────────────────────────────────────

    private static MQ9Client ClientWithMock(INatsConnection mock)
    {
        var client = new MQ9Client();
        client._nc = mock;
        return client;
    }

    private static NatsMsg<byte[]> Reply(string json) =>
        new NatsMsg<byte[]> { Data = Encoding.UTF8.GetBytes(json) };

    // ── not connected ─────────────────────────────────────────────────────────

    [Fact]
    public async Task NotConnected_Throws()
    {
        var client = new MQ9Client();
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => client.ListAsync("m-001"));
    }

    // ── create ────────────────────────────────────────────────────────────────

    [Fact]
    public async Task Create_PrivateMailbox()
    {
        var mock = Substitute.For<INatsConnection>();
        mock.RequestAsync<byte[], byte[]>(
                Arg.Is("$mq9.AI.MAILBOX.CREATE"), Arg.Any<byte[]>(),
                cancellationToken: Arg.Any<CancellationToken>())
            .Returns(Reply("{\"mail_id\":\"m-001\"}"));

        var client = ClientWithMock(mock);
        var mailbox = await client.CreateAsync(3600);

        Assert.Equal("m-001", mailbox.MailId);
        Assert.False(mailbox.Public);
    }

    [Fact]
    public async Task Create_PublicMailbox()
    {
        var mock = Substitute.For<INatsConnection>();
        mock.RequestAsync<byte[], byte[]>(
                Arg.Is("$mq9.AI.MAILBOX.CREATE"), Arg.Any<byte[]>(),
                cancellationToken: Arg.Any<CancellationToken>())
            .Returns(Reply("{\"mail_id\":\"task.queue\"}"));

        var client = ClientWithMock(mock);
        var mailbox = await client.CreateAsync(86400, isPublic: true, name: "task.queue", desc: "Tasks");

        Assert.Equal("task.queue", mailbox.MailId);
        Assert.True(mailbox.Public);
    }

    [Fact]
    public async Task Create_PublicWithoutName_Throws()
    {
        var mock = Substitute.For<INatsConnection>();
        var client = ClientWithMock(mock);

        await Assert.ThrowsAsync<MQ9Error>(
            () => client.CreateAsync(3600, isPublic: true));
    }

    [Fact]
    public async Task Create_ServerError_ThrowsMQ9Error()
    {
        var mock = Substitute.For<INatsConnection>();
        mock.RequestAsync<byte[], byte[]>(Arg.Any<string>(), Arg.Any<byte[]>(),
                cancellationToken: Arg.Any<CancellationToken>())
            .Returns(Reply("{\"error\":\"quota exceeded\",\"code\":429}"));

        var client = ClientWithMock(mock);
        var ex = await Assert.ThrowsAsync<MQ9Error>(() => client.CreateAsync(3600));
        Assert.Equal(429, ex.Code);
        Assert.Contains("quota exceeded", ex.Message);
    }

    // ── send ──────────────────────────────────────────────────────────────────

    [Fact]
    public async Task Send_PublishesCorrectSubject()
    {
        var mock = Substitute.For<INatsConnection>();
        var client = ClientWithMock(mock);

        await client.SendAsync("m-001", "hello"u8.ToArray(), Priority.Normal);

        await mock.Received(1).PublishAsync(
            "$mq9.AI.MAILBOX.MSG.m-001.normal",
            Arg.Any<byte[]>());
    }

    [Fact]
    public async Task Send_HighPriority_CorrectSubject()
    {
        var mock = Substitute.For<INatsConnection>();
        var client = ClientWithMock(mock);

        await client.SendAsync("m-001", "urgent"u8.ToArray(), Priority.High);

        await mock.Received(1).PublishAsync(
            "$mq9.AI.MAILBOX.MSG.m-001.high",
            Arg.Any<byte[]>());
    }

    // ── list ──────────────────────────────────────────────────────────────────

    [Fact]
    public async Task List_ReturnsMessageMeta()
    {
        var json = "{\"mail_id\":\"m-001\",\"messages\":[{\"msg_id\":\"x1\","
                   + "\"priority\":\"high\",\"ts\":100}]}";

        var mock = Substitute.For<INatsConnection>();
        mock.RequestAsync<byte[], byte[]>(
                Arg.Is("$mq9.AI.MAILBOX.LIST.m-001"), Arg.Any<byte[]>(),
                cancellationToken: Arg.Any<CancellationToken>())
            .Returns(Reply(json));

        var client = ClientWithMock(mock);
        var metas = await client.ListAsync("m-001");

        Assert.Single(metas);
        Assert.Equal("x1", metas[0].MsgId);
        Assert.Equal(Priority.High, metas[0].Priority);
        Assert.Equal(100L, metas[0].Ts);
    }

    [Fact]
    public async Task List_EmptyMailbox()
    {
        var mock = Substitute.For<INatsConnection>();
        mock.RequestAsync<byte[], byte[]>(Arg.Any<string>(), Arg.Any<byte[]>(),
                cancellationToken: Arg.Any<CancellationToken>())
            .Returns(Reply("{\"mail_id\":\"m-001\",\"messages\":[]}"));

        var client = ClientWithMock(mock);
        var metas = await client.ListAsync("m-001");
        Assert.Empty(metas);
    }

    // ── delete ────────────────────────────────────────────────────────────────

    [Fact]
    public async Task Delete_CallsCorrectSubject()
    {
        var mock = Substitute.For<INatsConnection>();
        mock.RequestAsync<byte[], byte[]>(Arg.Any<string>(), Arg.Any<byte[]>(),
                cancellationToken: Arg.Any<CancellationToken>())
            .Returns(Reply("{\"ok\":true}"));

        var client = ClientWithMock(mock);
        await client.DeleteAsync("m-001", "msg-42");

        await mock.Received(1).RequestAsync<byte[], byte[]>(
            "$mq9.AI.MAILBOX.DELETE.m-001.msg-42",
            Arg.Any<byte[]>(),
            cancellationToken: Arg.Any<CancellationToken>());
    }
}
