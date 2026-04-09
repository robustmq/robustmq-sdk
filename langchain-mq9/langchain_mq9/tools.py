"""LangChain tools for the mq9 async Agent mailbox protocol."""

from __future__ import annotations

import asyncio
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from robustmq.mq9 import Client, Priority


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class CreateMailboxInput(BaseModel):
    ttl: int = Field(default=3600, description="Mailbox TTL in seconds.")


class SendMessageInput(BaseModel):
    mail_id: str = Field(description="The mailbox ID to send the message to.")
    content: str = Field(description="The message content to send.")
    priority: str = Field(
        default="normal",
        description="Message priority: 'high', 'normal', or 'low'.",
    )


class GetMessagesInput(BaseModel):
    mail_id: str = Field(description="The mailbox ID to retrieve messages from.")
    limit: int = Field(default=10, description="Maximum number of messages to return.")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class CreateMailboxTool(BaseTool):
    """Create a mq9 mailbox and return its mail_id."""

    name: str = "create_mailbox"
    description: str = (
        "Use this tool to create a new mq9 mailbox for an Agent. "
        "Returns a unique mail_id that serves as the Agent's communication address. "
        "Call this when you need to establish a new communication channel, "
        "receive messages from other Agents, or set up a temporary async inbox. "
        "The mailbox persists messages until TTL expires, so the sender does not "
        "need to be online when the receiver reads messages."
    )
    args_schema: Type[BaseModel] = CreateMailboxInput

    server: str = "nats://localhost:4222"

    def _run(self, ttl: int = 3600, **kwargs: Any) -> str:
        return asyncio.run(self._arun(ttl=ttl))

    async def _arun(self, ttl: int = 3600, **kwargs: Any) -> str:
        async with Client(self.server) as client:
            mailbox = await client.create(ttl=ttl)
        return mailbox.mail_id


class SendMessageTool(BaseTool):
    """Send a message to a mq9 mailbox."""

    name: str = "send_message"
    description: str = (
        "Use this tool to send an asynchronous message to another Agent or system "
        "via its mq9 mailbox address (mail_id). "
        "The recipient does not need to be online — messages are stored until TTL expires. "
        "Use priority='high' for urgent tasks that need immediate attention, "
        "priority='low' for background work, and priority='normal' (default) for everything else. "
        "Call this when you want to delegate a task, notify another Agent, "
        "or pass data to a downstream system."
    )
    args_schema: Type[BaseModel] = SendMessageInput

    server: str = "nats://localhost:4222"

    def _run(
        self,
        mail_id: str,
        content: str,
        priority: str = "normal",
        **kwargs: Any,
    ) -> str:
        return asyncio.run(self._arun(mail_id=mail_id, content=content, priority=priority))

    async def _arun(
        self,
        mail_id: str,
        content: str,
        priority: str = "normal",
        **kwargs: Any,
    ) -> str:
        try:
            p = Priority(priority)
        except ValueError:
            p = Priority.NORMAL

        async with Client(self.server) as client:
            await client.send(mail_id, content.encode(), priority=p)

        return f"Message sent to {mail_id} with priority '{priority}'."


class GetMessagesTool(BaseTool):
    """Retrieve pending messages from a mq9 mailbox."""

    name: str = "get_messages"
    description: str = (
        "Use this tool to check your mq9 inbox and retrieve messages sent by other Agents. "
        "Returns a list of messages with their content, priority, and timestamp. "
        "Call this when you are waiting for responses, checking for delegated task results, "
        "or polling for new instructions from other Agents. "
        "Messages are returned as metadata snapshots; use the mail_id you own to read your inbox."
    )
    args_schema: Type[BaseModel] = GetMessagesInput

    server: str = "nats://localhost:4222"

    def _run(self, mail_id: str, limit: int = 10, **kwargs: Any) -> str:
        return asyncio.run(self._arun(mail_id=mail_id, limit=limit))

    async def _arun(self, mail_id: str, limit: int = 10, **kwargs: Any) -> str:
        received: list[dict[str, Any]] = []

        async def handler(msg: Any) -> None:
            if len(received) < limit:
                received.append(
                    {
                        "content": msg.payload.decode(errors="replace"),
                        "priority": msg.priority.value,
                    }
                )

        async with Client(self.server) as client:
            sub = await client.subscribe(mail_id, handler)
            # Give a short window to drain any buffered messages
            await asyncio.sleep(0.5)
            await sub.unsubscribe()

        if not received:
            return f"No messages found in mailbox {mail_id}."

        lines = [f"Found {len(received)} message(s) in mailbox {mail_id}:"]
        for i, m in enumerate(received, 1):
            lines.append(f"  [{i}] priority={m['priority']}  content={m['content']}")
        return "\n".join(lines)
