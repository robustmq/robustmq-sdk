# mq9 Protocol Specification

mq9 is RobustMQ's AI-native async communication protocol, built on the NATS text protocol.
It gives every agent a **durable mailbox**: messages persist until TTL expires, so senders
and receivers do not need to be online simultaneously.

---

## Core Concepts

### Mailbox (`mail_id`)

A mailbox is an agent's communication address. Two types:

| Type | `mail_id` | Created via |
|------|-----------|-------------|
| Private | Server-generated UUID (e.g. `m-550e-...`) | `CREATE` without `name` |
| Public | User-defined string (e.g. `task.queue`) | `CREATE` with `name` |

Properties:
- **TTL** — mailbox auto-destroys when expired; all messages cleaned automatically
- **Idempotent creation** — repeating `CREATE` returns success, original TTL preserved
- **No discovery mechanism** — public mailboxes use meaningful, predictable names. Knowing the name is sufficient to subscribe or publish.
- **Security boundary** — private `mail_id` is not guessable; knowing the `mail_id` is the only access control

### Priority

Each message carries one of three priorities:

| Value | Use |
|-------|-----|
| `critical` | Highest priority — abort signals, emergency commands, security events |
| `urgent` | Urgent — task interrupts, time-sensitive instructions |
| `normal` (default, no suffix) | Routine communication — task dispatch, result delivery |

- Same-priority messages: FIFO
- Cross-priority: higher processed first
- Ordering guaranteed by the storage layer — no client-side sorting needed

### Store-first delivery

Messages are persisted before delivery. When a subscriber connects:

1. All non-expired messages are pushed immediately
2. New arrivals are pushed in real-time going forward

No read/unread state is tracked on the server. Subscribing again replays all non-expired messages.

### Message ID (`msg_id`)

Each message has a unique `msg_id` assigned by the server. Clients use it for deduplication and for calling `DELETE`.

---

## Subject Design

All mq9 subjects are prefixed with `$mq9.AI.`.

### MAILBOX.CREATE

**Subject:** `$mq9.AI.MAILBOX.CREATE`  
**Direction:** PUB (with reply subject for response)

Create a mailbox. The server responds on the reply subject.

**Request payload — private mailbox:**

```json
{ "ttl": 3600 }
```

**Request payload — public mailbox:**

```json
{
  "ttl": 86400,
  "public": true,
  "name": "task.queue",
  "desc": "Task distribution queue"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ttl` | int | yes | Mailbox lifetime in seconds |
| `public` | bool | no | If true, mailbox uses a user-defined name |
| `name` | string | no | Human-readable name (required when `public=true`) |
| `desc` | string | no | Description |

**Response payload:**

```json
{ "mail_id": "m-550e8400-e29b-41d4-a716-446655440000" }
```

For public mailboxes, `mail_id` equals the user-supplied `name`.

---

### MAILBOX.MSG.{mail_id} / MAILBOX.MSG.{mail_id}.{priority}

**Subject (default/normal):** `$mq9.AI.MAILBOX.MSG.{mail_id}` (no suffix)  
**Subject (urgent/critical):** `$mq9.AI.MAILBOX.MSG.{mail_id}.{priority}`  
**Direction:** PUB to send; SUB to receive

**Sending a message:**

Publish to the bare subject for `normal` (default), or append `.urgent` / `.critical` for higher priorities.

```
PUB $mq9.AI.MAILBOX.MSG.m-uuid-001
{"task": "summarize", "doc_id": "abc123"}

PUB $mq9.AI.MAILBOX.MSG.m-uuid-001.urgent
{"type": "interrupt"}

PUB $mq9.AI.MAILBOX.MSG.m-uuid-001.critical
{"type": "abort"}
```

Payload is arbitrary bytes — the server does not inspect it.

**Receiving messages (subscribe):**

```
SUB $mq9.AI.MAILBOX.MSG.m-uuid-001.*        # all priorities (normal, urgent, critical)
SUB $mq9.AI.MAILBOX.MSG.m-uuid-001          # normal only (bare subject, no suffix)
SUB $mq9.AI.MAILBOX.MSG.m-uuid-001.urgent   # urgent only
SUB $mq9.AI.MAILBOX.MSG.m-uuid-001.critical # critical only
```

Subscription behavior:
- Server immediately pushes all non-expired messages matching the subject pattern
- New messages are delivered in real-time
- Queue group subscriptions enable competitive consumption (each message → exactly one subscriber)

**Forbidden:**
Wildcard on `mail_id` is rejected — you must specify the exact `mail_id`:

```
# These are rejected:
nats sub '$mq9.AI.MAILBOX.MSG.*'
nats sub '$mq9.AI.MAILBOX.MSG.#'
```

---

### MAILBOX.LIST.{mail_id}

**Subject:** `$mq9.AI.MAILBOX.LIST.{mail_id}`  
**Direction:** PUB (with reply subject)

Returns a snapshot of all non-expired messages in the mailbox.  
This is a metadata view — payloads are **not** included.

**Request:** empty payload

**Response payload:**

```json
{
  "mail_id": "m-uuid-001",
  "messages": [
    { "msg_id": "msg-001", "priority": "critical", "ts": 1234567890 },
    { "msg_id": "msg-002", "priority": "urgent", "ts": 1234567891 }
  ]
}
```

| Field | Description |
|-------|-------------|
| `msg_id` | Unique message identifier |
| `priority` | Message priority |
| `ts` | Unix timestamp (seconds) of message creation |

---

### MAILBOX.DELETE.{mail_id}.{msg_id}

**Subject:** `$mq9.AI.MAILBOX.DELETE.{mail_id}.{msg_id}`  
**Direction:** PUB (with optional reply subject)

Delete a single processed message from the mailbox.

**Request:** empty payload

**Response payload:**

```json
{ "deleted": true }
```

---

## Subject Reference Table

| Operation | Subject | Direction |
|-----------|---------|-----------|
| Create mailbox | `$mq9.AI.MAILBOX.CREATE` | PUB+reply |
| Send message | `$mq9.AI.MAILBOX.MSG.{mail_id}.{priority}` | PUB |
| Subscribe (all priorities) | `$mq9.AI.MAILBOX.MSG.{mail_id}.*` | SUB |
| Subscribe (one priority) | `$mq9.AI.MAILBOX.MSG.{mail_id}.{priority}` | SUB |
| List messages (no payload) | `$mq9.AI.MAILBOX.LIST.{mail_id}` | PUB+reply |
| Delete message | `$mq9.AI.MAILBOX.DELETE.{mail_id}.{msg_id}` | PUB+reply |

---

## Public Mailboxes

Public mailboxes use user-defined, predictable names. There is no discovery endpoint.

Agents that need to communicate through a public mailbox agree on the name out-of-band (e.g. configuration, documentation). Knowing the name is sufficient to subscribe or publish:

```bash
# Subscribe to a known public mailbox
nats sub '$mq9.AI.MAILBOX.MSG.task.queue.*'

# Send to a known public mailbox (normal/default priority, no suffix)
nats pub '$mq9.AI.MAILBOX.MSG.task.queue' 'payload'
```

Creating a public mailbox:

```bash
nats pub '$mq9.AI.MAILBOX.CREATE' '{
  "ttl": 3600,
  "public": true,
  "name": "task.queue",
  "desc": "Task distribution queue"
}'
# → {"mail_id": "task.queue"}
```

---

## Competitive Consumption (Queue Groups)

Multiple subscribers with the same queue group name receive each message exactly once,
distributed round-robin:

```
SUB $mq9.AI.MAILBOX.MSG.task.queue.* [queue workers]
```

---

## Transport

mq9 runs on the NATS text protocol. Any NATS client (Go, Python, Rust, JavaScript, Java, .NET)
connects directly — no special SDK needed for raw access.

Default port: `4222`

---

## Error Handling

Servers return errors as JSON on the reply subject:

```json
{ "error": "mailbox not found", "code": 404 }
```

Common error codes:

| Code | Meaning |
|------|---------|
| 400 | Bad request (missing required fields) |
| 403 | Forbidden (wildcard mail_id subscription rejected) |
| 404 | Mailbox or message not found |
| 409 | Conflict (name already taken by another mailbox) |
| 410 | Mailbox expired |

---

## Typical Scenarios

### Scenario 1: Point-to-point Agent communication

Agent A creates a private mailbox and publishes its `mail_id` to a well-known public mailbox.
Agent B reads the public mailbox to discover Agent A's address, sends a task result, and Agent A receives it.

```bash
# ── Step 1: Agent A creates a private mailbox ────────────────────────────────
nats req '$mq9.AI.MAILBOX.CREATE' '{"ttl":3600}'
# → {"mail_id":"m-550e8400-e29b-41d4-a716-446655440000"}
# Agent A stores this mail_id locally.

# ── Step 2: Agent A creates a well-known public mailbox for address exchange ──
nats req '$mq9.AI.MAILBOX.CREATE' '{"ttl":3600,"public":true,"name":"agent-a.inbox","desc":"Agent A address board"}'
# → {"mail_id":"agent-a.inbox"}

# ── Step 3: Agent A publishes its private mail_id to the public mailbox ───────
nats pub '$mq9.AI.MAILBOX.MSG.agent-a.inbox' \
  '{"reply_to":"m-550e8400-e29b-41d4-a716-446655440000"}'

# ── Step 4: Agent B subscribes to the public mailbox to discover Agent A ──────
nats sub '$mq9.AI.MAILBOX.MSG.agent-a.inbox'
# ← {"reply_to":"m-550e8400-e29b-41d4-a716-446655440000"}
# Agent B now knows Agent A's private mail_id.

# ── Step 5: Agent B sends a task result to Agent A's private mailbox ──────────
nats pub '$mq9.AI.MAILBOX.MSG.m-550e8400-e29b-41d4-a716-446655440000.critical' \
  '{"status":"done","result":"analysis complete","score":0.97}'

# ── Step 6: Agent A subscribes to its private mailbox and receives the result ─
nats sub '$mq9.AI.MAILBOX.MSG.m-550e8400-e29b-41d4-a716-446655440000.*'
# ← {"status":"done","result":"analysis complete","score":0.97}

# ── Step 7: Agent A deletes the processed message ─────────────────────────────
# First list to get msg_id:
nats req '$mq9.AI.MAILBOX.LIST.m-550e8400-e29b-41d4-a716-446655440000' '{}'
# → {"mail_id":"m-550e...","messages":[{"msg_id":"msg-001","priority":"critical","ts":1700000001}]}

nats req '$mq9.AI.MAILBOX.DELETE.m-550e8400-e29b-41d4-a716-446655440000.msg-001' '{}'
# → {"deleted":true}
```

**Key points:**
- Agent A's private `mail_id` is a UUID — it is not guessable. Only agents that receive it can send to it.
- The public mailbox `agent-a.inbox` acts as a lightweight address directory.
- Because mq9 is store-first, Agent B can read the address even if it starts after Agent A published it.

---

### Scenario 2: Multi-worker competitive task queue

A producer sends tasks at different priorities to a public mailbox. Three workers subscribe with the same `queue_group`, so each task is delivered to exactly one worker.

```bash
# ── Step 1: Create the shared task queue ──────────────────────────────────────
nats req '$mq9.AI.MAILBOX.CREATE' \
  '{"ttl":86400,"public":true,"name":"task.queue","desc":"Shared worker task queue"}'
# → {"mail_id":"task.queue"}

# ── Step 2: Start 3 workers (run each in a separate terminal) ─────────────────
# Worker 1:
nats sub '$mq9.AI.MAILBOX.MSG.task.queue.*' --queue workers
# Worker 2:
nats sub '$mq9.AI.MAILBOX.MSG.task.queue.*' --queue workers
# Worker 3:
nats sub '$mq9.AI.MAILBOX.MSG.task.queue.*' --queue workers
# Each message is delivered to exactly one worker in the "workers" group.

# ── Step 3: Producer sends 5 tasks with mixed priorities ──────────────────────
nats pub '$mq9.AI.MAILBOX.MSG.task.queue.critical' '{"task_id":"t-001","type":"urgent-analysis"}'
nats pub '$mq9.AI.MAILBOX.MSG.task.queue'          '{"task_id":"t-002","type":"summarize"}'
nats pub '$mq9.AI.MAILBOX.MSG.task.queue.urgent'   '{"task_id":"t-003","type":"interrupt"}'
nats pub '$mq9.AI.MAILBOX.MSG.task.queue.critical' '{"task_id":"t-004","type":"alert"}'
nats pub '$mq9.AI.MAILBOX.MSG.task.queue'          '{"task_id":"t-005","type":"report"}'

# ── Step 4: Observe delivery ───────────────────────────────────────────────────
# Critical-priority tasks (t-001, t-004) are delivered before urgent and normal.
# Each task goes to exactly one worker — no duplicate processing.
# Workers that start after the producer still receive stored messages immediately.

# Example worker output (distribution will vary):
# Worker 1 ← t-001 (critical), t-003 (urgent)
# Worker 2 ← t-004 (critical), t-005 (normal)
# Worker 3 ← t-002 (normal)

# ── Step 5: Check remaining queue depth ───────────────────────────────────────
nats req '$mq9.AI.MAILBOX.LIST.task.queue' '{}'
# → {"mail_id":"task.queue","messages":[]}   (all consumed)
```

**Key points:**
- All workers use the same `queue_group` name (`workers`). NATS delivers each message to exactly one member.
- Critical and urgent messages stored before workers connect are still delivered in priority order (critical → urgent → normal) on subscribe.
- Workers can be added or removed at any time — the queue group adjusts automatically.
- If a worker crashes before deleting its message, the message remains in the mailbox and will be re-delivered when the worker reconnects (store-first semantics).
