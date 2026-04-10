"""
langchain-mq9 demo — two Agents communicating via mq9 using all 6 protocol operations.

Flow:
  Agent A creates a private mailbox
  Agent B creates a public mailbox (shared channel)
  Agent B sends 3 messages (critical / urgent / normal) to Agent A
  Agent A lists message metadata (no payload)
  Agent A reads messages with full content
  Agent A deletes the first message

Run:
    cd demo/demo-langchain-mq9
    pip install -r requirements.txt
    python demo.py
"""

import asyncio

from langchain_mq9 import (
    CreateMailboxTool,
    CreatePublicMailboxTool,
    DeleteMessageTool,
    GetMessagesTool,
    ListMessagesTool,
    SendMessageTool,
)

# demo.robustmq.com is a public RobustMQ service for testing. Replace with your own server address if needed.
SERVER = "nats://demo.robustmq.com:4222"


async def main() -> None:
    create = CreateMailboxTool(server=SERVER)
    create_public = CreatePublicMailboxTool(server=SERVER)
    send = SendMessageTool(server=SERVER)
    get = GetMessagesTool(server=SERVER)
    list_msgs = ListMessagesTool(server=SERVER)
    delete = DeleteMessageTool(server=SERVER)

    # ── Agent A: create a private mailbox ────────────────────────────────────
    mail_id = await create._arun(ttl=60)
    print(f"[agent-a] private mailbox: {mail_id}")

    # ── Agent B: create a public mailbox (shared channel) ────────────────────
    result = await create_public._arun(name="demo.channel", ttl=60, desc="Demo shared channel")
    print(f"[agent-b] {result}")

    # ── Agent B: send 3 messages to Agent A ──────────────────────────────────
    result = await send._arun(mail_id=mail_id, content="ABORT: pipeline failed!", priority="critical")
    print(f"[agent-b] {result}")

    result = await send._arun(mail_id=mail_id, content="Interrupt: daily report ready.", priority="urgent")
    print(f"[agent-b] {result}")

    result = await send._arun(mail_id=mail_id, content="Background sync complete.", priority="normal")
    print(f"[agent-b] {result}")

    # ── Agent A: list message metadata (no payload) ───────────────────────────
    result = await list_msgs._arun(mail_id=mail_id)
    print(f"\n[agent-a] list:\n{result}")

    # ── Agent A: read messages with full content ──────────────────────────────
    result = await get._arun(mail_id=mail_id, limit=10)
    print(f"\n[agent-a] inbox:\n{result}")

    # ── Agent A: delete first message ─────────────────────────────────────────
    metas_result = await list_msgs._arun(mail_id=mail_id)
    # Parse first msg_id from metadata output
    first_msg_id = None
    for line in metas_result.splitlines():
        if "msg_id=" in line:
            first_msg_id = line.strip().split("msg_id=")[1].split(" ")[0]
            break

    if first_msg_id:
        result = await delete._arun(mail_id=mail_id, msg_id=first_msg_id)
        print(f"\n[agent-a] {result}")

    print("\n[done]")


if __name__ == "__main__":
    asyncio.run(main())
