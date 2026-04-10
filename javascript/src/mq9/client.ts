/**
 * mq9 client — AI-native async Agent mailbox communication over NATS.
 */

import { connect, NatsConnection, Subscription } from "nats";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Priority = "critical" | "urgent" | "normal";

export interface Mailbox {
  mailId: string;
  public: boolean;
  name: string;
  desc: string;
}

export interface MessageMeta {
  msgId: string;
  priority: Priority;
  ts: number;
}

export interface Mq9Message {
  msgId: string;
  mailId: string;
  priority: Priority;
  payload: Uint8Array;
}

export interface CreateOptions {
  ttl: number;
  public?: boolean;
  name?: string;
  desc?: string;
}

export interface SubscribeOptions {
  priority?: Priority | "*"; // "*" = all priorities (default)
  queueGroup?: string;
}

export class MQ9Error extends Error {
  readonly code: number;
  constructor(message: string, code = 0) {
    super(message);
    this.name = "MQ9Error";
    this.code = code;
  }
}

// ---------------------------------------------------------------------------
// Subject helpers
// ---------------------------------------------------------------------------

const PREFIX = "$mq9.AI";
const MAILBOX_CREATE = `${PREFIX}.MAILBOX.CREATE`;

function subjectMsgBase(mailId: string): string {
  return `${PREFIX}.MAILBOX.MSG.${mailId}`;
}

// Send subject: normal uses bare (no suffix); urgent/critical append suffix.
function subjectMsg(mailId: string, priority: string): string {
  if (priority === "normal") return subjectMsgBase(mailId);
  return `${subjectMsgBase(mailId)}.${priority}`;
}

// Subscribe subject: "*" uses wildcard; normal uses bare; others append suffix.
function subjectSub(mailId: string, priority: string): string {
  if (priority === "*") return `${subjectMsgBase(mailId)}.*`;
  if (priority === "normal") return subjectMsgBase(mailId);
  return `${subjectMsgBase(mailId)}.${priority}`;
}
function subjectList(mailId: string): string {
  return `${PREFIX}.MAILBOX.LIST.${mailId}`;
}
function subjectDelete(mailId: string, msgId: string): string {
  return `${PREFIX}.MAILBOX.DELETE.${mailId}.${msgId}`;
}

// ---------------------------------------------------------------------------
// Internal NATS transport interface (enables unit-testing without live server)
// ---------------------------------------------------------------------------

export interface NatsTransport {
  publish(subject: string, data: Uint8Array): void;
  request(
    subject: string,
    data: Uint8Array,
    opts?: { timeout?: number },
  ): Promise<{ data: Uint8Array }>;
  subscribe(
    subject: string,
    opts?: { queue?: string },
  ): AsyncIterable<{ subject: string; data: Uint8Array }> & {
    unsubscribe(): void;
  };
  drain(): Promise<void>;
}

// ---------------------------------------------------------------------------
// MQ9Client
// ---------------------------------------------------------------------------

export class MQ9Client {
  private readonly server: string;
  private readonly requestTimeout: number;
  // Internal — allows injecting a mock transport in tests
  _transport: NatsTransport | null = null;

  constructor(opts: { server?: string; requestTimeout?: number } = {}) {
    this.server = opts.server ?? "nats://localhost:4222";
    this.requestTimeout = opts.requestTimeout ?? 5000;
  }

  // ── Connection ────────────────────────────────────────────────────────────

  async connect(): Promise<void> {
    const nc = await connect({ servers: this.server });
    this._transport = new RealTransport(nc);
  }

  async close(): Promise<void> {
    await this._transport?.drain();
    this._transport = null;
  }

  // Support "await using" (TS 5.2+)
  async [Symbol.for("Symbol.asyncDispose")](): Promise<void> {
    await this.close();
  }

  // ── Create ────────────────────────────────────────────────────────────────

  async create(opts: CreateOptions): Promise<Mailbox> {
    if (opts.public && !opts.name) {
      throw new MQ9Error("name is required when public=true");
    }

    const req: Record<string, unknown> = { ttl: opts.ttl };
    if (opts.public) {
      req.public = true;
      req.name = opts.name;
      if (opts.desc) req.desc = opts.desc;
    }

    const resp = await this.request(MAILBOX_CREATE, req);
    const mailId = resp.mail_id as string;
    return {
      mailId,
      public: opts.public ?? false,
      name: opts.name ?? "",
      desc: opts.desc ?? "",
    };
  }

  // ── Send ──────────────────────────────────────────────────────────────────

  async send(
    mailId: string,
    payload: Uint8Array | string | object,
    priority: Priority = "normal",
  ): Promise<void> {
    this.ensureConnected();
    const subject = subjectMsg(mailId, priority);
    const data = encodePayload(payload);
    this._transport!.publish(subject, data);
  }

  // ── Subscribe ─────────────────────────────────────────────────────────────

  async subscribe(
    mailId: string,
    callback: (msg: Mq9Message) => Promise<void>,
    opts: SubscribeOptions = {},
  ): Promise<{ unsubscribe(): void }> {
    this.ensureConnected();
    const priority = opts.priority ?? "*";
    const subject = subjectSub(mailId, priority);
    const sub = this._transport!.subscribe(subject, {
      queue: opts.queueGroup,
    });

    const loop = async () => {
      for await (const raw of sub) {
        try {
          const msg = parseIncoming(mailId, raw.subject, raw.data);
          await callback(msg);
        } catch {
          // swallow to keep subscription alive
        }
      }
    };
    loop(); // fire-and-forget background loop

    return { unsubscribe: () => sub.unsubscribe() };
  }

  // ── List ──────────────────────────────────────────────────────────────────

  async list(mailId: string): Promise<MessageMeta[]> {
    const resp = await this.request(subjectList(mailId), {});
    const metas: MessageMeta[] = [];
    for (const m of (resp.messages as unknown[]) ?? []) {
      const node = m as Record<string, unknown>;
      metas.push({
        msgId: (node.msg_id as string) ?? "",
        priority: toPriority((node.priority as string) ?? "normal"),
        ts: (node.ts as number) ?? 0,
      });
    }
    return metas;
  }

  // ── Delete ────────────────────────────────────────────────────────────────

  async delete(mailId: string, msgId: string): Promise<void> {
    await this.request(subjectDelete(mailId, msgId), {});
  }

  // ── Internal helpers ─────────────────────────────────────────────────────

  private ensureConnected(): void {
    if (!this._transport) {
      throw new MQ9Error("Not connected. Call connect() first.");
    }
  }

  private async request(
    subject: string,
    payload: object,
  ): Promise<Record<string, unknown>> {
    this.ensureConnected();
    const data = encodePayload(payload);
    let reply: { data: Uint8Array };
    try {
      reply = await this._transport!.request(subject, data, {
        timeout: this.requestTimeout,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new MQ9Error(`request failed: ${msg}`);
    }
    const resp = JSON.parse(Buffer.from(reply.data).toString("utf8")) as Record<
      string,
      unknown
    >;
    if (resp.error) {
      throw new MQ9Error(resp.error as string, (resp.code as number) ?? 0);
    }
    return resp;
  }
}

// ---------------------------------------------------------------------------
// Real NATS transport
// ---------------------------------------------------------------------------

class RealTransport implements NatsTransport {
  constructor(private readonly nc: NatsConnection) {}

  publish(subject: string, data: Uint8Array): void {
    this.nc.publish(subject, data);
  }

  async request(
    subject: string,
    data: Uint8Array,
    opts?: { timeout?: number },
  ): Promise<{ data: Uint8Array }> {
    const msg = await this.nc.request(subject, data, {
      timeout: opts?.timeout ?? 5000,
    });
    return { data: msg.data };
  }

  subscribe(
    subject: string,
    opts?: { queue?: string },
  ): AsyncIterable<{ subject: string; data: Uint8Array }> & {
    unsubscribe(): void;
  } {
    const sub: Subscription = this.nc.subscribe(subject, {
      queue: opts?.queue,
    });
    return sub as unknown as AsyncIterable<{
      subject: string;
      data: Uint8Array;
    }> & { unsubscribe(): void };
  }

  async drain(): Promise<void> {
    await this.nc.drain();
  }
}

// ---------------------------------------------------------------------------
// Payload encoding
// ---------------------------------------------------------------------------

function encodePayload(payload: Uint8Array | string | object): Uint8Array {
  if (payload instanceof Uint8Array) return payload;
  if (typeof payload === "string") return Buffer.from(payload);
  return Buffer.from(JSON.stringify(payload));
}

// ---------------------------------------------------------------------------
// Message parsing
// ---------------------------------------------------------------------------

function parseIncoming(
  mailId: string,
  subject: string,
  data: Uint8Array,
): Mq9Message {
  const base = subjectMsgBase(mailId);
  const suffix = subject.startsWith(base) ? subject.slice(base.length) : "";
  const priorityStr = suffix.startsWith(".") ? suffix.slice(1) : "";
  const priority = toPriority(priorityStr);

  try {
    const node = JSON.parse(Buffer.from(data).toString("utf8")) as Record<
      string,
      unknown
    >;
    if (node.msg_id !== undefined) {
      return parseMessageNode(mailId, node);
    }
  } catch {
    // fall through
  }

  return { msgId: "", mailId, priority, payload: data };
}

function parseMessageNode(
  mailId: string,
  node: Record<string, unknown>,
): Mq9Message {
  const rawPayload = (node.payload as string) ?? "";
  const payload = rawPayload
    ? Buffer.from(rawPayload, "base64")
    : new Uint8Array();
  return {
    msgId: (node.msg_id as string) ?? "",
    mailId,
    priority: toPriority((node.priority as string) ?? "normal"),
    payload,
  };
}

function toPriority(s: string): Priority {
  if (s === "critical" || s === "urgent") return s;
  return "normal";
}
