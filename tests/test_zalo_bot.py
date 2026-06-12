import unittest

import httpx
from starlette.applications import Starlette
from starlette.routing import Route

from integrations.zalo_bot import (
    ZaloBotClient,
    ZaloBotApiError,
    ZaloWebhookHandler,
    extract_text_message,
    split_message,
)


def make_text_payload(text="Tim ve tu Ha Noi di Da Nang"):
    return {
        "ok": True,
        "result": {
            "event_name": "message.text.received",
            "message": {
                "from": {
                    "id": "user-123",
                    "display_name": "Ted",
                    "is_bot": False,
                },
                "chat": {
                    "id": "chat-456",
                    "chat_type": "PRIVATE",
                },
                "text": text,
                "message_id": "message-789",
                "date": 1750316131602,
            },
        },
    }


class FakeBotClient:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))


class ZaloPayloadTest(unittest.TestCase):
    def test_extracts_text_message(self):
        message = extract_text_message(make_text_payload("Xin chao"))

        self.assertEqual(message.chat_id, "chat-456")
        self.assertEqual(message.sender_id, "user-123")
        self.assertEqual(message.message_id, "message-789")
        self.assertEqual(message.text, "Xin chao")

    def test_extracts_unwrapped_text_message(self):
        payload = make_text_payload("Xin chao truc tiep")["result"]

        message = extract_text_message(payload)

        self.assertEqual(message.chat_id, "chat-456")
        self.assertEqual(message.sender_id, "user-123")
        self.assertEqual(message.message_id, "message-789")
        self.assertEqual(message.text, "Xin chao truc tiep")

    def test_ignores_non_text_event(self):
        payload = make_text_payload()
        payload["result"]["event_name"] = "message.image.received"

        self.assertIsNone(extract_text_message(payload))

    def test_rejects_null_required_fields(self):
        payload = make_text_payload()
        payload["result"]["message"]["text"] = None

        with self.assertRaises(ValueError):
            extract_text_message(payload)

    def test_splits_long_message_within_zalo_limit(self):
        text = ("A" * 1200) + "\n\n" + ("B" * 1200)

        chunks = split_message(text)

        self.assertEqual("".join(chunks), ("A" * 1200) + ("B" * 1200))
        self.assertTrue(all(len(chunk) <= 2000 for chunk in chunks))


class ZaloWebhookHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent_calls = []
        self.bot_client = FakeBotClient()

        def agent_runner(message, user_id, session_id):
            self.agent_calls.append((message, user_id, session_id))
            return "Ket qua phu hop"

        handler = ZaloWebhookHandler(
            secret_token="secret-token",
            agent_runner=agent_runner,
            bot_client=self.bot_client,
        )
        app = Starlette(
            routes=[Route("/webhooks/zalo", handler.handle, methods=["POST"])]
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_rejects_invalid_secret(self):
        with self.assertLogs("integrations.zalo_bot", level="WARNING") as logs:
            response = await self.client.post(
                "/webhooks/zalo",
                headers={"X-Bot-Api-Secret-Token": "wrong-token"},
                json=make_text_payload(),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.agent_calls, [])
        self.assertEqual(self.bot_client.messages, [])
        self.assertIn("secret token mismatch", "\n".join(logs.output))

    async def test_dispatches_text_message_and_replies_to_chat(self):
        with self.assertLogs("integrations.zalo_bot", level="INFO") as logs:
            response = await self.client.post(
                "/webhooks/zalo",
                headers={"X-Bot-Api-Secret-Token": "secret-token"},
                json=make_text_payload(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.agent_calls,
            [
                (
                    "Tim ve tu Ha Noi di Da Nang",
                    "zalo:user-123",
                    "zalo:chat-456",
                )
            ],
        )
        self.assertEqual(
            self.bot_client.messages,
            [("chat-456", "Ket qua phu hop")],
        )
        log_output = "\n".join(logs.output)
        self.assertIn("Zalo webhook accepted message_id=message-789", log_output)
        self.assertIn("Processing Zalo message message_id=message-789", log_output)
        self.assertIn(
            "Sent Zalo reply message_id=message-789 chunk=1/1",
            log_output,
        )

    async def test_dispatches_unwrapped_text_message(self):
        payload = make_text_payload("Tin nhan khong boc result")["result"]

        response = await self.client.post(
            "/webhooks/zalo",
            headers={"X-Bot-Api-Secret-Token": "secret-token"},
            json=payload,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.agent_calls,
            [
                (
                    "Tin nhan khong boc result",
                    "zalo:user-123",
                    "zalo:chat-456",
                )
            ],
        )
        self.assertEqual(
            self.bot_client.messages,
            [("chat-456", "Ket qua phu hop")],
        )

    async def test_acknowledges_and_ignores_non_text_event(self):
        payload = make_text_payload()
        payload["result"]["event_name"] = "message.sticker.received"

        with self.assertLogs("integrations.zalo_bot", level="INFO") as logs:
            response = await self.client.post(
                "/webhooks/zalo",
                headers={"X-Bot-Api-Secret-Token": "secret-token"},
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ignored"])
        self.assertEqual(self.agent_calls, [])
        self.assertIn(
            "event_name=message.sticker.received",
            "\n".join(logs.output),
        )


class ZaloBotClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_uses_expected_endpoint_and_payload(self):
        requests = []

        async def handle_request(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {"message_id": "sent-123", "date": 1749632637199},
                },
            )

        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request)
        )
        self.addAsyncCleanup(http_client.aclose)
        client = ZaloBotClient(
            "123456:abc-xyz",
            parse_mode="markdown",
            http_client=http_client,
        )

        await client.send_message("chat-456", "**Xin chao**")

        self.assertEqual(
            str(requests[0].url),
            "https://bot-api.zaloplatforms.com/bot123456:abc-xyz/sendMessage",
        )
        self.assertEqual(
            requests[0].read(),
            b'{"chat_id":"chat-456","text":"**Xin chao**","parse_mode":"markdown"}',
        )

    async def test_sanitizes_network_errors_that_could_expose_bot_token(self):
        async def handle_request(request):
            raise httpx.ConnectError("failed", request=request)

        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request)
        )
        self.addAsyncCleanup(http_client.aclose)
        client = ZaloBotClient(
            "secret-bot-token",
            http_client=http_client,
        )

        with self.assertRaisesRegex(ZaloBotApiError, "network error") as raised:
            await client.send_message("chat-456", "Xin chao")

        self.assertNotIn("secret-bot-token", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
