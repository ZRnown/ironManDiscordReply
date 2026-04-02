import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QAbstractItemView
except ModuleNotFoundError:  # pragma: no cover - optional GUI dependency in test env
    QApplication = None
    QAbstractItemView = None

from src.discord_client import Account
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
