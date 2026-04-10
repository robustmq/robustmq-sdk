"""
Agent A (Python) — creates a mailbox, sends 3 tasks to Agent B via a public
rendezvous mailbox, then waits for Agent B to send back results.

Run order: start agent_b.go first, then this script.

Run:
    cd demo/demo-multi-agent
    pip install robustmq
    python agent_a.py
"""

import asyncio

from robustmq.mq9 import Client, Priority

# demo.robustmq.com is a public RobustMQ service for testing. Replace with your own server address if needed.
SERVER = "nats://demo.robustmq.com:4222"

# Well-known public mailbox used as a rendezvous point so Agent B can
# discover Agent A's private mail_id without prior configuration.
RENDEZVOUS = "demo.multi-agent.rendezvous"

TASKS = [
    ("Analyze sentiment of Q3 earnings call", Priority.CRITICAL),
    ("Summarize the latest research papers", Priority.URGENT),
    ("Index new documents in the knowledge base", Priority.NORMAL),
]


async def main() -> None:
    async with Client(server=SERVER) as client:
        # 1. Create Agent A's private reply mailbox
        mailbox = await client.create(ttl=120)
        print(f"[agent-a] private mailbox: {mailbox.mail_id}")

        # 2. Publish Agent A's mail_id to the public rendezvous mailbox
        #    so Agent B knows where to send results
        await client.create(ttl=120, public=True, name=RENDEZVOUS, desc="address exchange")
        await client.send(
            RENDEZVOUS,
            mailbox.mail_id.encode(),
            priority=Priority.CRITICAL,
        )
        print(f"[agent-a] published reply address to '{RENDEZVOUS}'")

        # 3. Send 3 tasks to Agent B via the rendezvous mailbox
        for content, priority in TASKS:
            await client.send(RENDEZVOUS, content.encode(), priority=priority)
            print(f"[agent-a] sent task [{priority.value}]: {content}")

        # 4. Subscribe to own mailbox and collect results from Agent B
        results: list[str] = []
        expected = len(TASKS)

        async def on_result(msg):
            text = msg.payload.decode()
            results.append(text)
            print(f"[agent-a] received result [{msg.priority.value}]: {text}")

        sub = await client.subscribe(mailbox.mail_id, on_result)

        # Wait until all results arrive (or timeout after 15 s)
        deadline = asyncio.get_event_loop().time() + 15
        while len(results) < expected:
            if asyncio.get_event_loop().time() > deadline:
                print(f"[agent-a] timeout — received {len(results)}/{expected} results")
                break
            await asyncio.sleep(0.2)

        await sub.unsubscribe()
        print(f"[agent-a] done — received {len(results)}/{expected} results")


if __name__ == "__main__":
    asyncio.run(main())
