"""Unit tests for the mq9 Python client.

All tests mock the underlying NATS connection so no live server is required.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from robustmq.mq9 import Client, Mailbox, Message, Priority
from robustmq.mq9.client import Mq9Error, _encode_payload, _parse_incoming


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_reply(data: dict[str, Any]) -> MagicMock:
    msg = MagicMock()
    msg.data = json.dumps(data).encode()
    return msg


def _make_error_reply(error: str, code: int = 400) -> MagicMock:
    return _make_reply({"error": error, "code": code})


def _make_client() -> Client:
    return Client(server="nats://localhost:4222")


async def _inject_nc(client: Client) -> AsyncMock:
    """Attach a mock NATS connection to a client."""
    nc = AsyncMock()
    nc.is_closed = False
    client._nc = nc
    return nc


# ---------------------------------------------------------------------------
# connect / close
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_and_close():
    client = _make_client()
    with patch("robustmq.mq9.client.nats.connect", new_callable=AsyncMock) as mock_connect:
        nc = AsyncMock()
        nc.is_closed = False
        mock_connect.return_value = nc

        await client.connect()
        assert client._nc is nc

        await client.close()
        nc.drain.assert_awaited_once()
        assert client._nc is None


@pytest.mark.asyncio
async def test_context_manager():
    client = _make_client()
    with patch("robustmq.mq9.client.nats.connect", new_callable=AsyncMock) as mock_connect:
        nc = AsyncMock()
        nc.is_closed = False
        mock_connect.return_value = nc

        async with client:
            assert client._nc is nc
        assert client._nc is None


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_private_mailbox():
    client = _make_client()
    nc = await _inject_nc(client)
    nc.request = AsyncMock(return_value=_make_reply({"mail_id": "m-abc-001"}))

    mailbox = await client.create(ttl=3600)

    assert isinstance(mailbox, Mailbox)
    assert mailbox.mail_id == "m-abc-001"
    assert mailbox.public is False

    nc.request.assert_awaited_once()
    subject, data, *_ = nc.request.call_args.args
    assert subject == "$mq9.AI.MAILBOX.CREATE"
    payload = json.loads(data)
    assert payload == {"ttl": 3600}


@pytest.mark.asyncio
async def test_create_public_mailbox():
    client = _make_client()
    nc = await _inject_nc(client)
    nc.request = AsyncMock(return_value=_make_reply({"mail_id": "task.queue"}))

    mailbox = await client.create(ttl=86400, public=True, name="task.queue", desc="Task queue")

    assert mailbox.mail_id == "task.queue"
    assert mailbox.public is True
    assert mailbox.name == "task.queue"

    _, data, *_ = nc.request.call_args.args
    payload = json.loads(data)
    assert payload["public"] is True
    assert payload["name"] == "task.queue"
    assert payload["desc"] == "Task queue"


@pytest.mark.asyncio
async def test_create_public_mailbox_requires_name():
    client = _make_client()
    await _inject_nc(client)

    with pytest.raises(ValueError, match="name is required"):
        await client.create(ttl=3600, public=True)


@pytest.mark.asyncio
async def test_create_server_error():
    client = _make_client()
    nc = await _inject_nc(client)
    nc.request = AsyncMock(return_value=_make_error_reply("quota exceeded", 429))

    with pytest.raises(Mq9Error) as exc_info:
        await client.create(ttl=3600)
    assert exc_info.value.code == 429
    assert "quota exceeded" in str(exc_info.value)


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_bytes_normal_priority():
    client = _make_client()
    nc = await _inject_nc(client)

    await client.send("m-001", b"hello", priority=Priority.NORMAL)

    nc.publish.assert_awaited_once_with(
        "$mq9.AI.MAILBOX.MSG.m-001.normal", b"hello"
    )


@pytest.mark.asyncio
async def test_send_string_payload():
    client = _make_client()
    nc = await _inject_nc(client)

    await client.send("m-001", "hello world")

    subject, data = nc.publish.call_args.args
    assert data == b"hello world"


@pytest.mark.asyncio
async def test_send_dict_payload():
    client = _make_client()
    nc = await _inject_nc(client)

    await client.send("m-001", {"task": "summarize"}, priority="high")

    subject, data = nc.publish.call_args.args
    assert subject == "$mq9.AI.MAILBOX.MSG.m-001.high"
    assert json.loads(data) == {"task": "summarize"}


@pytest.mark.asyncio
async def test_send_invalid_priority():
    client = _make_client()
    await _inject_nc(client)

    with pytest.raises(ValueError):
        await client.send("m-001", b"x", priority="urgent")


# ---------------------------------------------------------------------------
# subscribe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subscribe_all_priorities():
    client = _make_client()
    nc = await _inject_nc(client)
    nc.subscribe = AsyncMock(return_value=MagicMock())

    callback = AsyncMock()
    sub = await client.subscribe("m-001", callback)

    nc.subscribe.assert_awaited_once()
    subject = nc.subscribe.call_args.args[0]
    assert subject == "$mq9.AI.MAILBOX.MSG.m-001.*"
    assert sub is not None


@pytest.mark.asyncio
async def test_subscribe_single_priority():
    client = _make_client()
    nc = await _inject_nc(client)
    nc.subscribe = AsyncMock(return_value=MagicMock())

    await client.subscribe("m-001", AsyncMock(), priority="high")

    subject = nc.subscribe.call_args.args[0]
    assert subject == "$mq9.AI.MAILBOX.MSG.m-001.high"


@pytest.mark.asyncio
async def test_subscribe_queue_group():
    client = _make_client()
    nc = await _inject_nc(client)
    nc.subscribe = AsyncMock(return_value=MagicMock())

    await client.subscribe("task.queue", AsyncMock(), queue_group="workers")

    kwargs = nc.subscribe.call_args.kwargs
    assert kwargs.get("queue") == "workers"


@pytest.mark.asyncio
async def test_subscribe_callback_invoked():
    """Verify the internal NATS callback unpacks and forwards to user callback."""
    client = _make_client()
    nc = await _inject_nc(client)

    captured_cb = None

    async def fake_subscribe(subject, cb=None, queue=None):
        nonlocal captured_cb
        captured_cb = cb
        return MagicMock()

    nc.subscribe = fake_subscribe

    received: list[Message] = []

    async def handler(msg: Message) -> None:
        received.append(msg)

    await client.subscribe("m-001", handler, priority="normal")
    assert captured_cb is not None

    # Simulate server pushing a raw message
    raw = MagicMock()
    raw.subject = "$mq9.AI.MAILBOX.MSG.m-001.normal"
    raw.data = b'{"msg_id":"x1","priority":"normal","payload":"aGVsbG8="}'

    await captured_cb(raw)

    assert len(received) == 1
    assert received[0].msg_id == "x1"
    assert received[0].payload == b"hello"
    assert received[0].priority == Priority.NORMAL


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_messages():
    client = _make_client()
    nc = await _inject_nc(client)

    server_resp = {
        "mail_id": "m-001",
        "messages": [
            {"msg_id": "msg-1", "priority": "high", "ts": 1000},
        ],
    }
    nc.request = AsyncMock(return_value=_make_reply(server_resp))

    metas = await client.list("m-001")

    assert len(metas) == 1
    assert metas[0].msg_id == "msg-1"
    assert metas[0].priority == Priority.HIGH
    assert metas[0].ts == 1000

    subject = nc.request.call_args.args[0]
    assert subject == "$mq9.AI.MAILBOX.LIST.m-001"


@pytest.mark.asyncio
async def test_list_empty_mailbox():
    client = _make_client()
    nc = await _inject_nc(client)
    nc.request = AsyncMock(return_value=_make_reply({"mail_id": "m-001", "messages": []}))

    messages = await client.list("m-001")
    assert messages == []


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_message():
    client = _make_client()
    nc = await _inject_nc(client)
    nc.request = AsyncMock(return_value=_make_reply({"ok": True}))

    await client.delete("m-001", "msg-42")

    subject = nc.request.call_args.args[0]
    assert subject == "$mq9.AI.MAILBOX.DELETE.m-001.msg-42"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_timeout_raises_mq9_error():
    import nats.errors

    client = _make_client()
    nc = await _inject_nc(client)
    nc.request = AsyncMock(side_effect=asyncio.TimeoutError())

    with pytest.raises(Mq9Error, match="timed out"):
        await client.list("m-001")


@pytest.mark.asyncio
async def test_no_responders_raises_mq9_error():
    import nats.errors

    client = _make_client()
    nc = await _inject_nc(client)
    nc.request = AsyncMock(side_effect=nats.errors.NoRespondersError())

    with pytest.raises(Mq9Error, match="No responders"):
        await client.create(ttl=3600)


@pytest.mark.asyncio
async def test_not_connected_raises_runtime_error():
    client = _make_client()

    with pytest.raises(RuntimeError, match="not connected"):
        await client.send("m-001", b"hi")


# ---------------------------------------------------------------------------
# _encode_payload helper
# ---------------------------------------------------------------------------

def test_encode_bytes():
    assert _encode_payload(b"raw") == b"raw"


def test_encode_str():
    assert _encode_payload("hello") == b"hello"


def test_encode_dict():
    result = _encode_payload({"key": "val"})
    assert json.loads(result) == {"key": "val"}


# ---------------------------------------------------------------------------
# _parse_incoming helper
# ---------------------------------------------------------------------------

def test_parse_incoming_with_envelope():
    raw = MagicMock()
    raw.subject = "$mq9.AI.MAILBOX.MSG.m-001.high"
    raw.data = json.dumps({
        "msg_id": "x9",
        "priority": "high",
        "payload": base64.b64encode(b"data").decode(),
    }).encode()

    msg = _parse_incoming("m-001", raw)
    assert msg.msg_id == "x9"
    assert msg.priority == Priority.HIGH
    assert msg.payload == b"data"


def test_parse_incoming_raw_bytes():
    raw = MagicMock()
    raw.subject = "$mq9.AI.MAILBOX.MSG.m-001.low"
    raw.data = b"plain bytes"

    msg = _parse_incoming("m-001", raw)
    assert msg.payload == b"plain bytes"
    assert msg.priority == Priority.LOW
    assert msg.msg_id == ""


def test_parse_incoming_unknown_priority():
    raw = MagicMock()
    raw.subject = "$mq9.AI.MAILBOX.MSG.m-001.unknown"
    raw.data = b"data"

    msg = _parse_incoming("m-001", raw)
    assert msg.priority == Priority.NORMAL  # fallback
