import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import discord
from src.discord_client import Account, BlockSettings, DiscordManager, MatchType, Rule


class FakeClient:
    active_startups = 0
    max_active_startups = 0
    stop_calls = 0

    def __init__(self, account, rules, log_callback=None, discord_manager=None):
        self.account = account
        self.rules = rules
        self.log_callback = log_callback
        self.discord_manager = discord_manager
        self.is_running = False
        self._startup_complete = asyncio.Event()
        self._stopped = asyncio.Event()

    async def start_client(self):
        type(self).active_startups += 1
        type(self).max_active_startups = max(type(self).max_active_startups, type(self).active_startups)

        await asyncio.sleep(0.01)
        self.is_running = True
        self._startup_complete.set()
        type(self).active_startups -= 1

        await self._stopped.wait()
        self.is_running = False

    async def wait_for_startup(self, timeout):
        await asyncio.wait_for(self._startup_complete.wait(), timeout)
        return self.is_running

    async def stop_client(self):
        type(self).stop_calls += 1
        self._stopped.set()

    @classmethod
    def reset(cls):
        cls.active_startups = 0
        cls.max_active_startups = 0
        cls.stop_calls = 0


class FakeMessageSender:
    def __init__(self, side_effects=None, delay=0.0):
        self.side_effects = list(side_effects or [])
        self.sent_messages = []
        self.delay = delay

    async def send(self, content=None, **kwargs):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.sent_messages.append({"content": content, "kwargs": kwargs})

        if self.side_effects:
            effect = self.side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect

        return object()


class FakeThreadChannel:
    def __init__(self, thread_id, archived=False, locked=False):
        self.id = thread_id
        self.archived = archived
        self.locked = locked
        self.join_call_count = 0
        self.edit_calls = []

    async def join(self):
        self.join_call_count += 1

    async def edit(self, **kwargs):
        self.edit_calls.append(kwargs)
        if "archived" in kwargs:
            self.archived = kwargs["archived"]
        if "locked" in kwargs:
            self.locked = kwargs["locked"]
        return self


class FakeRotationClient:
    def __init__(self, account, sender=None):
        self.account = account
        self.sender = sender or FakeMessageSender()
        self.requests = []

    def get_partial_messageable(self, channel_id, **kwargs):
        self.requests.append({"channel_id": channel_id, "kwargs": kwargs})
        return self.sender


class FakeMessage:
    def __init__(
        self,
        channel_id=123,
        guild_id=456,
        message_id=789,
        author_id=321,
        author_name="Alice",
        thread=None,
        fetch_thread_result=None,
        create_thread_result=None,
    ):
        self.id = message_id
        self.channel = SimpleNamespace(id=channel_id, name="general")
        self.guild = SimpleNamespace(id=guild_id)
        self.author = SimpleNamespace(id=author_id, name=author_name)
        self.thread = thread
        self.fetch_thread_result = fetch_thread_result
        self.create_thread_result = create_thread_result
        self.reply_calls = []
        self.reference_calls = []
        self.fetch_thread_calls = 0
        self.create_thread_calls = []

    def to_reference(self, **kwargs):
        self.reference_calls.append(kwargs)
        return {"message_id": self.id, **kwargs}

    async def reply(self, content=None, **kwargs):
        self.reply_calls.append({"content": content, "kwargs": kwargs})
        return object()

    async def fetch_thread(self):
        self.fetch_thread_calls += 1
        if isinstance(self.fetch_thread_result, Exception):
            raise self.fetch_thread_result
        if self.fetch_thread_result is None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "missing thread")
        self.thread = self.fetch_thread_result
        return self.fetch_thread_result

    async def create_thread(self, **kwargs):
        self.create_thread_calls.append(kwargs)
        if isinstance(self.create_thread_result, Exception):
            raise self.create_thread_result
        if self.create_thread_result is None:
            self.create_thread_result = FakeThreadChannel(thread_id=self.id)
        self.thread = self.create_thread_result
        return self.create_thread_result


def build_http_exception(code, message="request failed"):
    response = SimpleNamespace(status=429, reason="Too Many Requests")
    payload = {"code": code, "message": message}
    return discord.HTTPException(response, payload)


class DiscordManagerStartupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeClient.reset()
        self.manager = DiscordManager()
        self.manager.max_parallel_starts = 3
        self.manager.startup_timeout = 0.5
        self.manager.accounts = [
            Account(
                token=f"token-{index}",
                is_active=True,
                is_valid=True,
                user_info={"name": f"user-{index}", "discriminator": "0000"},
            )
            for index in range(7)
        ]

    async def asyncTearDown(self):
        await self.manager.stop_all_clients()

    async def test_start_all_clients_limits_parallel_startups_and_marks_running(self):
        with patch("src.discord_client.AutoReplyClient", FakeClient):
            await self.manager.start_all_clients()

        self.assertTrue(self.manager.is_running)
        self.assertEqual(len(self.manager.client_tasks), len(self.manager.accounts))
        self.assertLessEqual(FakeClient.max_active_startups, self.manager.max_parallel_starts)

    async def test_start_all_clients_treats_empty_rule_ids_as_all_rules(self):
        self.manager.accounts = [
            Account(
                token="token-1",
                is_active=True,
                is_valid=True,
                user_info={"name": "user-1", "discriminator": "0000"},
                rule_ids=[],
            )
        ]
        self.manager.rules = [
            Rule(
                id="rule-1",
                keywords=["123"],
                reply="r1",
                match_type=MatchType.PARTIAL,
                target_channels=[],
            ),
            Rule(
                id="rule-2",
                keywords=["abc"],
                reply="r2",
                match_type=MatchType.EXACT,
                target_channels=[],
            ),
        ]

        with patch("src.discord_client.AutoReplyClient", FakeClient):
            await self.manager.start_all_clients()

        self.assertEqual(len(self.manager.clients), 1)
        self.assertEqual([rule.id for rule in self.manager.clients[0].rules], ["rule-1", "rule-2"])

    async def test_get_message_rule_matches_reuses_cached_result_for_same_message(self):
        self.manager.rules = [
            Rule(
                id="rule-1",
                keywords=["hello"],
                reply="world",
                match_type=MatchType.PARTIAL,
                target_channels=[],
            )
        ]
        message = FakeMessage(message_id=9001)
        message.content = "hello there"

        first_result = self.manager.get_message_rule_matches(message, message.content)

        with patch.object(
            self.manager.rule_matcher,
            "match_content",
            side_effect=AssertionError("should reuse cached result"),
        ):
            second_result = self.manager.get_message_rule_matches(message, message.content)

        self.assertEqual(first_result, {"rule-1": "hello"})
        self.assertEqual(second_result, {"rule-1": "hello"})

    async def test_stop_all_clients_clears_tracked_tasks(self):
        with patch("src.discord_client.AutoReplyClient", FakeClient):
            await self.manager.start_all_clients()
            await self.manager.stop_all_clients()

        self.assertFalse(self.manager.is_running)
        self.assertEqual(self.manager.client_tasks, {})
        self.assertEqual(self.manager.clients, [])
        self.assertEqual(FakeClient.stop_calls, len(self.manager.accounts))

    async def test_rotation_only_uses_accounts_allowed_for_channel(self):
        self.manager.rotation_enabled = True
        self.manager.accounts = [
            Account(
                token="token-1",
                is_active=True,
                is_valid=True,
                target_channels=[111],
            ),
            Account(
                token="token-2",
                is_active=True,
                is_valid=True,
                target_channels=[222],
            ),
        ]

        selected_account = self.manager.get_next_available_account(channel_id=222)

        self.assertIsNotNone(selected_account)
        self.assertEqual(selected_account.token, "token-2")

    async def test_send_rotated_reply_uses_selected_client_context(self):
        self.manager.rotation_enabled = True
        self.manager.accounts = [
            Account(token="token-1", is_active=True, is_valid=True),
            Account(token="token-2", is_active=True, is_valid=True),
        ]
        self.manager.current_rotation_index = 1

        client_one = FakeRotationClient(self.manager.accounts[0])
        client_two = FakeRotationClient(self.manager.accounts[1])
        self.manager.clients = [client_one, client_two]

        message = FakeMessage(channel_id=222, guild_id=333, message_id=999)

        success = await self.manager.send_rotated_reply(message, "hello world")

        self.assertTrue(success)
        self.assertEqual(message.reply_calls, [])
        self.assertEqual(client_one.sender.sent_messages, [])
        self.assertEqual(len(client_two.sender.sent_messages), 1)
        self.assertEqual(message.create_thread_calls, [])
        self.assertEqual(client_two.requests[0]["channel_id"], 222)
        self.assertEqual(client_two.sender.sent_messages[0]["content"], "hello world")
        self.assertEqual(
            client_two.sender.sent_messages[0]["kwargs"]["reference"],
            {"message_id": 999, "fail_if_not_exists": False},
        )
        self.assertFalse(client_two.sender.sent_messages[0]["kwargs"]["mention_author"])
        self.assertIn(999, self.manager.replied_messages)

    async def test_send_rule_replies_creates_thread_and_sends_all_accounts_inside_it(self):
        self.manager.reply_in_thread_mode = True
        primary_account = Account(token="token-1", is_active=True, is_valid=True)
        secondary_account = Account(token="token-2", is_active=True, is_valid=True)
        self.manager.accounts = [primary_account, secondary_account]

        primary_sender = FakeMessageSender()
        secondary_sender = FakeMessageSender()
        primary_client = FakeRotationClient(primary_account, sender=primary_sender)
        secondary_client = FakeRotationClient(secondary_account, sender=secondary_sender)
        self.manager.clients = [primary_client, secondary_client]

        rule = Rule(
            id="rule-1",
            keywords=["hello"],
            reply="inside thread",
            match_type=MatchType.PARTIAL,
            target_channels=[],
            reply_account_count=2,
        )
        message = FakeMessage(
            channel_id=222,
            guild_id=333,
            message_id=1010,
            create_thread_result=FakeThreadChannel(thread_id=9010),
        )

        success_count = await self.manager.send_rule_replies(
            message,
            rule,
            matched_keyword="hello",
            preferred_account=primary_account,
            preferred_client=primary_client,
        )

        self.assertEqual(success_count, 2)
        self.assertEqual(message.reply_calls, [])
        self.assertEqual(len(message.create_thread_calls), 1)
        self.assertEqual(message.create_thread_calls[0]["name"], "回复-Alice-1010")
        self.assertEqual(primary_client.requests[0]["channel_id"], 9010)
        self.assertEqual(secondary_client.requests[0]["channel_id"], 9010)
        self.assertEqual(primary_sender.sent_messages[0]["content"], "inside thread")
        self.assertEqual(secondary_sender.sent_messages[0]["content"], "inside thread")
        self.assertNotIn("reference", primary_sender.sent_messages[0]["kwargs"])
        self.assertNotIn("reference", secondary_sender.sent_messages[0]["kwargs"])

    async def test_send_rotated_reply_reuses_existing_thread(self):
        self.manager.rotation_enabled = True
        self.manager.reply_in_thread_mode = True
        self.manager.accounts = [
            Account(token="token-1", is_active=True, is_valid=True),
        ]

        sender = FakeMessageSender()
        client = FakeRotationClient(self.manager.accounts[0], sender=sender)
        self.manager.clients = [client]
        existing_thread = FakeThreadChannel(thread_id=8001)
        message = FakeMessage(
            channel_id=222,
            guild_id=333,
            message_id=1000,
            thread=existing_thread,
        )

        success = await self.manager.send_rotated_reply(message, "reply in existing thread")

        self.assertTrue(success)
        self.assertEqual(message.create_thread_calls, [])
        self.assertEqual(client.requests[0]["channel_id"], 8001)
        self.assertEqual(sender.sent_messages[0]["content"], "reply in existing thread")
        self.assertNotIn("reference", sender.sent_messages[0]["kwargs"])

    async def test_send_rotated_reply_waits_for_random_global_delay(self):
        self.manager.rotation_enabled = True
        self.manager.block_settings = BlockSettings(
            reply_delay_min=1.0,
            reply_delay_max=4.0,
        )
        self.manager.accounts = [
            Account(token="token-1", is_active=True, is_valid=True),
        ]
        sender = FakeMessageSender()
        self.manager.clients = [
            FakeRotationClient(self.manager.accounts[0], sender=sender),
        ]
        message = FakeMessage(channel_id=222, guild_id=333, message_id=1005)

        sleep_mock = AsyncMock()
        with patch("src.discord_client.random.uniform", return_value=2.5), patch(
            "src.discord_client.asyncio.sleep",
            new=sleep_mock,
        ):
            success = await self.manager.send_rotated_reply(message, "delayed reply")

        self.assertTrue(success)
        sleep_mock.assert_awaited_once_with(2.5)
        self.assertEqual(sender.sent_messages[0]["content"], "delayed reply")

    async def test_send_rule_replies_uses_normal_reply_when_thread_mode_disabled(self):
        primary_account = Account(token="token-1", is_active=True, is_valid=True)
        secondary_account = Account(token="token-2", is_active=True, is_valid=True)
        self.manager.accounts = [primary_account, secondary_account]

        secondary_sender = FakeMessageSender()
        primary_client = FakeRotationClient(primary_account)
        secondary_client = FakeRotationClient(secondary_account, sender=secondary_sender)
        self.manager.clients = [primary_client, secondary_client]

        rule = Rule(
            id="rule-1",
            keywords=["hello"],
            reply="normal reply",
            match_type=MatchType.PARTIAL,
            target_channels=[],
            reply_account_count=2,
        )
        message = FakeMessage(channel_id=222, guild_id=333, message_id=1011)

        success_count = await self.manager.send_rule_replies(
            message,
            rule,
            matched_keyword="hello",
            preferred_account=primary_account,
            preferred_client=primary_client,
        )

        self.assertEqual(success_count, 2)
        self.assertEqual(message.create_thread_calls, [])
        self.assertEqual(len(message.reply_calls), 1)
        self.assertEqual(message.reply_calls[0]["content"], "normal reply")
        self.assertEqual(len(secondary_sender.sent_messages), 1)
        self.assertEqual(secondary_client.requests[0]["channel_id"], 222)
        self.assertEqual(
            secondary_sender.sent_messages[0]["kwargs"]["reference"],
            {"message_id": 1011, "fail_if_not_exists": False},
        )

    async def test_send_rotated_reply_tries_next_account_after_slowmode(self):
        self.manager.rotation_enabled = True
        self.manager.accounts = [
            Account(token="token-1", is_active=True, is_valid=True),
            Account(token="token-2", is_active=True, is_valid=True),
        ]
        self.manager.current_rotation_index = 0

        slowmode_sender = FakeMessageSender(
            side_effects=[build_http_exception(20016, "slowmode")]
        )
        fallback_sender = FakeMessageSender()
        self.manager.clients = [
            FakeRotationClient(self.manager.accounts[0], sender=slowmode_sender),
            FakeRotationClient(self.manager.accounts[1], sender=fallback_sender),
        ]

        message = FakeMessage(channel_id=222, guild_id=333, message_id=1001)

        success = await self.manager.send_rotated_reply(message, "fallback reply")

        self.assertTrue(success)
        self.assertIsNotNone(self.manager.accounts[0].rate_limit_until)
        self.assertEqual(len(fallback_sender.sent_messages), 1)
        self.assertEqual(fallback_sender.sent_messages[0]["content"], "fallback reply")
        self.assertIn(1001, self.manager.replied_messages)
        self.assertEqual(message.reply_calls, [])

    async def test_rotation_puts_account_into_cooldown_and_reuses_after_expiry(self):
        self.manager.rotation_enabled = True
        self.manager.rotation_interval = 10
        self.manager.accounts = [
            Account(token="token-1", is_active=True, is_valid=True),
            Account(token="token-2", is_active=True, is_valid=True),
        ]
        sender_one = FakeMessageSender()
        sender_two = FakeMessageSender()
        self.manager.clients = [
            FakeRotationClient(self.manager.accounts[0], sender=sender_one),
            FakeRotationClient(self.manager.accounts[1], sender=sender_two),
        ]

        with patch("src.discord_client.time.time", return_value=100.0):
            first_success = await self.manager.send_rotated_reply(FakeMessage(message_id=2001), "first")

        with patch("src.discord_client.time.time", return_value=101.0):
            second_success = await self.manager.send_rotated_reply(FakeMessage(message_id=2002), "second")

        with patch("src.discord_client.time.time", return_value=105.0):
            third_success = await self.manager.send_rotated_reply(FakeMessage(message_id=2003), "third")

        with patch("src.discord_client.time.time", return_value=112.0):
            fourth_success = await self.manager.send_rotated_reply(FakeMessage(message_id=2004), "fourth")

        self.assertTrue(first_success)
        self.assertTrue(second_success)
        self.assertFalse(third_success)
        self.assertTrue(fourth_success)
        self.assertEqual([item["content"] for item in sender_one.sent_messages], ["first", "fourth"])
        self.assertEqual([item["content"] for item in sender_two.sent_messages], ["second"])
        self.assertEqual(self.manager.accounts[0].cooldown_until, 122.0)
        self.assertEqual(self.manager.accounts[1].cooldown_until, 111.0)

    async def test_concurrent_rotation_attempts_only_send_once_per_message(self):
        self.manager.rotation_enabled = True
        self.manager.accounts = [
            Account(token="token-1", is_active=True, is_valid=True),
            Account(token="token-2", is_active=True, is_valid=True),
        ]
        shared_message = FakeMessage(message_id=3001)
        sender_one = FakeMessageSender(delay=0.01)
        sender_two = FakeMessageSender(delay=0.01)
        self.manager.clients = [
            FakeRotationClient(self.manager.accounts[0], sender=sender_one),
            FakeRotationClient(self.manager.accounts[1], sender=sender_two),
        ]

        results = await asyncio.gather(
            self.manager.send_rotated_reply(shared_message, "once only"),
            self.manager.send_rotated_reply(shared_message, "once only"),
        )

        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 1)
        total_sent = len(sender_one.sent_messages) + len(sender_two.sent_messages)
        self.assertEqual(total_sent, 1)
        self.assertIn(3001, self.manager.replied_messages)

    async def test_send_rotated_reply_logs_only_sender_and_target(self):
        self.manager.rotation_enabled = True
        self.manager.accounts = [
            Account(
                token="token-1",
                is_active=True,
                is_valid=True,
                user_info={"name": "sender", "discriminator": "0001"},
            ),
        ]
        sender = FakeMessageSender()
        self.manager.clients = [
            FakeRotationClient(self.manager.accounts[0], sender=sender),
        ]
        logs = []
        self.manager.log_callback = logs.append

        success = await self.manager.send_rotated_reply(
            FakeMessage(message_id=4001, author_name="Bob"),
            "hello Bob",
        )

        self.assertTrue(success)
        self.assertEqual(logs, ["sender#0001 回复了 Bob"])

    def test_get_status_reports_cooldown_remaining_seconds(self):
        self.manager.accounts = [
            Account(token="token-1", is_active=True, is_valid=True, cooldown_until=108.0),
            Account(token="token-2", is_active=True, is_valid=True, cooldown_until=95.0),
        ]

        with patch("src.discord_client.time.time", return_value=100.0):
            status = self.manager.get_status()

        self.assertEqual(status["accounts"][0]["cooldown_remaining_seconds"], 8)
        self.assertEqual(status["accounts"][1]["cooldown_remaining_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
