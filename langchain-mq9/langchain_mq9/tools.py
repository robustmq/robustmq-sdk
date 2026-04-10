"""LangChain tools for the mq9 async Agent mailbox protocol."""

from __future__ import annotations

import asyncio
from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from robustmq.mq9 import Client, Priority


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class CreateMailboxInput(BaseModel):
    ttl: int = Field(default=3600, description="Mailbox TTL in seconds.")


class CreatePublicMailboxInput(BaseModel):
    name: str = Field(description="Public mailbox name (e.g. 'task.queue'). Must be unique.")
    ttl: int = Field(default=86400, description="Mailbox TTL in seconds.")
    desc: str = Field(default="", description="Optional description of the mailbox.")


class SendMessageInput(BaseModel):
    mail_id: str = Field(description="The mailbox ID to send the message to.")
    content: str = Field(description="The message content to send.")
    priority: str = Field(
        default="normal",
        description="Message priority: 'critical', 'urgent', or 'normal' (default).",
    )


class GetMessagesInput(BaseModel):
    mail_id: str = Field(description="The mailbox ID to retrieve messages from.")
    limit: int = Field(default=10, description="Maximum number of messages to return.")


class ListMessagesInput(BaseModel):
    mail_id: str = Field(description="The mailbox ID to list message metadata from.")


class DeleteMessageInput(BaseModel):
    mail_id: str = Field(description="The mailbox ID that contains the message.")
    msg_id: str = Field(description="The message ID to delete.")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class CreateMailboxTool(BaseTool):
    """Create a private mq9 mailbox and return its mail_id."""

    name: str = "create_mailbox"
    description: str = (
        "Use this tool to create a new private mq9 mailbox for an Agent. "
        "Returns a unique mail_id (UUID) that serves as the Agent's communication address. "
        "Call this when you need to establish a new communication channel, "
        "receive messages from other Agents, or set up a temporary async inbox. "
        "The mailbox persists messages until TTL expires, so the sender does not "
        "need to be online when the receiver reads messages. "
        "Use create_public_mailbox instead if you need a human-readable, predictable address."
    )
    args_schema: Type[BaseModel] = CreateMailboxInput

    server: str = "nats://localhost:4222"

    def _run(self, ttl: int = 3600, **kwargs: Any) -> str:
        return asyncio.run(self._arun(ttl=ttl))

    async def _arun(self, ttl: int = 3600, **kwargs: Any) -> str:
        async with Client(self.server) as client:
            mailbox = await client.create(ttl=ttl)
        return mailbox.mail_id


class CreatePublicMailboxTool(BaseTool):
    """Create a public mq9 mailbox with a user-defined name."""

    name: str = "create_public_mailbox"
    description: str = (
        "Use this tool to create a public mq9 mailbox with a human-readable, predictable name "
        "(e.g. 'task.queue', 'agent.results'). "
        "The mail_id equals the name you provide, so other Agents can send messages "
        "without being told the address first — they just need to agree on the name. "
        "Call this when setting up a shared channel, a well-known task queue, "
        "or any mailbox whose address must be known in advance. "
        "Creation is idempotent: repeating with the same name returns success and preserves the original TTL."
    )
    args_schema: Type[BaseModel] = CreatePublicMailboxInput

    server: str = "nats://localhost:4222"

    def _run(self, name: str, ttl: int = 86400, desc: str = "", **kwargs: Any) -> str:
        return asyncio.run(self._arun(name=name, ttl=ttl, desc=desc))

    async def _arun(self, name: str, ttl: int = 86400, desc: str = "", **kwargs: Any) -> str:
        async with Client(self.server) as client:
            mailbox = await client.create(ttl=ttl, public=True, name=name, desc=desc)
        return f"Public mailbox created. mail_id='{mailbox.mail_id}'"


class SendMessageTool(BaseTool):
    """Send a message to a mq9 mailbox."""

    name: str = "send_message"
    description: str = (
        "Use this tool to send an asynchronous message to another Agent or system "
        "via its mq9 mailbox address (mail_id). "
        "The recipient does not need to be online — messages are stored until TTL expires. "
        "Use priority='critical' for abort signals or emergencies, "
        "priority='urgent' for time-sensitive interrupts, "
        "and priority='normal' (default) for routine messages. "
        "Call this when you want to delegate a task, notify another Agent, "
        "or pass data to a downstream system."
    )
    args_schema: Type[BaseModel] = SendMessageInput

    server: str = "nats://localhost:4222"

    def _run(self, mail_id: str, content: str, priority: str = "normal", **kwargs: Any) -> str:
        return asyncio.run(self._arun(mail_id=mail_id, content=content, priority=priority))

    async def _arun(self, mail_id: str, content: str, priority: str = "normal", **kwargs: Any) -> str:
        try:
            p = Priority(priority)
        except ValueError:
            p = Priority.NORMAL

        async with Client(self.server) as client:
            await client.send(mail_id, content.encode(), priority=p)

        return f"Message sent to '{mail_id}' with priority '{p.value}'."


class GetMessagesTool(BaseTool):
    """Subscribe to a mq9 mailbox and retrieve pending messages with full payload."""

    name: str = "get_messages"
    description: str = (
        "Use this tool to check your mq9 inbox and retrieve messages sent by other Agents, "
        "including the full message content (payload). "
        "Call this when you are waiting for responses, checking for delegated task results, "
        "or polling for new instructions. "
        "To only see message metadata (msg_id, priority, timestamp) without payloads, "
        "use list_messages instead — it is faster and does not consume messages."
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
            await asyncio.sleep(0.5)
            await sub.unsubscribe()

        if not received:
            return f"No messages found in mailbox '{mail_id}'."

        lines = [f"Found {len(received)} message(s) in mailbox '{mail_id}':"]
        for i, m in enumerate(received, 1):
            lines.append(f"  [{i}] priority={m['priority']}  content={m['content']}")
        return "\n".join(lines)


class ListMessagesTool(BaseTool):
    """List message metadata in a mq9 mailbox without consuming them."""

    name: str = "list_messages"
    description: str = (
        "Use this tool to get a metadata snapshot of all pending messages in a mq9 mailbox. "
        "Returns msg_id, priority, and timestamp for each message — no payload is included. "
        "Call this when you want to inspect what is queued, count pending messages, "
        "check message priorities, or find a specific msg_id before deleting it. "
        "This is a non-destructive read: messages remain in the mailbox after listing. "
        "Use get_messages instead if you need the actual message content."
    )
    args_schema: Type[BaseModel] = ListMessagesInput

    server: str = "nats://localhost:4222"

    def _run(self, mail_id: str, **kwargs: Any) -> str:
        return asyncio.run(self._arun(mail_id=mail_id))

    async def _arun(self, mail_id: str, **kwargs: Any) -> str:
        async with Client(self.server) as client:
            metas = await client.list(mail_id)

        if not metas:
            return f"No messages in mailbox '{mail_id}'."

        lines = [f"{len(metas)} message(s) in mailbox '{mail_id}':"]
        for m in metas:
            lines.append(f"  msg_id={m.msg_id}  priority={m.priority.value}  ts={m.ts}")
        return "\n".join(lines)


class DeleteMessageTool(BaseTool):
    """Delete a specific message from a mq9 mailbox."""

    name: str = "delete_message"
    description: str = (
        "Use this tool to delete a specific message from a mq9 mailbox by its msg_id. "
        "Call this after processing a message to prevent it from being re-delivered "
        "on the next subscribe, or to clean up messages that are no longer needed. "
        "Use list_messages first to obtain the msg_id of the message you want to delete. "
        "Deleting a message is permanent and cannot be undone."
    )
    args_schema: Type[BaseModel] = DeleteMessageInput

    server: str = "nats://localhost:4222"

    def _run(self, mail_id: str, msg_id: str, **kwargs: Any) -> str:
        return asyncio.run(self._arun(mail_id=mail_id, msg_id=msg_id))

    async def _arun(self, mail_id: str, msg_id: str, **kwargs: Any) -> str:
        async with Client(self.server) as client:
            await client.delete(mail_id, msg_id)
        return f"Message '{msg_id}' deleted from mailbox '{mail_id}'."
