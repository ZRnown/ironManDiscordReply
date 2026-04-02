import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.discord_client import (
    Account,
    AutoReplyClient,
    BlockSettings,
    DiscordManager,
    MatchType,
    Rule,
)


class FakeTypingContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeInboundChannel:
    def __init__(self, channel_id=123, name="general"):
        self.id = channel_id
        self.name = name

    def typing(self):
        return FakeTypingContext()


class FakeInboundMessage:
    def __init__(
        self,
        content,
        author_id=123,
        author_name="Alice",
        channel_id=123,
        mentions=None,
        reference=None,
        message_id=1001,
    ):
        self.id = message_id
        self.content = content
        self.author = SimpleNamespace(id=author_id, name=author_name)
        self.channel = FakeInboundChannel(channel_id=channel_id)
        self.guild = SimpleNamespace(id=456)
        self.mentions = list(mentions or [])
        self.reference = reference
        self.reply_calls = []

    async def reply(self, content=None, **kwargs):
        self.reply_calls.append({"content": content, "kwargs": kwargs})
        return object()


class AutoReplyClientMessageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logs = []
        self.account = Account(
            token="token-1",
            is_active=True,
            is_valid=True,
            user_info={"name": "sender", "discriminator": "0001"},
        )
        self.rule = Rule(
            id="rule-1",
            keywords=["hello"],
            reply="hi there",
            match_type=MatchType.PARTIAL,
            target_channels=[],
        )
        self.manager = DiscordManager()
        self.manager.block_settings = BlockSettings()
        self.client = AutoReplyClient(
            self.account,
            [self.rule],
            log_callback=self.logs.append,
            discord_manager=self.manager,
        )
        self.client._connection.user = SimpleNamespace(id=999, name="self-user")

    async def asyncTearDown(self):
        await self.client.close()

    async def test_blocked_keywords_do_not_trigger_when_rule_does_not_match(self):
        self.manager.block_settings = BlockSettings(blocked_keywords=["http"])
        message = FakeInboundMessage(content="check http link")

        with patch("src.discord_client.random.uniform", return_value=0.0), patch(
            "src.discord_client.asyncio.sleep",
            new=AsyncMock(),
        ):
            await self.client.on_message(message)

        self.assertEqual(message.reply_calls, [])
        self.assertEqual(self.logs, [])

    async def test_blocked_keywords_skip_reply_silently_after_match(self):
        self.manager.block_settings = BlockSettings(blocked_keywords=["http"])
        message = FakeInboundMessage(content="hello http")

        with patch("src.discord_client.random.uniform", return_value=0.0), patch(
            "src.discord_client.asyncio.sleep",
            new=AsyncMock(),
        ):
            await self.client.on_message(message)

        self.assertEqual(message.reply_calls, [])
        self.assertEqual(self.logs, [])

    async def test_success_log_only_reports_who_replied_to_whom(self):
        message = FakeInboundMessage(content="hello there", author_name="Alice")

        with patch("src.discord_client.random.uniform", return_value=0.0), patch(
            "src.discord_client.asyncio.sleep",
            new=AsyncMock(),
        ):
            await self.client.on_message(message)

        self.assertEqual(len(message.reply_calls), 1)
        self.assertEqual(message.reply_calls[0]["content"], "hi there")
        self.assertEqual(self.logs, ["sender#0001 回复了 Alice"])

    async def test_block_settings_only_checked_inside_account_channels(self):
        self.account.target_channels = [999]
        message = FakeInboundMessage(content="hello http", channel_id=123)

        with patch("src.discord_client.random.uniform", return_value=0.0), patch(
            "src.discord_client.asyncio.sleep",
            new=AsyncMock(),
        ), patch.object(
            self.client,
            "_is_blocked_message",
            side_effect=AssertionError("should not check block settings outside target channels"),
        ):
            await self.client.on_message(message)

        self.assertEqual(message.reply_calls, [])


if __name__ == "__main__":
    unittest.main()
