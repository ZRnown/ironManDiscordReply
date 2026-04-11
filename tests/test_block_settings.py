import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.config_manager import ConfigManager, resolve_runtime_config_dir
from src.discord_client import Account, BlockSettings, MatchType, Rule


class BlockSettingsTests(unittest.TestCase):
    def test_blocks_keywords_for_all_accounts(self):
        settings = BlockSettings(
            blocked_keywords=["http", "discord.gg"],
            account_scope="all",
        )
        account = Account(token="token-1")

        self.assertTrue(settings.should_block_message(account, content="check http link", author_id="123"))

    def test_selected_account_scope_only_blocks_targeted_accounts(self):
        settings = BlockSettings(
            blocked_keywords=["spam"],
            account_scope="selected",
            account_tokens=["token-2"],
        )
        non_target_account = Account(token="token-1")
        target_account = Account(token="token-2")

        self.assertFalse(settings.should_block_message(non_target_account, content="spam here", author_id="123"))
        self.assertTrue(settings.should_block_message(target_account, content="spam here", author_id="123"))

    def test_blocks_user_ids(self):
        settings = BlockSettings(
            blocked_user_ids=["111", "222"],
            account_scope="all",
        )
        account = Account(token="token-1")

        self.assertTrue(settings.should_block_message(account, content="hello", author_id="222"))
        self.assertFalse(settings.should_block_message(account, content="hello", author_id="333"))

    def test_global_message_filters_default_to_ignoring_replies_and_mentions(self):
        settings = BlockSettings()

        self.assertTrue(settings.ignore_replies)
        self.assertTrue(settings.ignore_mentions)


class ConfigManagerBlockSettingsTests(unittest.TestCase):
    def test_saves_and_loads_block_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ConfigManager(config_dir=temp_dir)
            accounts = [Account(token="token-1", rule_ids=["rule-1"], target_channels=[123456])]
            rules = [
                Rule(
                    id="rule-1",
                    keywords=["hi"],
                    reply="hello",
                    match_type=MatchType.PARTIAL,
                    target_channels=[],
                    reply_account_count=3,
                )
            ]
            block_settings = BlockSettings(
                blocked_keywords=["http"],
                blocked_user_ids=["1001"],
                blocked_channel_ids=[123456],
                account_scope="selected",
                account_tokens=["token-1"],
                ignore_replies=False,
                ignore_mentions=False,
                case_sensitive=True,
            )

            self.assertTrue(manager.save_config(accounts, rules, block_settings))

            loaded_accounts, loaded_rules, loaded_block_settings = manager.load_config()

            self.assertEqual([account.token for account in loaded_accounts], ["token-1"])
            self.assertEqual(loaded_accounts[0].target_channels, [123456])
            self.assertEqual([rule.id for rule in loaded_rules], ["rule-1"])
            self.assertEqual(loaded_rules[0].reply_account_count, 3)
            self.assertEqual(loaded_block_settings.blocked_keywords, ["http"])
            self.assertEqual(loaded_block_settings.blocked_user_ids, ["1001"])
            self.assertEqual(loaded_block_settings.blocked_channel_ids, [123456])
            self.assertEqual(loaded_block_settings.account_scope, "selected")
            self.assertEqual(loaded_block_settings.account_tokens, ["token-1"])
            self.assertFalse(loaded_block_settings.ignore_replies)
            self.assertFalse(loaded_block_settings.ignore_mentions)
            self.assertFalse(loaded_block_settings.case_sensitive)

    def test_saves_and_loads_reply_thread_mode_setting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ConfigManager(config_dir=temp_dir)

            self.assertTrue(
                manager.save_config(
                    [],
                    [],
                    BlockSettings(),
                    reply_in_thread_mode=True,
                )
            )

            manager.load_config()

            self.assertTrue(manager.reply_in_thread_mode)

    def test_saves_and_loads_external_rule_sync_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ConfigManager(config_dir=temp_dir)

            self.assertTrue(
                manager.save_config(
                    [],
                    [],
                    BlockSettings(),
                    external_rule_sync_settings={
                        "enabled": True,
                        "file_path": "/tmp/follow.xlsx",
                        "interval_seconds": 120,
                    },
                )
            )

            manager.load_config()

            self.assertTrue(manager.external_rule_sync_settings["enabled"])
            self.assertEqual(manager.external_rule_sync_settings["file_path"], "/tmp/follow.xlsx")
            self.assertEqual(manager.external_rule_sync_settings["interval_seconds"], 120)

    def test_channel_scoped_block_only_applies_to_selected_channels(self):
        settings = BlockSettings(
            blocked_keywords=["spam"],
            blocked_channel_ids=[123],
            account_scope="all",
        )
        account = Account(token="token-1")

        self.assertTrue(settings.should_block_message(account, content="spam here", author_id="1", channel_id=123))
        self.assertFalse(settings.should_block_message(account, content="spam here", author_id="1", channel_id=456))

    def test_migrates_legacy_rule_exclude_keywords_into_block_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = f"{temp_dir}/config.json"
            payload = {
                "accounts": [{"token": "token-1", "rule_ids": ["rule-1"]}],
                "rules": [
                    {
                        "id": "rule-1",
                        "keywords": ["hi"],
                        "reply": "hello",
                        "match_type": "partial",
                        "target_channels": [],
                        "exclude_keywords": ["http", "discord.gg"],
                    }
                ],
            }
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)

            manager = ConfigManager(config_dir=temp_dir)
            _, loaded_rules, loaded_block_settings = manager.load_config()

            self.assertEqual(loaded_rules[0].exclude_keywords, [])
            self.assertEqual(loaded_block_settings.blocked_keywords, ["http", "discord.gg"])
            self.assertEqual(loaded_block_settings.account_scope, "all")

    def test_migrates_uniform_legacy_rule_filters_into_block_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = f"{temp_dir}/config.json"
            payload = {
                "accounts": [{"token": "token-1", "rule_ids": ["rule-1"]}],
                "rules": [
                    {
                        "id": "rule-1",
                        "keywords": ["hello"],
                        "reply": "world",
                        "match_type": "partial",
                        "ignore_replies": False,
                        "ignore_mentions": False,
                        "case_sensitive": True,
                    }
                ],
            }
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)

            manager = ConfigManager(config_dir=temp_dir)
            _, _, loaded_block_settings = manager.load_config()

            self.assertFalse(loaded_block_settings.ignore_replies)
            self.assertFalse(loaded_block_settings.ignore_mentions)
            self.assertFalse(loaded_block_settings.case_sensitive)


class AccountChannelScopeTests(unittest.TestCase):
    def test_account_channel_scope_allows_configured_channel(self):
        account = Account(token="token-1", target_channels=[123, 456])

        self.assertTrue(account.allows_channel(123))
        self.assertFalse(account.allows_channel(789))

    def test_empty_account_channel_scope_means_all_channels(self):
        account = Account(token="token-1", target_channels=[])

        self.assertTrue(account.allows_channel(123))


class ConfigManagerAccountChannelTests(unittest.TestCase):
    def test_migrates_legacy_rule_channels_into_account_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = f"{temp_dir}/config.json"
            payload = {
                "accounts": [{"token": "token-1", "rule_ids": ["rule-1", "rule-2"]}],
                "rules": [
                    {
                        "id": "rule-1",
                        "keywords": ["hi"],
                        "reply": "hello",
                        "match_type": "partial",
                        "target_channels": [100, 200],
                    },
                    {
                        "id": "rule-2",
                        "keywords": ["bye"],
                        "reply": "later",
                        "match_type": "partial",
                        "target_channels": [200, 300],
                    }
                ],
            }
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)

            manager = ConfigManager(config_dir=temp_dir)
            loaded_accounts, loaded_rules, _ = manager.load_config()

            self.assertEqual(loaded_accounts[0].target_channels, [100, 200, 300])
            self.assertEqual(loaded_rules[0].target_channels, [])
            self.assertEqual(loaded_rules[1].target_channels, [])


class RuntimeConfigPathTests(unittest.TestCase):
    def test_resolve_runtime_config_dir_uses_instance_subdirectory(self):
        with patch.dict(os.environ, {}, clear=True):
            config_dir = resolve_runtime_config_dir(instance_name="Team A")

        self.assertTrue(
            config_dir.endswith(os.path.join("DiscordAutoReply", "instances", "Team_A"))
        )

    def test_resolve_runtime_config_dir_uses_packaged_executable_copy_when_no_instance_given(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "frozen", True, create=True), patch.object(
            sys,
            "executable",
            os.path.join("/tmp", "DiscordAutoReply-A.exe"),
        ):
            config_dir = resolve_runtime_config_dir()

        self.assertEqual(config_dir, os.path.join("/tmp", "DiscordAutoReply-A_data"))


if __name__ == "__main__":
    unittest.main()
