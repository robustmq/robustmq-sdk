import { MQ9Client, MQ9Error, NatsTransport, Mq9Message, MessageMeta, Priority } from "./client.js";

// ---------------------------------------------------------------------------
// Mock transport
// ---------------------------------------------------------------------------

function mockTransport(overrides: Partial<NatsTransport> = {}): NatsTransport {
  return {
    publish: jest.fn(),
    request: jest.fn(),
    subscribe: jest.fn(),
    drain: jest.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as NatsTransport;
}

function jsonReply(data: object): { data: Uint8Array } {
  return { data: Buffer.from(JSON.stringify(data)) };
}

function clientWith(transport: NatsTransport): MQ9Client {
  const c = new MQ9Client();
  c._transport = transport;
  return c;
}

// ---------------------------------------------------------------------------
// create
// ---------------------------------------------------------------------------

describe("create", () => {
  test("private mailbox", async () => {
    const t = mockTransport({
      request: jest.fn().mockResolvedValue(jsonReply({ mail_id: "m-001" })),
    });
    const client = clientWith(t);
    const mb = await client.create({ ttl: 3600 });

    expect(mb.mailId).toBe("m-001");
    expect(mb.public).toBe(false);
    expect(t.request).toHaveBeenCalledWith(
      "$mq9.AI.MAILBOX.CREATE",
      expect.any(Uint8Array),
      expect.anything()
    );
  });

  test("public mailbox", async () => {
    const t = mockTransport({
      request: jest.fn().mockResolvedValue(jsonReply({ mail_id: "task.queue" })),
    });
    const client = clientWith(t);
    const mb = await client.create({
      ttl: 86400,
      public: true,
      name: "task.queue",
      desc: "Tasks",
    });

    expect(mb.mailId).toBe("task.queue");
    expect(mb.public).toBe(true);

    const sentPayload = JSON.parse(
      Buffer.from((t.request as jest.Mock).mock.calls[0][1]).toString()
    );
    expect(sentPayload.public).toBe(true);
    expect(sentPayload.name).toBe("task.queue");
  });

  test("public without name throws MQ9Error", async () => {
    const client = clientWith(mockTransport());
    await expect(client.create({ ttl: 3600, public: true })).rejects.toThrow(
      MQ9Error
    );
  });

  test("server error throws MQ9Error with code", async () => {
    const t = mockTransport({
      request: jest.fn().mockResolvedValue(
        jsonReply({ error: "quota exceeded", code: 429 })
      ),
    });
    const client = clientWith(t);
    const err = await client.create({ ttl: 3600 }).catch((e) => e);
    expect(err).toBeInstanceOf(MQ9Error);
    expect(err.code).toBe(429);
  });
});

// ---------------------------------------------------------------------------
// send
// ---------------------------------------------------------------------------

describe("send", () => {
  test("publishes to correct subject with normal priority", async () => {
    const t = mockTransport();
    const client = clientWith(t);
    await client.send("m-001", Buffer.from("hello"), "normal");

    expect(t.publish).toHaveBeenCalledWith(
      "$mq9.AI.MAILBOX.MSG.m-001.normal",
      expect.any(Uint8Array)
    );
  });

  test("publishes to high priority subject", async () => {
    const t = mockTransport();
    const client = clientWith(t);
    await client.send("m-001", Buffer.from("urgent"), "high");

    expect(t.publish).toHaveBeenCalledWith(
      "$mq9.AI.MAILBOX.MSG.m-001.high",
      expect.any(Uint8Array)
    );
  });

  test("encodes string payload", async () => {
    const t = mockTransport();
    const client = clientWith(t);
    await client.send("m-001", "hello world");

    const data = (t.publish as jest.Mock).mock.calls[0][1] as Uint8Array;
    expect(Buffer.from(data).toString()).toBe("hello world");
  });

  test("encodes object payload as JSON", async () => {
    const t = mockTransport();
    const client = clientWith(t);
    await client.send("m-001", { task: "summarize" });

    const data = (t.publish as jest.Mock).mock.calls[0][1] as Uint8Array;
    expect(JSON.parse(Buffer.from(data).toString())).toEqual({ task: "summarize" });
  });
});

// ---------------------------------------------------------------------------
// list
// ---------------------------------------------------------------------------

describe("list", () => {
  test("returns message metadata", async () => {
    const t = mockTransport({
      request: jest.fn().mockResolvedValue(
        jsonReply({
          mail_id: "m-001",
          messages: [
            { msg_id: "x1", priority: "high", ts: 100 },
          ],
        })
      ),
    });
    const client = clientWith(t);
    const msgs: MessageMeta[] = await client.list("m-001");

    expect(msgs).toHaveLength(1);
    expect(msgs[0].msgId).toBe("x1");
    expect(msgs[0].priority).toBe("high" as Priority);
    expect(msgs[0].ts).toBe(100);

    expect(t.request).toHaveBeenCalledWith(
      "$mq9.AI.MAILBOX.LIST.m-001",
      expect.any(Uint8Array),
      expect.anything()
    );
  });

  test("returns empty array for empty mailbox", async () => {
    const t = mockTransport({
      request: jest.fn().mockResolvedValue(
        jsonReply({ mail_id: "m-001", messages: [] })
      ),
    });
    const client = clientWith(t);
    const msgs = await client.list("m-001");
    expect(msgs).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// delete
// ---------------------------------------------------------------------------

describe("delete", () => {
  test("calls correct subject", async () => {
    const t = mockTransport({
      request: jest.fn().mockResolvedValue(jsonReply({ ok: true })),
    });
    const client = clientWith(t);
    await client.delete("m-001", "msg-42");

    expect(t.request).toHaveBeenCalledWith(
      "$mq9.AI.MAILBOX.DELETE.m-001.msg-42",
      expect.any(Uint8Array),
      expect.anything()
    );
  });
});

// ---------------------------------------------------------------------------
// not connected
// ---------------------------------------------------------------------------

describe("not connected", () => {
  test("throws MQ9Error", async () => {
    const client = new MQ9Client();
    await expect(client.list("m-001")).rejects.toThrow(MQ9Error);
  });
});

// ---------------------------------------------------------------------------
// request failure
// ---------------------------------------------------------------------------

describe("request failure", () => {
  test("throws MQ9Error on network error", async () => {
    const t = mockTransport({
      request: jest.fn().mockRejectedValue(new Error("timeout")),
    });
    const client = clientWith(t);
    const err = await client.list("m-001").catch((e) => e);
    expect(err).toBeInstanceOf(MQ9Error);
    expect(err.message).toContain("timeout");
  });
});
