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
        self.typing_call_count = 0

    def typing(self):
        self.typing_call_count += 1
        return FakeTypingContext()


class FakeOutboundChannel:
    def __init__(self):
        self.send_calls = []

    async def send(self, content=None, **kwargs):
        self.send_calls.append({"content": content, "kwargs": kwargs})
        return object()


class FakeSecondaryClient:
    def __init__(self, account):
        self.account = account
        self.channel = FakeOutboundChannel()

    def get_partial_messageable(self, channel_id, guild_id=None):
        return self.channel


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
        self.manager.accounts = [self.account]
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

    async def test_replies_immediately_without_sleep_or_typing(self):
        message = FakeInboundMessage(content="hello there", author_name="Alice")

        sleep_mock = AsyncMock()
        with patch("src.discord_client.asyncio.sleep", new=sleep_mock):
            await self.client.on_message(message)

        sleep_mock.assert_not_awaited()
        self.assertEqual(message.channel.typing_call_count, 0)

    async def test_reply_updates_reply_count_and_recent_history(self):
        message = FakeInboundMessage(content="hello there", author_name="Alice", channel_id=123, message_id=1001)

        with patch("src.discord_client.asyncio.sleep", new=AsyncMock()):
            await self.client.on_message(message)

        status = self.manager.get_status()
        self.assertEqual(status["accounts"][0]["reply_count"], 1)
        self.assertEqual(len(status["recent_replies"]), 1)
        self.assertEqual(status["recent_replies"][0]["account_alias"], "sender#0001")
        self.assertEqual(status["recent_replies"][0]["keyword"], "hello")
        self.assertEqual(status["recent_replies"][0]["customer_message"], "hello there")
        self.assertEqual(
            status["recent_replies"][0]["message_link"],
            "https://discord.com/channels/456/123/1001",
        )
        self.assertEqual(status["recent_replies"][0]["reply_content"], "hi there")

    async def test_partial_match_requires_whole_keyword_boundaries(self):
        self.rule.keywords = ["123", "1235"]
        self.rule.match_type = MatchType.PARTIAL
        message = FakeInboundMessage(content="1234 567", author_name="Alice")

        await self.client.on_message(message)

        self.assertEqual(len(message.reply_calls), 0)

    async def test_partial_match_uses_whole_phrase_not_inner_substring(self):
        self.rule.keywords = ["ric", "Eric Emmanuel Shorts"]
        self.rule.match_type = MatchType.PARTIAL
        message = FakeInboundMessage(content="Eric Emmanuel Shorts", author_name="Alice")

        await self.client.on_message(message)

        self.assertEqual(len(message.reply_calls), 1)
        self.assertEqual(message.reply_calls[0]["content"], "hi there")
        status = self.manager.get_status()
        self.assertEqual(status["recent_replies"][0]["keyword"], "Eric Emmanuel Shorts")

    async def test_exact_match_ignores_surrounding_whitespace(self):
        self.rule.keywords = ["exact value"]
        self.rule.match_type = MatchType.EXACT
        message = FakeInboundMessage(content="  exact value  ", author_name="Alice")

        await self.client.on_message(message)

        self.assertEqual(len(message.reply_calls), 1)
        self.assertEqual(message.reply_calls[0]["content"], "hi there")

    async def test_matching_is_case_insensitive_even_if_rule_requests_sensitive(self):
        self.rule.keywords = ["Shorts"]
        self.rule.match_type = MatchType.PARTIAL
        self.rule.case_sensitive = True
        message = FakeInboundMessage(content="shorts", author_name="Alice")

        await self.client.on_message(message)

        self.assertEqual(len(message.reply_calls), 1)
        self.assertEqual(message.reply_calls[0]["content"], "hi there")

    async def test_rule_can_request_two_accounts_to_reply(self):
        secondary_account = Account(
            token="token-2",
            is_active=True,
            is_valid=True,
            user_info={"name": "backup", "discriminator": "0002"},
        )
        secondary_client = FakeSecondaryClient(secondary_account)
        self.manager.accounts = [self.account, secondary_account]
        self.manager.clients = [self.client, secondary_client]
        self.rule.reply_account_count = 2

        message = FakeInboundMessage(content="hello there", author_name="Alice", channel_id=123, message_id=1002)

        with patch("src.discord_client.asyncio.sleep", new=AsyncMock()):
            await self.client.on_message(message)

        self.assertEqual(len(message.reply_calls), 1)
        self.assertEqual(len(secondary_client.channel.send_calls), 1)
        self.assertEqual(secondary_client.channel.send_calls[0]["content"], "hi there")


if __name__ == "__main__":
    unittest.main()
