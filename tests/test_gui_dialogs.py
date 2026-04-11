import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QAbstractItemView
except ModuleNotFoundError:  # pragma: no cover - optional GUI dependency in test env
    QApplication = None
    QAbstractItemView = None
    Qt = None

from pathlib import Path
import tempfile

from src.discord_client import Account, MatchType, Rule
from tests.test_gui_helpers import build_test_xlsx
if QApplication is not None:
    from src.gui import MainWindow, RuleDialog


@unittest.skipIf(QApplication is None, "PySide6 is not installed in this test environment")
class GuiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])


class RuleDialogKeywordSelectionTests(GuiTestCase):
    def tearDown(self):
        if hasattr(self, "dialog"):
            self.dialog.close()
            self.dialog.deleteLater()

    def test_keyword_list_supports_multi_selection(self):
        self.dialog = RuleDialog()

        self.assertEqual(
            self.dialog.keywords_list.selectionMode(),
            QAbstractItemView.SelectionMode.ExtendedSelection,
        )

    def test_select_all_keywords_selects_every_item(self):
        self.dialog = RuleDialog()
        self.dialog.add_keywords(["alpha", "beta", "gamma"])

        self.dialog.select_all_keywords()

        self.assertEqual(
            [item.text() for item in self.dialog.keywords_list.selectedItems()],
            ["alpha", "beta", "gamma"],
        )

    def test_remove_selected_keyword_removes_all_selected_items(self):
        self.dialog = RuleDialog()
        self.dialog.add_keywords(["alpha", "beta", "gamma", "delta"])
        self.dialog.keywords_list.item(0).setSelected(True)
        self.dialog.keywords_list.item(2).setSelected(True)

        self.dialog.remove_selected_keyword()

        self.assertEqual(self.dialog.get_keywords(), ["beta", "delta"])

    def test_clear_all_keywords_removes_every_keyword(self):
        self.dialog = RuleDialog()
        self.dialog.add_keywords(["alpha", "beta"])

        self.dialog.clear_all_keywords()

        self.assertEqual(self.dialog.get_keywords(), [])

    def test_reply_account_count_defaults_to_one(self):
        self.dialog = RuleDialog()

        self.assertEqual(self.dialog.get_rule_data()["reply_account_count"], 1)


class MainWindowAccountCooldownTests(GuiTestCase):
    def setUp(self):
        with patch.object(MainWindow, "load_config", autospec=True):
            self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def test_accounts_table_shows_cooldown_column(self):
        self.window.discord_manager.accounts = [
            Account(
                token="token-1",
                is_active=True,
                is_valid=True,
                user_info={"name": "sender", "discriminator": "0001"},
                cooldown_until=108.0,
            ),
        ]

        with patch("src.gui.time.time", return_value=100.0):
            self.window.update_accounts_list()

        headers = [
            self.window.accounts_table.horizontalHeaderItem(index).text()
            for index in range(self.window.accounts_table.columnCount())
        ]

        self.assertIn("冷却", headers)
        self.assertIn("冷却", headers)
        self.assertEqual(self.window.accounts_table.item(0, 4).text(), "冷却 8秒")

    def test_update_status_refreshes_account_cooldown_text(self):
        self.window.discord_manager.accounts = [
            Account(
                token="token-1",
                is_active=True,
                is_valid=True,
                user_info={"name": "sender", "discriminator": "0001"},
                cooldown_until=108.0,
            ),
        ]

        with patch("src.gui.time.time", return_value=100.0):
            self.window.update_accounts_list()

        with patch("src.discord_client.time.time", return_value=109.0), patch(
            "src.gui.time.time",
            return_value=109.0,
        ):
            self.window.update_status()

        self.assertEqual(self.window.accounts_table.item(0, 4).text(), "可用")

    def test_accounts_table_shows_empty_rule_ids_as_all_rules(self):
        self.window.discord_manager.rules = [
            Rule(
                id="rule-1",
                keywords=["hello"],
                reply="world",
                match_type=MatchType.PARTIAL,
                target_channels=[],
            ),
            Rule(
                id="rule-2",
                keywords=["123"],
                reply="456",
                match_type=MatchType.PARTIAL,
                target_channels=[],
            ),
        ]
        self.window.discord_manager.accounts = [
            Account(
                token="token-1",
                is_active=True,
                is_valid=True,
                user_info={"name": "sender", "discriminator": "0001"},
                rule_ids=[],
            ),
        ]

        self.window.update_accounts_list()

        self.assertEqual(self.window.accounts_table.item(0, 2).text(), "全部(2)")


class MainWindowReplyThreadModeTests(GuiTestCase):
    def setUp(self):
        with patch.object(MainWindow, "load_config", autospec=True):
            self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def test_reply_thread_mode_checkbox_toggles_manager_setting(self):
        with patch.object(self.window, "save_config", autospec=True) as save_mock:
            self.window.reply_thread_mode_checkbox.setChecked(True)

        self.assertTrue(self.window.discord_manager.reply_in_thread_mode)
        self.assertTrue(self.window.reply_thread_mode_checkbox.isChecked())
        self.assertTrue(save_mock.called)

    def test_load_config_applies_reply_thread_mode_setting(self):
        self.window.config_manager.reply_in_thread_mode = True
        self.window.config_manager.external_rule_sync_settings = self.window.default_external_rule_sync_settings()

        with patch.object(
            self.window.config_manager,
            "load_config",
            return_value=([], [], self.window.discord_manager.block_settings),
        ):
            self.window.load_config()

        self.assertTrue(self.window.reply_thread_mode_checkbox.isChecked())
        self.assertTrue(self.window.discord_manager.reply_in_thread_mode)


class MainWindowReplyHistoryTests(GuiTestCase):
    def setUp(self):
        with patch.object(MainWindow, "load_config", autospec=True):
            self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def test_reply_history_supports_pagination(self):
        self.window.discord_manager.recent_replies = [
            {
                "time_text": f"10:{index:02d}",
                "account_alias": "sender#0001",
                "keyword": f"keyword-{index}",
                "customer_message": f"customer-{index}",
                "message_link": f"https://discord.com/channels/456/123/{index}",
                "reply_content": f"reply-{index}",
            }
            for index in range(25)
        ]

        self.window.update_status()

        self.assertEqual(self.window.reply_history_table.rowCount(), 20)
        self.assertEqual(self.window.reply_history_page_label.text(), "第 1/2 页")
        self.assertEqual(self.window.reply_history_table.item(0, 2).text(), "keyword-24")
        self.assertEqual(self.window.reply_history_table.item(0, 3).text(), "customer-24")
        self.assertEqual(self.window.reply_history_table.item(0, 4).text(), "打开消息")
        self.assertEqual(
            self.window.reply_history_table.item(0, 4).data(Qt.ItemDataRole.UserRole),
            "https://discord.com/channels/456/123/24",
        )
        self.assertEqual(self.window.reply_history_table.item(0, 5).text(), "reply-24")

        self.window.show_next_reply_history_page()

        self.assertEqual(self.window.reply_history_table.rowCount(), 5)
        self.assertEqual(self.window.reply_history_page_label.text(), "第 2/2 页")
        self.assertEqual(self.window.reply_history_table.item(0, 2).text(), "keyword-4")

    def test_copy_selected_reply_history_text_copies_selected_cells(self):
        self.window.discord_manager.recent_replies = [
            {
                "time_text": "10:00",
                "account_alias": "sender#0001",
                "keyword": "keyword-1",
                "customer_message": "customer-1",
                "message_link": "https://discord.com/channels/456/123/1001",
                "reply_content": "reply-1",
            }
        ]

        self.window.update_status()
        self.window.reply_history_table.item(0, 3).setSelected(True)
        self.window.reply_history_table.item(0, 5).setSelected(True)

        self.window.copy_selected_reply_history_text()

        self.assertEqual(QApplication.clipboard().text(), "customer-1\treply-1")

    def test_clicking_reply_history_message_link_opens_url(self):
        self.window.discord_manager.recent_replies = [
            {
                "time_text": "10:00",
                "account_alias": "sender#0001",
                "keyword": "keyword-1",
                "customer_message": "customer-1",
                "message_link": "https://discord.com/channels/456/123/1001",
                "reply_content": "reply-1",
            }
        ]

        self.window.update_status()

        with patch("src.gui.QDesktopServices.openUrl") as open_mock:
            self.window.open_reply_history_message_link(0, 4)

        self.assertEqual(open_mock.call_count, 1)
        self.assertEqual(open_mock.call_args[0][0].toString(), "https://discord.com/channels/456/123/1001")


class MainWindowStorageStatusTests(GuiTestCase):
    def tearDown(self):
        if hasattr(self, "window"):
            self.window.close()
            self.window.deleteLater()

    def test_packaged_copy_shows_current_executable_name_as_instance(self):
        with patch.object(MainWindow, "load_config", autospec=True), patch.object(
            sys,
            "frozen",
            True,
            create=True,
        ), patch.object(
            sys,
            "executable",
            os.path.join("/tmp", "DiscordAutoReply-A.exe"),
        ):
            self.window = MainWindow()

        self.assertIn("当前实例: DiscordAutoReply-A", self.window.data_dir_label.text())
        self.assertIn("当前数据目录: /tmp/DiscordAutoReply-A_data", self.window.data_dir_label.text())


class MainWindowFollowFileSyncTests(GuiTestCase):
    def setUp(self):
        with patch.object(MainWindow, "load_config", autospec=True):
            self.window = MainWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def test_sync_rules_from_follow_xlsx_adds_and_removes_rules(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            xlsx_path = Path(temp_dir) / "follow.xlsx"
            build_test_xlsx(
                xlsx_path,
                [
                    ("alpha", "reply-a"),
                    ("beta", "reply-b"),
                ],
            )

            self.window.external_rule_sync_settings["enabled"] = True
            self.window.external_rule_sync_settings["file_path"] = str(xlsx_path)
            self.window.external_rule_sync_settings["interval_seconds"] = 30

            self.window.sync_rules_from_follow_file(force=True)

            self.assertEqual(len(self.window.discord_manager.rules), 2)
            self.assertTrue(all(getattr(rule, "sync_source", "") == "follow_file" for rule in self.window.discord_manager.rules))
            self.assertEqual([rule.reply for rule in self.window.discord_manager.rules], ["reply-a", "reply-b"])

            build_test_xlsx(
                xlsx_path,
                [
                    ("alpha", "reply-a-updated"),
                ],
            )

            self.window.sync_rules_from_follow_file(force=True)

            self.assertEqual(len(self.window.discord_manager.rules), 1)
            self.assertEqual(self.window.discord_manager.rules[0].keywords, ["alpha"])
            self.assertEqual(self.window.discord_manager.rules[0].reply, "reply-a-updated")

    def test_sync_rules_from_follow_xlsx_reuses_existing_manual_rule_instead_of_duplicating(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            xlsx_path = Path(temp_dir) / "follow.xlsx"
            build_test_xlsx(
                xlsx_path,
                [
                    ("alpha", "reply-a"),
                ],
            )

            self.window.discord_manager.rules = [
                Rule(
                    id="manual-1",
                    keywords=["alpha"],
                    reply="reply-a",
                    match_type=MatchType.PARTIAL,
                    target_channels=[],
                )
            ]
            self.window.external_rule_sync_settings["enabled"] = True
            self.window.external_rule_sync_settings["file_path"] = str(xlsx_path)
            self.window.external_rule_sync_settings["interval_seconds"] = 30

            self.window.sync_rules_from_follow_file(force=True)

            self.assertEqual(len(self.window.discord_manager.rules), 1)
            self.assertEqual(self.window.discord_manager.rules[0].id, "manual-1")
            self.assertEqual(getattr(self.window.discord_manager.rules[0], "sync_source", ""), "follow_file")


class MainWindowRuleSelectionTests(GuiTestCase):
    def setUp(self):
        with patch.object(MainWindow, "load_config", autospec=True):
            self.window = MainWindow()
        self.window.discord_manager.rules = [
            Rule(
                id=f"rule-{index}",
                keywords=[f"keyword-{index}"],
                reply=f"reply-{index}",
                match_type=MatchType.PARTIAL,
                target_channels=[],
            )
            for index in range(1, 4)
        ]
        self.window.update_rules_list()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def test_select_all_rules_selects_every_visible_row(self):
        self.window.select_all_rules()

        selected_rows = [
            model_index.row()
            for model_index in self.window.rules_table.selectionModel().selectedRows()
        ]

        self.assertEqual(selected_rows, [0, 1, 2])

    def test_select_rules_by_range_uses_filtered_visible_order(self):
        self.window.rule_search_input.setText("keyword-2")
        self.window.rule_range_input.setText("1")

        self.window.select_rules_by_range()

        selected_rows = [
            model_index.row()
            for model_index in self.window.rules_table.selectionModel().selectedRows()
        ]

        self.assertEqual(selected_rows, [1])

    def test_rules_table_reply_count_column_shows_one_account(self):
        self.assertEqual(self.window.rules_table.item(0, 3).text(), "1个账号")

    def test_apply_reply_account_count_to_all_rules_updates_every_rule(self):
        self.window.bulk_reply_account_count_combo.setCurrentIndex(2)

        with patch.object(self.window, "save_config") as save_mock, patch("src.gui.QMessageBox.information"):
            self.window.apply_reply_account_count_to_all_rules()

        self.assertTrue(save_mock.called)
        self.assertEqual(
            [rule.reply_account_count for rule in self.window.discord_manager.rules],
            [3, 3, 3],
        )
        self.assertEqual(self.window.rules_table.item(0, 3).text(), "3个账号")

    def test_export_rules_to_csv_writes_table_headers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "rules.csv"
            with patch("src.gui.QFileDialog.getSaveFileName", return_value=(str(output_path), "CSV 文件 (*.csv)")), patch(
                "src.gui.QMessageBox.information"
            ):
                self.window.export_rules_table()

            content = output_path.read_text(encoding="utf-8-sig")
            self.assertIn("序号,关键词,回复内容,匹配类型,回复账号数,是否启用", content)
