"""Mq9Toolkit — bundles all three mq9 tools for LangChain Agents."""

from __future__ import annotations

from typing import List

from langchain_core.tools import BaseTool
from langchain_core.tools.base import BaseToolkit
from pydantic import BaseModel

from .tools import CreateMailboxTool, GetMessagesTool, SendMessageTool


class Mq9Toolkit(BaseToolkit):
    """Toolkit that gives a LangChain Agent access to the mq9 mailbox protocol.

    Usage::

        toolkit = Mq9Toolkit(server="nats://localhost:4222")
        tools = toolkit.get_tools()

        agent = initialize_agent(tools, llm, ...)
    """

    server: str = "nats://localhost:4222"

    def get_tools(self) -> List[BaseTool]:
        """Return the three mq9 tools, each pre-configured with the server address."""
        return [
            CreateMailboxTool(server=self.server),
            SendMessageTool(server=self.server),
            GetMessagesTool(server=self.server),
        ]
