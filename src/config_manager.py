import json
import os
from typing import List, Dict, Any
from dataclasses import asdict
from discord_client import Account, Rule, MatchType


class ConfigManager:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "config.json")
        self.ensure_config_dir()

    def ensure_config_dir(self):
        """确保配置目录存在"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

    def save_config(self, accounts: List[Account], rules: List[Rule]):
        """保存配置到文件"""
        config_data = {
            "accounts": [
                {
                    "token": acc.token,
                    "is_active": acc.is_active,
                    "is_valid": acc.is_valid,
                    "last_verified": acc.last_verified,
                    "user_info": acc.user_info,
                    "rule_ids": acc.rule_ids
                }
                for acc in accounts
            ],
            "rules": [
                {
                    "id": rule.id,
                    "keywords": rule.keywords,
                    "reply": rule.reply,
                    "match_type": rule.match_type.value,
                    "target_channels": rule.target_channels,
                    "delay_min": rule.delay_min,
                    "delay_max": rule.delay_max,
                    "is_active": rule.is_active,
                    "ignore_replies": getattr(rule, 'ignore_replies', False),
                    "ignore_mentions": getattr(rule, 'ignore_mentions', False)
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

    def load_config(self) -> tuple[List[Account], List[Rule]]:
        """从文件加载配置"""
        if not os.path.exists(self.config_file):
            return [], []

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            accounts = []
            for acc_data in config_data.get("accounts", []):
                account = Account(
                    token=acc_data["token"],
                    is_active=acc_data.get("is_active", True),
                    is_valid=acc_data.get("is_valid", False),
                    last_verified=acc_data.get("last_verified"),
                    user_info=acc_data.get("user_info"),
                    rule_ids=acc_data.get("rule_ids", [])
                )
                accounts.append(account)

            rules = []
            for rule_data in config_data.get("rules", []):
                rule = Rule(
                    id=rule_data.get("id", f"rule_{len(rules)}"),  # 如果没有id，生成一个
                    keywords=rule_data["keywords"],
                    reply=rule_data["reply"],
                    match_type=MatchType(rule_data["match_type"]),
                    target_channels=rule_data["target_channels"],
                    delay_min=rule_data.get("delay_min", 2.0),
                    delay_max=rule_data.get("delay_max", 5.0),
                    is_active=rule_data.get("is_active", True),
                    ignore_replies=rule_data.get("ignore_replies", False),
                    ignore_mentions=rule_data.get("ignore_mentions", False)
                )
                rules.append(rule)

            return accounts, rules

        except Exception as e:
            print(f"加载配置失败: {e}")
            return [], []

    def export_config(self, filepath: str, accounts: List[Account], rules: List[Rule]) -> bool:
        """导出配置到指定文件"""
        try:
            config_data = {
                "accounts": [
                    {
                        "token": acc.token,
                        "alias": acc.alias,
                        "is_active": acc.is_active
                    }
                    for acc in accounts
                ],
                "rules": [
                    {
                        "keywords": rule.keywords,
                        "reply": rule.reply,
                        "match_type": rule.match_type.value,
                        "target_channels": rule.target_channels,
                        "delay_min": rule.delay_min,
                        "delay_max": rule.delay_max,
                        "is_active": rule.is_active
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

    def import_config(self, filepath: str) -> tuple[List[Account], List[Rule]]:
        """从指定文件导入配置"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            accounts = []
            for acc_data in config_data.get("accounts", []):
                account = Account(
                    token=acc_data["token"],
                    is_active=acc_data.get("is_active", True),
                    is_valid=acc_data.get("is_valid", False),
                    last_verified=acc_data.get("last_verified"),
                    user_info=acc_data.get("user_info"),
                    rule_ids=acc_data.get("rule_ids", [])
                )
                accounts.append(account)

            rules = []
            for rule_data in config_data.get("rules", []):
                rule = Rule(
                    id=rule_data.get("id", f"rule_{len(rules)}"),  # 如果没有id，生成一个
                    keywords=rule_data["keywords"],
                    reply=rule_data["reply"],
                    match_type=MatchType(rule_data["match_type"]),
                    target_channels=rule_data["target_channels"],
                    delay_min=rule_data.get("delay_min", 2.0),
                    delay_max=rule_data.get("delay_max", 5.0),
                    is_active=rule_data.get("is_active", True),
                    ignore_replies=rule_data.get("ignore_replies", False),
                    ignore_mentions=rule_data.get("ignore_mentions", False)
                )
                rules.append(rule)

            return accounts, rules

        except Exception as e:
            print(f"导入配置失败: {e}")
            return [], []
