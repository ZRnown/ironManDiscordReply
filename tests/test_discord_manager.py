import asyncio
import unittest
from unittest.mock import patch

from src.discord_client import Account, DiscordManager


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

    async def test_stop_all_clients_clears_tracked_tasks(self):
        with patch("src.discord_client.AutoReplyClient", FakeClient):
            await self.manager.start_all_clients()
            await self.manager.stop_all_clients()

        self.assertFalse(self.manager.is_running)
        self.assertEqual(self.manager.client_tasks, {})
        self.assertEqual(self.manager.clients, [])
        self.assertEqual(FakeClient.stop_calls, len(self.manager.accounts))


if __name__ == "__main__":
    unittest.main()
