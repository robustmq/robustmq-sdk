"""
langchain-mq9 demo — two Agents communicating asynchronously via mq9 mailboxes.

This demo does NOT require an LLM API key. It calls the tools directly to show
the full mq9 communication flow:

  Agent A  →  creates a mailbox  →  gets a mail_id
  Agent B  →  sends 3 messages to Agent A's mailbox
  Agent A  →  retrieves messages from its inbox

Run:
    cd demo/demo-langchain-mq9
    pip install -r requirements.txt
    python demo.py
"""

import asyncio

from langchain_mq9 import CreateMailboxTool, GetMessagesTool, SendMessageTool

# demo.robustmq.com is a public RobustMQ service for testing. Replace with your own server address if needed.
SERVER = "nats://demo.robustmq.com:4222"


async def main() -> None:
    create = CreateMailboxTool(server=SERVER)
    send = SendMessageTool(server=SERVER)
    get = GetMessagesTool(server=SERVER)

    # ── Agent A: create a mailbox ────────────────────────────────────────────
    mail_id = await create._arun(ttl=60)
    print(f"[agent-a] created mailbox: {mail_id}")

    # ── Agent B: send messages to Agent A ────────────────────────────────────
    result = await send._arun(mail_id=mail_id, content="Urgent: server is down!", priority="high")
    print(f"[agent-b] {result}")

    result = await send._arun(mail_id=mail_id, content="Daily report is ready.", priority="normal")
    print(f"[agent-b] {result}")

    result = await send._arun(mail_id=mail_id, content="Background sync complete.", priority="low")
    print(f"[agent-b] {result}")

    # ── Agent A: read inbox ──────────────────────────────────────────────────
    result = await get._arun(mail_id=mail_id, limit=10)
    print(f"\n[agent-a] inbox:\n{result}")


if __name__ == "__main__":
    asyncio.run(main())
