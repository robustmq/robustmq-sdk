"""Mq9Toolkit — bundles all mq9 tools for LangChain Agents."""

from __future__ import annotations

from typing import List

from langchain_core.tools import BaseTool
from langchain_core.tools.base import BaseToolkit

from .tools import (
    CreateMailboxTool,
    CreatePublicMailboxTool,
    DeleteMessageTool,
    GetMessagesTool,
    ListMessagesTool,
    SendMessageTool,
)


class Mq9Toolkit(BaseToolkit):
    """Toolkit that gives a LangChain Agent full access to the mq9 mailbox protocol.

    Covers all protocol operations:
    - CreateMailboxTool        — create a private mailbox
    - CreatePublicMailboxTool  — create a named public mailbox
    - SendMessageTool          — send a message with priority
    - GetMessagesTool          — subscribe and read messages with payload
    - ListMessagesTool         — list message metadata (no payload)
    - DeleteMessageTool        — delete a processed message

    Usage::

        toolkit = Mq9Toolkit(server="nats://demo.robustmq.com:4222")
        tools = toolkit.get_tools()

        agent = initialize_agent(tools, llm, ...)
    """

    server: str = "nats://localhost:4222"

    def get_tools(self) -> List[BaseTool]:
        """Return all 6 mq9 tools, each pre-configured with the server address."""
        return [
            CreateMailboxTool(server=self.server),
            CreatePublicMailboxTool(server=self.server),
            SendMessageTool(server=self.server),
            GetMessagesTool(server=self.server),
            ListMessagesTool(server=self.server),
            DeleteMessageTool(server=self.server),
        ]
