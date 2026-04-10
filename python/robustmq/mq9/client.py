"""mq9 client — async Agent mailbox communication over NATS."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable

import nats
import nats.errors
from nats.aio.client import Client as NATSClient
from nats.aio.msg import Msg
from nats.aio.subscription import Subscription

logger = logging.getLogger(__name__)

# Subject constants
_PREFIX = "$mq9.AI"
_MAILBOX_CREATE = f"{_PREFIX}.MAILBOX.CREATE"
_MAILBOX_MSG_BASE = f"{_PREFIX}.MAILBOX.MSG.{{mail_id}}"
_MAILBOX_LIST = f"{_PREFIX}.MAILBOX.LIST.{{mail_id}}"
_MAILBOX_DELETE = f"{_PREFIX}.MAILBOX.DELETE.{{mail_id}}.{{msg_id}}"

# Request/response timeout
_REQUEST_TIMEOUT = 5.0  # seconds


def _msg_subject(mail_id: str, priority: "Priority") -> str:
    """Return the NATS subject for sending a message.

    normal (default) uses the bare subject (no suffix).
    urgent and critical append the priority as a suffix.
    """
    if priority == Priority.NORMAL:
        return _MAILBOX_MSG_BASE.format(mail_id=mail_id)
    return f"{_MAILBOX_MSG_BASE.format(mail_id=mail_id)}.{priority.value}"


def _sub_subject(mail_id: str, priority: str) -> str:
    """Return the NATS subject for subscribing.

    "*" → wildcard subject, matches all priorities (normal, urgent, critical).
    "normal" → bare subject (no suffix).
    "urgent" / "critical" → subject with priority suffix.
    """
    if priority == "*":
        return f"{_MAILBOX_MSG_BASE.format(mail_id=mail_id)}.*"
    if Priority(priority) == Priority.NORMAL:
        return _MAILBOX_MSG_BASE.format(mail_id=mail_id)
    return f"{_MAILBOX_MSG_BASE.format(mail_id=mail_id)}.{priority}"


class Priority(str, Enum):
    CRITICAL = "critical"
    URGENT = "urgent"
    NORMAL = "normal"


@dataclass
class Mailbox:
    """Represents a created mq9 mailbox."""

    mail_id: str
    public: bool = False
    name: str = ""
    desc: str = ""


@dataclass
class MessageMeta:
    """Metadata for a message returned by list(). Does not include payload."""

    msg_id: str
    priority: Priority
    ts: int  # Unix timestamp of message creation

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "MessageMeta":
        return cls(
            msg_id=data["msg_id"],
            priority=Priority(data["priority"]),
            ts=data.get("ts", 0),
        )


@dataclass
class Message:
    """A message received via subscribe()."""

    msg_id: str
    mail_id: str
    priority: Priority
    payload: bytes


class Mq9Error(Exception):
    """Raised when the server returns an error response."""

    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(message)
        self.code = code


class Client:
    """
    mq9 client for RobustMQ.

    Usage::

        client = Client(server="nats://localhost:4222")
        await client.connect()

        mailbox = await client.create(ttl=3600)
        await client.send(mailbox.mail_id, b"hello", priority="high")

        async def handler(msg: Message) -> None:
            print(msg.payload)

        await client.subscribe(mailbox.mail_id, handler)
        await client.close()

    Reconnection is handled automatically by the underlying NATS client.
    """

    def __init__(
        self,
        server: str = "nats://localhost:4222",
        *,
        max_reconnect_attempts: int = 10,
        reconnect_time_wait: float = 2.0,
        request_timeout: float = _REQUEST_TIMEOUT,
        name: str = "robustmq-mq9-python",
    ) -> None:
        self._server = server
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_time_wait = reconnect_time_wait
        self._request_timeout = request_timeout
        self._name = name
        self._nc: NATSClient | None = None
        self._subscriptions: list[Subscription] = []

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish connection to the NATS server backing RobustMQ."""
        self._nc = await nats.connect(
            self._server,
            name=self._name,
            max_reconnect_attempts=self._max_reconnect_attempts,
            reconnect_time_wait=self._reconnect_time_wait,
            error_cb=self._on_error,
            reconnected_cb=self._on_reconnected,
            disconnected_cb=self._on_disconnected,
        )
        logger.info("mq9 client connected to %s", self._server)

    async def close(self) -> None:
        """Drain subscriptions and close the NATS connection."""
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
            logger.info("mq9 client closed")

    # ------------------------------------------------------------------
    # Mailbox operations
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        ttl: int,
        public: bool = False,
        name: str = "",
        desc: str = "",
    ) -> Mailbox:
        """
        Create a mailbox.

        Args:
            ttl: Mailbox lifetime in seconds.
            public: If True, mailbox is publicly discoverable.
            name: Human-readable name (required when public=True).
            desc: Description shown in public listing.

        Returns:
            Mailbox with the assigned mail_id.
        """
        payload: dict[str, Any] = {"ttl": ttl}
        if public:
            if not name:
                raise ValueError("name is required when public=True")
            payload["public"] = True
            payload["name"] = name
            if desc:
                payload["desc"] = desc

        resp = await self._request(_MAILBOX_CREATE, payload)
        mail_id = resp["mail_id"]
        return Mailbox(mail_id=mail_id, public=public, name=name, desc=desc)

    async def send(
        self,
        mail_id: str,
        payload: bytes | str | dict[str, Any],
        *,
        priority: Priority | str = Priority.NORMAL,
    ) -> None:
        """
        Send a message to a mailbox.

        Args:
            mail_id: Target mailbox identifier.
            payload: Message body. Strings are UTF-8 encoded; dicts are JSON-encoded.
            priority: Message priority — critical, urgent, or normal (default).
        """
        self._ensure_connected()
        priority = Priority(priority)
        subject = _msg_subject(mail_id, priority)
        data = _encode_payload(payload)
        await self._nc.publish(subject, data)  # type: ignore[union-attr]

    async def subscribe(
        self,
        mail_id: str,
        callback: Callable[[Message], Awaitable[None]],
        *,
        priority: Priority | str = "*",
        queue_group: str = "",
    ) -> Subscription:
        """
        Subscribe to messages from a mailbox.

        Args:
            mail_id: Mailbox to subscribe to.
            callback: Async callable invoked for each message.
            priority: Filter by priority, or "*" for all (default).
            queue_group: NATS queue group name for competitive consumption.

        Returns:
            The underlying NATS Subscription (call .unsubscribe() to cancel).
        """
        self._ensure_connected()

        p = priority if isinstance(priority, str) else priority.value
        subject = _sub_subject(mail_id, p)

        async def _handler(raw: Msg) -> None:
            try:
                msg = _parse_incoming(mail_id, raw)
                await callback(msg)
            except Exception:
                logger.exception("Unhandled exception in mq9 subscription callback")

        kwargs: dict[str, Any] = {"cb": _handler}
        if queue_group:
            kwargs["queue"] = queue_group

        sub = await self._nc.subscribe(subject, **kwargs)  # type: ignore[union-attr]
        self._subscriptions.append(sub)
        logger.debug("Subscribed to %s", subject)
        return sub

    async def list(self, mail_id: str) -> list[MessageMeta]:
        """
        Return a metadata snapshot of all non-expired messages in a mailbox.
        Does not include message payloads — subscribe to receive full messages.

        Args:
            mail_id: Mailbox to query.

        Returns:
            List of MessageMeta (msg_id, priority, ts).
        """
        subject = _MAILBOX_LIST.format(mail_id=mail_id)
        resp = await self._request(subject, {})
        return [MessageMeta._from_dict(m) for m in resp.get("messages", [])]

    async def delete(self, mail_id: str, msg_id: str) -> None:
        """
        Delete a message from a mailbox.

        Args:
            mail_id: Mailbox containing the message.
            msg_id: Message identifier to delete.
        """
        subject = _MAILBOX_DELETE.format(mail_id=mail_id, msg_id=msg_id)
        await self._request(subject, {})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        if self._nc is None or self._nc.is_closed:
            raise RuntimeError(
                "Client is not connected. Call await client.connect() first."
            )

    async def _request(self, subject: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_connected()
        data = json.dumps(payload).encode()
        try:
            reply = await self._nc.request(  # type: ignore[union-attr]
                subject, data, timeout=self._request_timeout
            )
        except nats.errors.NoRespondersError as exc:
            raise Mq9Error(f"No responders for subject: {subject}") from exc
        except asyncio.TimeoutError as exc:
            raise Mq9Error(f"Request timed out: {subject}") from exc

        resp = json.loads(reply.data)
        if "error" in resp:
            raise Mq9Error(resp["error"], code=resp.get("code", 0))
        return resp

    async def _on_error(self, exc: Exception) -> None:
        logger.error("mq9 NATS error: %s", exc)

    async def _on_reconnected(self) -> None:
        logger.info("mq9 client reconnected to %s", self._server)

    async def _on_disconnected(self) -> None:
        logger.warning("mq9 client disconnected from %s", self._server)

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "Client":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _encode_payload(payload: bytes | str | dict[str, Any]) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode()
    return json.dumps(payload).encode()


def _parse_incoming(mail_id: str, raw: Msg) -> Message:
    """
    Parse a raw NATS message arriving on a mq9 subscription subject.

    Subject format: $mq9.AI.MAILBOX.MSG.{mail_id}.{priority}
    The server may send a JSON envelope or raw bytes depending on version.
    We try JSON first and fall back to treating the full body as payload.
    """
    # Extract priority from subject.
    # Subject is $mq9.AI.MAILBOX.MSG.{mail_id} (normal, no suffix)
    # or $mq9.AI.MAILBOX.MSG.{mail_id}.{urgent|critical}
    # We strip the fixed prefix to find whether a priority suffix is present.
    _msg_prefix = f"$mq9.AI.MAILBOX.MSG.{mail_id}"
    suffix = raw.subject[len(_msg_prefix):]  # "" or ".urgent" or ".critical"
    priority_str = suffix.lstrip(".")
    try:
        priority = Priority(priority_str) if priority_str else Priority.NORMAL
    except ValueError:
        priority = Priority.NORMAL

    # Try to unwrap JSON envelope sent by server
    try:
        envelope = json.loads(raw.data)
        if isinstance(envelope, dict) and "msg_id" in envelope:
            return Message(
                msg_id=envelope["msg_id"],
                mail_id=mail_id,
                priority=priority,
                payload=(
                    base64.b64decode(envelope["payload"])
                    if envelope.get("payload")
                    else raw.data
                ),
            )
    except (json.JSONDecodeError, KeyError):
        pass

    # No envelope — treat raw data as payload
    return Message(
        msg_id="",
        mail_id=mail_id,
        priority=priority,
        payload=raw.data,
    )
