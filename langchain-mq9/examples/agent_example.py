"""Two LangChain Agents communicating asynchronously via mq9 mailboxes.

Agent A creates a mailbox and passes its address to Agent B.
Agent B sends a message to Agent A's mailbox.
Agent A retrieves and prints the message.

Run:
    pip install langchain-mq9 langchain-openai
    export OPENAI_API_KEY=...
    python examples/agent_example.py
"""

import asyncio

from langchain.agents import AgentType, initialize_agent
from langchain_openai import ChatOpenAI

from langchain_mq9 import Mq9Toolkit

SERVER = "nats://demo.robustmq.com:4222"


def make_agent(name: str, llm: ChatOpenAI) -> tuple:
    toolkit = Mq9Toolkit(server=SERVER)
    tools = toolkit.get_tools()
    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.OPENAI_FUNCTIONS,
        verbose=True,
        agent_kwargs={"system_message": f"You are {name}, an AI Agent."},
    )
    return agent, tools


async def main() -> None:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    agent_a, _ = make_agent("Agent A", llm)
    agent_b, _ = make_agent("Agent B", llm)

    # Step 1: Agent A creates a mailbox
    print("=== Agent A: creating mailbox ===")
    result_a = agent_a.invoke(
        {"input": "Create a mailbox with TTL of 3600 seconds and tell me the mail_id."}
    )
    mail_id = result_a["output"].strip()
    print(f"Agent A mailbox: {mail_id}\n")

    # Step 2: Agent B sends a message to Agent A's mailbox
    print("=== Agent B: sending message ===")
    agent_b.invoke(
        {
            "input": (
                f"Send a high-priority message to mailbox '{mail_id}' "
                "with content: 'Task complete: analysis finished successfully.'"
            )
        }
    )
    print()

    # Step 3: Agent A reads its inbox
    print("=== Agent A: checking inbox ===")
    result_check = agent_a.invoke(
        {"input": f"Check my mailbox '{mail_id}' and retrieve any messages."}
    )
    print(f"\nAgent A received:\n{result_check['output']}")


if __name__ == "__main__":
    asyncio.run(main())
