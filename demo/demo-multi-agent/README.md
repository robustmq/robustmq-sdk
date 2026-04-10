# Multi-Agent Demo: Python ↔ Go

Demonstrates cross-language Agent communication via mq9:

- **Agent A** (Python) creates a private mailbox, publishes its address to a public rendezvous mailbox, sends 3 tasks with different priorities, then waits for results.
- **Agent B** (Go) subscribes to the rendezvous mailbox, discovers Agent A's reply address, processes each task, and sends results back.

```
Agent A (Python)                         Agent B (Go)
      │                                        │
      │── create private mailbox ──────────────│
      │── publish reply address ──────────────▶│ (rendezvous mailbox)
      │── send task [critical] ───────────────▶│
      │── send task [normal] ────────────────▶│
      │── send task [urgent] ───────────────▶│
      │                                        │── process + send result ──▶ Agent A
      │                                        │── process + send result ──▶ Agent A
      │                                        │── process + send result ──▶ Agent A
      │◀── receive result ─────────────────────│
      │◀── receive result ─────────────────────│
      │◀── receive result ─────────────────────│
```

## Prerequisites

- Access to `nats://demo.robustmq.com:4222` (public RobustMQ service), or run your own RobustMQ instance
- Python 3.10+
- Go 1.21+

## Run

Open two terminals.

**Terminal 1 — start Agent B first** (it must be subscribed before Agent A sends):

```bash
cd demo/demo-multi-agent
go run agent_b.go
```

**Terminal 2 — start Agent A**:

```bash
cd demo/demo-multi-agent
pip install robustmq
python agent_a.py
```

## Expected output

**Agent B (Go):**

```
[agent-b] connected, waiting for messages on demo.multi-agent.rendezvous
[agent-b] discovered Agent A reply address: m-550e8400-...
[agent-b] processing [critical]: Analyze sentiment of Q3 earnings call
[agent-b] sent result to m-550e8400-...: DONE: Analyze sentiment of Q3 earnings call
[agent-b] processing [normal]: Summarize the latest research papers
[agent-b] sent result to m-550e8400-...: DONE: Summarize the latest research papers
[agent-b] processing [urgent]: Index new documents in the knowledge base
[agent-b] sent result to m-550e8400-...: DONE: Index new documents in the knowledge base
[agent-b] done — processed 3 tasks
```

**Agent A (Python):**

```
[agent-a] private mailbox: m-550e8400-...
[agent-a] published reply address to 'demo.multi-agent.rendezvous'
[agent-a] sent task [critical]: Analyze sentiment of Q3 earnings call
[agent-a] sent task [normal]: Summarize the latest research papers
[agent-a] sent task [urgent]: Index new documents in the knowledge base
[agent-a] received result [normal]: DONE: Analyze sentiment of Q3 earnings call
[agent-a] received result [normal]: DONE: Summarize the latest research papers
[agent-a] received result [normal]: DONE: Index new documents in the knowledge base
[agent-a] done — received 3/3 results
```

## What this demo shows

| Concept | Where |
|---------|-------|
| Private mailbox as a secure reply channel | `agent_a.py` — `client.create(ttl=120)` |
| Public mailbox as an address rendezvous | `agent_a.py` — `client.create(..., public=True, name=rendezvous)` |
| Priority-ordered task delivery | Agent B receives `critical` before `urgent` before `normal` |
| Cross-language communication | Python SDK → Go SDK, same NATS subjects |
| Store-first semantics | Agent B can start after Agent A publishes — it still gets all messages |
