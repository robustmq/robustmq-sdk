"""
mq9 Python demo — connects to nats://demo.robustmq.com:4222 and runs the full scenario.

Run:
    cd demo/demo-python
    pip install -r requirements.txt
    python demo.py
"""

import asyncio
from robustmq.mq9 import Client, Priority


async def main() -> None:
    # demo.robustmq.com is a public RobustMQ service for testing. Replace with your own server address if needed.
    client = Client(server="nats://demo.robustmq.com:4222")
    await client.connect()
    print("[python] connected")

    # 1. Create a private mailbox (TTL 60s)
    mailbox = await client.create(ttl=60)
    print(f"[python] private mailbox: {mailbox.mail_id}")

    # 2. Send 3 messages with different priorities
    await client.send(mailbox.mail_id, b"abort signal", priority=Priority.CRITICAL)
    await client.send(mailbox.mail_id, b"urgent task", priority=Priority.URGENT)
    await client.send(mailbox.mail_id, b"normal task", priority=Priority.NORMAL)
    print("[python] sent 3 messages (critical / urgent / normal)")

    # 3. Subscribe and print received messages
    async def handler(msg):
        print(f"[python] received [{msg.priority.value}] {msg.payload.decode()}")

    sub = await client.subscribe(mailbox.mail_id, handler)
    await asyncio.sleep(0.5)
    await sub.unsubscribe()

    # 4. List mailbox metadata
    metas = await client.list(mailbox.mail_id)
    print(f"[python] list: {len(metas)} message(s) in mailbox")
    for m in metas:
        print(f"  msg_id={m.msg_id}  priority={m.priority.value}  ts={m.ts}")

    # 5. Delete first message
    if metas:
        await client.delete(mailbox.mail_id, metas[0].msg_id)
        print(f"[python] deleted {metas[0].msg_id}")

    # 6. Create a public mailbox
    pub = await client.create(ttl=60, public=True, name="demo.queue", desc="Demo queue")
    print(f"[python] public mailbox: {pub.mail_id}")

    await client.close()
    print("[python] done")


if __name__ == "__main__":
    asyncio.run(main())
