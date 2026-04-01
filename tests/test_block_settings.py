import json
import tempfile
import unittest

from src.config_manager import ConfigManager
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
                )
            ]
            block_settings = BlockSettings(
                blocked_keywords=["http"],
                blocked_user_ids=["1001"],
                account_scope="selected",
                account_tokens=["token-1"],
                case_sensitive=True,
            )

            self.assertTrue(manager.save_config(accounts, rules, block_settings))

            loaded_accounts, loaded_rules, loaded_block_settings = manager.load_config()

            self.assertEqual([account.token for account in loaded_accounts], ["token-1"])
            self.assertEqual(loaded_accounts[0].target_channels, [123456])
            self.assertEqual([rule.id for rule in loaded_rules], ["rule-1"])
            self.assertEqual(loaded_block_settings.blocked_keywords, ["http"])
            self.assertEqual(loaded_block_settings.blocked_user_ids, ["1001"])
            self.assertEqual(loaded_block_settings.account_scope, "selected")
            self.assertEqual(loaded_block_settings.account_tokens, ["token-1"])
            self.assertTrue(loaded_block_settings.case_sensitive)

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


if __name__ == "__main__":
    unittest.main()
