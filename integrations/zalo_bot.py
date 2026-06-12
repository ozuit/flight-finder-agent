"""Zalo Bot webhook and sendMessage integration."""

from __future__ import annotations

import asyncio
import hmac
import inspect
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

import httpx
from greennode_agentbase.core.logging import configure_logger
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse

ZALO_API_BASE_URL = "https://bot-api.zaloplatforms.com"
ZALO_TEXT_LIMIT = 2000

logger = logging.getLogger(__name__)
configure_logger(logger)

AgentRunner = Callable[[str, str, str], str | Awaitable[str]]


class ZaloBotApiError(RuntimeError):
    """Raised when the Zalo Bot API rejects a request."""


@dataclass(frozen=True)
class ZaloTextMessage:
    """A normalized text message received from a Zalo webhook."""

    chat_id: str
    sender_id: str
    message_id: str
    text: str


def extract_text_message(payload: object) -> Optional[ZaloTextMessage]:
    """Extract a text event, returning None for unsupported event types."""
    if not isinstance(payload, dict):
        raise ValueError("Webhook payload must be a JSON object.")

    wrapped_result = payload.get("result")
    if isinstance(wrapped_result, dict):
        result = wrapped_result
    elif isinstance(payload.get("event_name"), str):
        # Zalo currently delivers some webhook events without the documented
        # {"ok": true, "result": {...}} envelope.
        result = payload
    else:
        raise ValueError("Webhook payload is missing event data.")

    if result.get("event_name") != "message.text.received":
        return None

    message = result.get("message")
    if not isinstance(message, dict):
        raise ValueError("Text event is missing 'message'.")

    sender = message.get("from")
    chat = message.get("chat")
    if not isinstance(sender, dict) or not isinstance(chat, dict):
        raise ValueError("Text event is missing sender or chat information.")

    sender_id = sender.get("id")
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    text = message.get("text")
    if not all(
        isinstance(value, str) for value in (sender_id, chat_id, message_id, text)
    ):
        raise ValueError("Text event required fields must be strings.")

    sender_id = sender_id.strip()
    chat_id = chat_id.strip()
    message_id = message_id.strip()
    text = text.strip()
    if not sender_id or not chat_id or not message_id or not text:
        raise ValueError("Text event contains empty required fields.")

    return ZaloTextMessage(
        chat_id=chat_id,
        sender_id=sender_id,
        message_id=message_id,
        text=text,
    )


def split_message(text: str, limit: int = ZALO_TEXT_LIMIT) -> list[str]:
    """Split long replies on natural boundaries without exceeding Zalo's limit."""
    text = text.strip()
    if not text:
        return []
    if limit <= 0:
        raise ValueError("Message limit must be positive.")

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        boundary = remaining.rfind("\n\n", 0, limit + 1)
        if boundary <= 0:
            boundary = remaining.rfind("\n", 0, limit + 1)
        if boundary <= 0:
            boundary = remaining.rfind(" ", 0, limit + 1)
        if boundary <= 0:
            boundary = limit

        chunk = remaining[:boundary].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[boundary:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks


class ZaloBotClient:
    """Small client for the Zalo Bot sendMessage API."""

    def __init__(
        self,
        bot_token: str,
        *,
        parse_mode: Optional[str] = "markdown",
        timeout_seconds: float = 15.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.bot_token = bot_token
        self.parse_mode = parse_mode
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    async def send_message(self, chat_id: str, text: str) -> None:
        payload = {"chat_id": chat_id, "text": text}
        if self.parse_mode:
            payload["parse_mode"] = self.parse_mode

        url = f"{ZALO_API_BASE_URL}/bot{self.bot_token}/sendMessage"
        try:
            if self.http_client is not None:
                response = await self.http_client.post(url, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(url, json=payload)
        except httpx.HTTPError:
            raise ZaloBotApiError(
                "Zalo sendMessage failed because of a network error."
            ) from None

        if response.status_code >= 400:
            raise ZaloBotApiError(
                f"Zalo sendMessage returned HTTP {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ZaloBotApiError("Zalo sendMessage returned invalid JSON.") from exc

        if not isinstance(data, dict):
            raise ZaloBotApiError("Zalo sendMessage returned an invalid response.")
        if data.get("ok") is not True:
            description = data.get("description") or "unknown API error"
            error_code = data.get("error_code")
            error_suffix = (
                f" (error_code={error_code})"
                if error_code is not None
                else ""
            )
            raise ZaloBotApiError(
                f"Zalo sendMessage failed: {description}{error_suffix}"
            )


class ZaloWebhookHandler:
    """Validate Zalo webhook requests and dispatch them to the flight agent."""

    def __init__(
        self,
        *,
        secret_token: str,
        agent_runner: AgentRunner,
        bot_client: Optional[ZaloBotClient],
    ) -> None:
        self.secret_token = secret_token
        self.agent_runner = agent_runner
        self.bot_client = bot_client

    async def handle(self, request: Request) -> JSONResponse:
        if not self.secret_token or self.bot_client is None:
            logger.error("Zalo webhook rejected: integration is not configured")
            return JSONResponse(
                {"ok": False, "message": "Zalo Bot integration is not configured."},
                status_code=503,
            )

        received_token = request.headers.get("X-Bot-Api-Secret-Token", "")
        if not received_token or not hmac.compare_digest(
            received_token, self.secret_token
        ):
            logger.warning("Zalo webhook rejected: secret token mismatch")
            return JSONResponse(
                {"ok": False, "message": "Unauthorized."},
                status_code=403,
            )

        payload: object = None
        try:
            payload = await request.json()
            message = extract_text_message(payload)
        except (ValueError, TypeError) as exc:
            payload_keys = (
                ",".join(sorted(str(key) for key in payload))
                if isinstance(payload, dict)
                else "not-an-object"
            )
            logger.warning(
                "Zalo webhook rejected: invalid payload (%s); top_level_keys=%s",
                exc,
                payload_keys,
            )
            return JSONResponse(
                {"ok": False, "message": "Invalid webhook payload."},
                status_code=400,
            )

        if message is None:
            event_name = None
            if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
                event_name = payload["result"].get("event_name")
            logger.info(
                "Zalo webhook ignored unsupported event event_name=%s",
                event_name or "unknown",
            )
            return JSONResponse({"ok": True, "ignored": True})

        logger.info(
            "Zalo webhook accepted message_id=%s",
            message.message_id,
        )
        return JSONResponse(
            {"ok": True},
            background=BackgroundTask(self._process_message, message),
        )

    async def _process_message(self, message: ZaloTextMessage) -> None:
        logger.info(
            "Processing Zalo message message_id=%s",
            message.message_id,
        )
        try:
            response_text = await self._run_agent(message)
        except Exception:
            logger.exception(
                "Flight agent failed for Zalo message_id=%s", message.message_id
            )
            response_text = (
                "Xin lỗi, hệ thống tìm vé đang gặp sự cố. "
                "Bạn vui lòng thử lại sau ít phút."
            )

        chunks = split_message(response_text)
        if not chunks:
            chunks = ["Xin lỗi, tôi chưa thể tạo câu trả lời. Bạn vui lòng thử lại."]

        for chunk_index, chunk in enumerate(chunks, 1):
            try:
                await self.bot_client.send_message(message.chat_id, chunk)
            except Exception:
                logger.exception(
                    "Could not send Zalo reply for message_id=%s",
                    message.message_id,
                )
                return
            logger.info(
                "Sent Zalo reply message_id=%s chunk=%d/%d",
                message.message_id,
                chunk_index,
                len(chunks),
            )

    async def _run_agent(self, message: ZaloTextMessage) -> str:
        user_id = f"zalo:{message.sender_id}"
        session_id = f"zalo:{message.chat_id}"
        if inspect.iscoroutinefunction(self.agent_runner):
            result = await self.agent_runner(message.text, user_id, session_id)
        else:
            result = await asyncio.to_thread(
                self.agent_runner,
                message.text,
                user_id,
                session_id,
            )
        return str(result)
