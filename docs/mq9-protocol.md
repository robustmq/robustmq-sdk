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
| `high` | Urgent (task abort, emergency commands) |
| `normal` | Regular communication (task distribution, results) |
| `low` | Background (logging, status reports) |

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

### MAILBOX.MSG.{mail_id}.{priority}

**Subject:** `$mq9.AI.MAILBOX.MSG.{mail_id}.{priority}`  
**Direction:** PUB to send; SUB to receive

**Sending a message:**

Publish to the subject where `priority` is one of `high`, `normal`, `low`.

```
PUB $mq9.AI.MAILBOX.MSG.m-uuid-001.normal
{"task": "summarize", "doc_id": "abc123"}
```

Payload is arbitrary bytes — the server does not inspect it.

**Receiving messages (subscribe):**

Subscribe with wildcard `*` to receive all priorities, or specify a single priority:

```
SUB $mq9.AI.MAILBOX.MSG.m-uuid-001.*        # all priorities
SUB $mq9.AI.MAILBOX.MSG.m-uuid-001.high     # high only
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
    { "msg_id": "msg-001", "priority": "high", "ts": 1234567890 },
    { "msg_id": "msg-002", "priority": "normal", "ts": 1234567891 }
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

# Send to a known public mailbox
nats pub '$mq9.AI.MAILBOX.MSG.task.queue.normal' 'payload'
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
