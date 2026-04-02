import json
import os
import sys
from typing import List, Dict, Any

# 添加src目录到Python路径（确保打包后能找到模块）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from discord_client import Account, Rule, MatchType, BlockSettings


class ConfigManager:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "config.json")
        self.ensure_config_dir()

    def ensure_config_dir(self):
        """确保配置目录存在"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

    @staticmethod
    def _dedupe_int_values(values: List[Any]) -> List[int]:
        normalized_values = []
        seen_values = set()

        for value in values or []:
            try:
                cleaned_value = int(str(value).strip())
            except (TypeError, ValueError):
                continue

            if cleaned_value in seen_values:
                continue
            normalized_values.append(cleaned_value)
            seen_values.add(cleaned_value)

        return normalized_values

    @classmethod
    def _derive_account_target_channels(cls, account_data: Dict[str, Any], rules: List[Rule]) -> List[int]:
        existing_channels = cls._dedupe_int_values(account_data.get("target_channels", []))
        if existing_channels:
            return existing_channels

        assigned_rule_ids = set(account_data.get("rule_ids", []))
        if not assigned_rule_ids:
            return []

        assigned_rules = [rule for rule in rules if rule.id in assigned_rule_ids]
        if not assigned_rules:
            return []

        if any(not getattr(rule, "target_channels", []) for rule in assigned_rules):
            return []

        merged_channels = []
        for rule in assigned_rules:
            merged_channels.extend(getattr(rule, "target_channels", []))
        return cls._dedupe_int_values(merged_channels)

    @staticmethod
    def _derive_uniform_rule_toggle(rule_data_list: List[Dict[str, Any]], key: str, default: bool) -> bool:
        values = {
            bool(rule_data[key])
            for rule_data in rule_data_list
            if key in rule_data
        }
        if len(values) == 1:
            return values.pop()
        return default

    @staticmethod
    def _normalize_delay_range(delay_min: Any, delay_max: Any, default_min: float = 0.1, default_max: float = 1.0) -> tuple[float, float]:
        return 0.0, 0.0

    @staticmethod
    def _normalize_reply_account_count(value: Any) -> int:
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = 1
        return max(1, min(3, count))

    @classmethod
    def _derive_account_delay_range(cls, account_data: Dict[str, Any], rule_data_list: List[Dict[str, Any]]) -> tuple[float, float]:
        if "delay_min" in account_data or "delay_max" in account_data:
            return cls._normalize_delay_range(
                account_data.get("delay_min"),
                account_data.get("delay_max"),
            )

        assigned_rule_ids = set(account_data.get("rule_ids", []))
        candidate_rule_data = [
            rule_data
            for rule_data in rule_data_list
            if not assigned_rule_ids or rule_data.get("id") in assigned_rule_ids
        ]

        explicit_rule_delays = [
            (
                rule_data.get("delay_min"),
                rule_data.get("delay_max"),
            )
            for rule_data in candidate_rule_data
            if "delay_min" in rule_data or "delay_max" in rule_data
        ]

        if not explicit_rule_delays:
            return cls._normalize_delay_range(None, None)

        normalized_ranges = [
            cls._normalize_delay_range(delay_min, delay_max)
            for delay_min, delay_max in explicit_rule_delays
        ]
        return min(delay_range[0] for delay_range in normalized_ranges), max(delay_range[1] for delay_range in normalized_ranges)

    def save_config(self, accounts: List[Account], rules: List[Rule], block_settings: BlockSettings):
        """保存配置到文件"""
        config_data = {
            "accounts": [
                {
                    "token": acc.token,
                    "is_active": acc.is_active,
                    "is_valid": acc.is_valid,
                    "last_verified": acc.last_verified,
                    "user_info": acc.user_info,
                    "rule_ids": acc.rule_ids,
                    "target_channels": acc.target_channels,
                    "delay_min": 0.0,
                    "delay_max": 0.0,
                    "reply_count": acc.reply_count,
                }
                for acc in accounts
            ],
            "block_settings": {
                "blocked_keywords": block_settings.blocked_keywords,
                "blocked_user_ids": block_settings.blocked_user_ids,
                "blocked_channel_ids": block_settings.blocked_channel_ids,
                "account_scope": block_settings.account_scope,
                "account_tokens": block_settings.account_tokens,
                "ignore_replies": block_settings.ignore_replies,
                "ignore_mentions": block_settings.ignore_mentions,
                "case_sensitive": block_settings.case_sensitive,
            },
            "rules": [
                {
                    "id": rule.id,
                    "keywords": rule.keywords,
                    "reply": rule.reply,
                    "match_type": rule.match_type.value,
                    "delay_min": 0.0,
                    "delay_max": 0.0,
                    "is_active": rule.is_active,
                    "ignore_replies": getattr(rule, 'ignore_replies', False),
                    "ignore_mentions": getattr(rule, 'ignore_mentions', False),
                    "case_sensitive": getattr(rule, 'case_sensitive', False),
                    "reply_account_count": getattr(rule, "reply_account_count", 1),
                }
                for rule in rules
            ]
        }

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    def load_config(self) -> tuple[List[Account], List[Rule], BlockSettings]:
        """从文件加载配置"""
        if not os.path.exists(self.config_file):
            return [], [], BlockSettings()

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            accounts_data = config_data.get("accounts", [])
            rules_data = config_data.get("rules", [])
            rules = []
            legacy_blocked_keywords = []
            for rule_data in rules_data:
                exclude_keywords = rule_data.get("exclude_keywords", [])
                if isinstance(exclude_keywords, str):
                    exclude_keywords = [exclude_keywords]
                legacy_blocked_keywords.extend(exclude_keywords)
                rule = Rule(
                    id=rule_data.get("id", f"rule_{len(rules)}"),  # 如果没有id，生成一个
                    keywords=rule_data["keywords"],
                    reply=rule_data["reply"],
                    match_type=MatchType(rule_data["match_type"]),
                    target_channels=[],
                    delay_min=0.0,
                    delay_max=0.0,
                    is_active=rule_data.get("is_active", True),
                    ignore_replies=rule_data.get("ignore_replies", False),
                    ignore_mentions=rule_data.get("ignore_mentions", False),
                    case_sensitive=rule_data.get("case_sensitive", False),
                    exclude_keywords=[],
                    reply_account_count=self._normalize_reply_account_count(rule_data.get("reply_account_count", 1)),
                )
                rules.append(rule)

            for rule, rule_data in zip(rules, rules_data):
                rule.target_channels = self._dedupe_int_values(rule_data.get("target_channels", []))

            accounts = []
            for acc_data in accounts_data:
                delay_min, delay_max = self._derive_account_delay_range(acc_data, rules_data)
                account = Account(
                    token=acc_data["token"],
                    is_active=acc_data.get("is_active", True),
                    is_valid=acc_data.get("is_valid", False),
                    last_verified=acc_data.get("last_verified"),
                    user_info=acc_data.get("user_info"),
                    rule_ids=acc_data.get("rule_ids", []),
                    target_channels=self._derive_account_target_channels(acc_data, rules),
                    delay_min=delay_min,
                    delay_max=delay_max,
                    reply_count=acc_data.get("reply_count", 0),
                )
                accounts.append(account)

            for rule in rules:
                rule.target_channels = []

            block_settings_data = config_data.get("block_settings", {})
            legacy_ignore_replies = self._derive_uniform_rule_toggle(config_data.get("rules", []), "ignore_replies", True)
            legacy_ignore_mentions = self._derive_uniform_rule_toggle(config_data.get("rules", []), "ignore_mentions", True)
            legacy_case_sensitive = self._derive_uniform_rule_toggle(config_data.get("rules", []), "case_sensitive", False)
            blocked_keywords = block_settings_data.get("blocked_keywords", [])
            if isinstance(blocked_keywords, str):
                blocked_keywords = [blocked_keywords]
            if not blocked_keywords and legacy_blocked_keywords:
                blocked_keywords = legacy_blocked_keywords

            blocked_user_ids = block_settings_data.get("blocked_user_ids", [])
            if isinstance(blocked_user_ids, str):
                blocked_user_ids = [blocked_user_ids]

            blocked_channel_ids = block_settings_data.get("blocked_channel_ids", [])
            if isinstance(blocked_channel_ids, (str, int)):
                blocked_channel_ids = [blocked_channel_ids]

            account_tokens = block_settings_data.get("account_tokens", [])
            if isinstance(account_tokens, str):
                account_tokens = [account_tokens]

            block_settings = BlockSettings(
                blocked_keywords=blocked_keywords,
                blocked_user_ids=blocked_user_ids,
                blocked_channel_ids=self._dedupe_int_values(blocked_channel_ids),
                account_scope=block_settings_data.get("account_scope", "all"),
                account_tokens=account_tokens,
                ignore_replies=block_settings_data.get("ignore_replies", legacy_ignore_replies),
                ignore_mentions=block_settings_data.get("ignore_mentions", legacy_ignore_mentions),
                case_sensitive=block_settings_data.get("case_sensitive", legacy_case_sensitive),
            )

            return accounts, rules, block_settings

        except Exception as e:
            print(f"加载配置失败: {e}")
            return [], [], BlockSettings()

    def export_config(self, filepath: str, accounts: List[Account], rules: List[Rule], block_settings: BlockSettings) -> bool:
        """导出配置到指定文件"""
        try:
            config_data = {
                "accounts": [
                    {
                        "token": acc.token,
                        "alias": acc.alias,
                        "is_active": acc.is_active,
                        "target_channels": acc.target_channels,
                        "delay_min": 0.0,
                        "delay_max": 0.0,
                    }
                    for acc in accounts
                ],
                "block_settings": {
                    "blocked_keywords": block_settings.blocked_keywords,
                    "blocked_user_ids": block_settings.blocked_user_ids,
                    "blocked_channel_ids": block_settings.blocked_channel_ids,
                    "account_scope": block_settings.account_scope,
                    "account_tokens": block_settings.account_tokens,
                    "ignore_replies": block_settings.ignore_replies,
                    "ignore_mentions": block_settings.ignore_mentions,
                    "case_sensitive": block_settings.case_sensitive,
                },
                "rules": [
                    {
                        "keywords": rule.keywords,
                        "reply": rule.reply,
                        "match_type": rule.match_type.value,
                        "delay_min": 0.0,
                        "delay_max": 0.0,
                        "is_active": rule.is_active,
                        "ignore_replies": getattr(rule, 'ignore_replies', False),
                        "ignore_mentions": getattr(rule, 'ignore_mentions', False),
                        "case_sensitive": getattr(rule, 'case_sensitive', False),
                        "reply_account_count": getattr(rule, "reply_account_count", 1),
                    }
                    for rule in rules
                ]
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"导出配置失败: {e}")
            return False

    def import_config(self, filepath: str) -> tuple[List[Account], List[Rule], BlockSettings]:
        """从指定文件导入配置"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            accounts_data = config_data.get("accounts", [])
            rules_data = config_data.get("rules", [])
            rules = []
            legacy_blocked_keywords = []
            for rule_data in rules_data:
                exclude_keywords = rule_data.get("exclude_keywords", [])
                if isinstance(exclude_keywords, str):
                    exclude_keywords = [exclude_keywords]
                legacy_blocked_keywords.extend(exclude_keywords)
                rule = Rule(
                    id=rule_data.get("id", f"rule_{len(rules)}"),  # 如果没有id，生成一个
                    keywords=rule_data["keywords"],
                    reply=rule_data["reply"],
                    match_type=MatchType(rule_data["match_type"]),
                    target_channels=[],
                    delay_min=0.0,
                    delay_max=0.0,
                    is_active=rule_data.get("is_active", True),
                    ignore_replies=rule_data.get("ignore_replies", False),
                    ignore_mentions=rule_data.get("ignore_mentions", False),
                    case_sensitive=rule_data.get("case_sensitive", False),
                    exclude_keywords=[],
                    reply_account_count=self._normalize_reply_account_count(rule_data.get("reply_account_count", 1)),
                )
                rules.append(rule)

            for rule, rule_data in zip(rules, rules_data):
                rule.target_channels = self._dedupe_int_values(rule_data.get("target_channels", []))

            accounts = []
            for acc_data in accounts_data:
                delay_min, delay_max = self._derive_account_delay_range(acc_data, rules_data)
                account = Account(
                    token=acc_data["token"],
                    is_active=acc_data.get("is_active", True),
                    is_valid=acc_data.get("is_valid", False),
                    last_verified=acc_data.get("last_verified"),
                    user_info=acc_data.get("user_info"),
                    rule_ids=acc_data.get("rule_ids", []),
                    target_channels=self._derive_account_target_channels(acc_data, rules),
                    delay_min=delay_min,
                    delay_max=delay_max,
                    reply_count=acc_data.get("reply_count", 0),
                )
                accounts.append(account)

            for rule in rules:
                rule.target_channels = []

            block_settings_data = config_data.get("block_settings", {})
            legacy_ignore_replies = self._derive_uniform_rule_toggle(config_data.get("rules", []), "ignore_replies", True)
            legacy_ignore_mentions = self._derive_uniform_rule_toggle(config_data.get("rules", []), "ignore_mentions", True)
            legacy_case_sensitive = self._derive_uniform_rule_toggle(config_data.get("rules", []), "case_sensitive", False)
            blocked_keywords = block_settings_data.get("blocked_keywords", [])
            if isinstance(blocked_keywords, str):
                blocked_keywords = [blocked_keywords]
            if not blocked_keywords and legacy_blocked_keywords:
                blocked_keywords = legacy_blocked_keywords

            blocked_user_ids = block_settings_data.get("blocked_user_ids", [])
            if isinstance(blocked_user_ids, str):
                blocked_user_ids = [blocked_user_ids]

            blocked_channel_ids = block_settings_data.get("blocked_channel_ids", [])
            if isinstance(blocked_channel_ids, (str, int)):
                blocked_channel_ids = [blocked_channel_ids]

            account_tokens = block_settings_data.get("account_tokens", [])
            if isinstance(account_tokens, str):
                account_tokens = [account_tokens]

            block_settings = BlockSettings(
                blocked_keywords=blocked_keywords,
                blocked_user_ids=blocked_user_ids,
                blocked_channel_ids=self._dedupe_int_values(blocked_channel_ids),
                account_scope=block_settings_data.get("account_scope", "all"),
                account_tokens=account_tokens,
                ignore_replies=block_settings_data.get("ignore_replies", legacy_ignore_replies),
                ignore_mentions=block_settings_data.get("ignore_mentions", legacy_ignore_mentions),
                case_sensitive=block_settings_data.get("case_sensitive", legacy_case_sensitive),
            )

            return accounts, rules, block_settings

        except Exception as e:
            print(f"导入配置失败: {e}")
            return [], [], BlockSettings()
