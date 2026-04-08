import argparse
import sys
import asyncio
import csv
import hashlib
import html
import os
import time
from typing import List, Optional
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QListWidget, QListWidgetItem, QPushButton, QLabel,
    QLineEdit, QTextEdit, QComboBox, QSpinBox,
    QCheckBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFileDialog, QSplitter, QProgressBar,
    QDialog, QMenu, QScrollArea, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QItemSelectionModel, QUrl
from PySide6.QtGui import QFont, QIcon, QColor, QDesktopServices

# 添加src目录到Python路径（确保打包后能找到模块）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from discord_client import DiscordManager, Account, Rule, MatchType, BlockSettings
from config_manager import ConfigManager, resolve_runtime_config_dir, resolve_runtime_instance_name
from gui_helpers import (
    apply_checked_indices,
    build_row_selection_range,
    can_move_adjacent_row,
    find_item_index_by_id,
    format_remaining_duration,
    get_adjacent_row_index,
    merge_flag_bits,
    move_item_in_list,
    normalize_reorder_target_row,
    parse_channel_ids,
    parse_rule_import_file,
    parse_selection_ranges,
    remove_items_by_indices,
    replace_item_preserving_order,
    split_keywords,
)


class AccountDialog(QDialog):
    """账号添加/编辑对话框"""
    def __init__(self, parent=None, account=None, discord_manager=None):
        super().__init__(parent)
        self.account = account
        self.discord_manager = discord_manager
        self.is_validating = False
        self.current_user_info = account.user_info if account else None
        self.current_is_valid = account.is_valid if account else False
        self.current_last_verified = account.last_verified if account else None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("添加账号" if not self.account else "编辑账号")
        self.setModal(True)
        self.resize(560, 380)

        layout = QVBoxLayout(self)

        # Token输入
        token_layout = QHBoxLayout()
        token_layout.addWidget(QLabel("Discord Token:"))
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("输入Discord用户Token（非机器人Token）")
        if self.account:
            self.token_input.setText(self.account.token)
        self.token_input.textChanged.connect(self.on_token_changed)
        token_layout.addWidget(self.token_input)

        # 验证按钮
        self.validate_btn = QPushButton("验证Token")
        self.validate_btn.clicked.connect(self.validate_token)
        token_layout.addWidget(self.validate_btn)

        # 帮助按钮
        help_btn = QPushButton("❓")
        help_btn.setMaximumWidth(30)
        help_btn.setToolTip("如何获取Discord Token")
        help_btn.clicked.connect(self.show_token_help)
        token_layout.addWidget(help_btn)

        layout.addLayout(token_layout)

        # 验证状态显示
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        self.status_label.setWordWrap(True)  # 允许换行
        layout.addWidget(self.status_label)

        # 显示当前用户信息（如果有的话）
        if self.account and self.account.user_info and isinstance(self.account.user_info, dict):
            user_info = self.account.user_info
            username = f"{user_info.get('name', 'Unknown')}#{user_info.get('discriminator', '0000')}"
            info_label = QLabel(f"当前账号: {username}")
            info_label.setStyleSheet("color: blue; font-weight: bold;")
            layout.addWidget(info_label)

        # 激活状态
        self.active_checkbox = QCheckBox("启用账号")
        self.active_checkbox.setChecked(True if not self.account else self.account.is_active)
        layout.addWidget(self.active_checkbox)

        channels_layout = QVBoxLayout()
        channels_layout.addWidget(QLabel("频道ID (可选，可多个):"))
        self.account_channels_input = QLineEdit()
        self.account_channels_input.setPlaceholderText("为空则监听所有频道，多个频道可用逗号、空格或换行分隔")
        self.account_channels_input.setToolTip("支持多个频道ID，留空表示全部频道")
        if self.account:
            self.account_channels_input.setText(", ".join(map(str, self.account.target_channels)))
        channels_layout.addWidget(self.account_channels_input)
        channels_hint = QLabel("支持多个频道ID。留空表示全部频道。")
        channels_hint.setStyleSheet("color: gray;")
        channels_layout.addWidget(channels_hint)
        layout.addLayout(channels_layout)

        speed_hint = QLabel("回复速度已固定为 0 秒，命中后立即回复。")
        speed_hint.setStyleSheet("color: gray;")
        layout.addWidget(speed_hint)

        # 按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept_and_validate)
        self.ok_btn.setDefault(True)
        buttons_layout.addWidget(self.ok_btn)

        layout.addLayout(buttons_layout)

        # 如果是编辑模式，显示当前验证状态
        if self.account:
            self.update_validation_status()

    def on_token_changed(self):
        """Token输入改变时重置验证状态"""
        if not self.is_validating:
            self.status_label.setText("")
            self.status_label.setStyleSheet("color: gray; font-style: italic;")
            self.current_user_info = None
            self.current_is_valid = False
            self.current_last_verified = None

    def update_validation_status(self):
        """更新验证状态显示"""
        if self.current_last_verified:
            if self.current_is_valid and self.current_user_info and isinstance(self.current_user_info, dict):
                user_info = self.current_user_info
                username = f"{user_info.get('name', 'Unknown')}#{user_info.get('discriminator', '0000')}"
                self.status_label.setText(f"✅ Token有效 - 用户名: {username}")
                self.status_label.setStyleSheet("color: green;")
            else:
                self.status_label.setText("❌ Token无效或已过期")
                self.status_label.setStyleSheet("color: red;")
        else:
            self.status_label.setText("⚠️ Token未验证")
            self.status_label.setStyleSheet("color: orange;")

    async def validate_token_async(self):
        """异步验证Token"""
        token = self.token_input.text().strip()
        if not token:
            self.status_label.setText("❌ 请输入Token")
            self.status_label.setStyleSheet("color: red;")
            return

        self.is_validating = True
        self.validate_btn.setEnabled(False)
        self.validate_btn.setText("验证中...")
        self.status_label.setText("🔄 正在验证Token，请稍候...")
        self.status_label.setStyleSheet("color: blue;")

        # 强制更新UI
        QApplication.processEvents()

        try:
            # 更新状态：正在连接
            self.status_label.setText("🔗 正在连接Discord服务器...")
            self.status_label.setStyleSheet("color: blue;")
            QApplication.processEvents()

            # 导入验证器
            from discord_client import TokenValidator
            validator = TokenValidator()

            # 执行验证
            is_valid, user_info, error_msg = await validator.validate_token(token)

            if is_valid and user_info and isinstance(user_info, dict):
                self.current_user_info = user_info
                self.current_is_valid = True
                self.current_last_verified = time.time()
                username = f"{user_info.get('name', 'Unknown')}#{user_info.get('discriminator', '0000')}"
                bot_status = "🤖 机器人账号" if user_info.get('bot', False) else "👤 用户账号"
                self.status_label.setText(f"✅ Token有效\n{bot_status}\n👤 用户名: {username}\n🔗 验证成功！")
                self.status_label.setStyleSheet("color: green;")
            else:
                self.current_user_info = None
                self.current_is_valid = False
                self.current_last_verified = time.time()
                # 提供更友好的错误信息
                if "401" in error_msg or "Unauthorized" in error_msg:
                    friendly_msg = "Token无效或已过期，请重新获取"
                elif "Improper token" in error_msg:
                    friendly_msg = "Token格式错误，请检查是否正确复制"
                elif "429" in error_msg:
                    friendly_msg = "请求过于频繁，请稍后再试"
                elif "403" in error_msg:
                    friendly_msg = "Token权限不足"
                elif "timeout" in error_msg.lower():
                    friendly_msg = "连接超时，请检查网络"
                elif "格式" in error_msg:
                    friendly_msg = error_msg
                else:
                    friendly_msg = "Token验证失败，请检查Token是否正确"

                self.status_label.setText(f"❌ Token无效\n💡 {friendly_msg}\n🔍 原始错误: {error_msg}")
                self.status_label.setStyleSheet("color: red;")

        except Exception as e:
            self.current_user_info = None
            self.current_is_valid = False
            self.current_last_verified = None
            self.status_label.setText(f"❌ 验证出错: {str(e)}")
            self.status_label.setStyleSheet("color: red;")
        finally:
            self.is_validating = False
            self.validate_btn.setEnabled(True)
            self.validate_btn.setText("验证Token")

    def validate_token(self):
        """验证Token（同步包装器）"""
        # 创建新的事件循环来运行异步验证
        # 注意：这会暂时阻塞GUI，但在PySide6不使用qasync的情况下，这是处理短时间异步任务的简单方法
        try:
            # 显示验证开始状态
            self.status_label.setText("🔄 正在验证Token，请稍候...")
            self.status_label.setStyleSheet("color: blue;")
            QApplication.processEvents()  # 强制更新UI

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.validate_token_async())
            loop.close()
        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 100:
                error_msg = error_msg[:100] + "..."
            self.status_label.setText(f"❌ 验证系统错误: {error_msg}")
            self.status_label.setStyleSheet("color: red;")

    def show_token_help(self):
        """显示Token获取帮助"""
        help_text = """
        <h3>如何获取Discord Token</h3>

        <p><b>重要提醒：</b>请谨慎使用Token，不要泄露给他人！</p>

        <h4>获取用户Token（推荐用于个人使用）：</h4>
        <ol>
        <li>打开Discord网页版或桌面客户端</li>
        <li>按 <b>F12</b> 打开开发者工具</li>
        <li>切换到 <b>Application</b> 标签页</li>
        <li>在左侧选择 <b>Local Storage</b> → <b>https://discord.com</b></li>
        <li>找到 <b>token</b> 字段</li>
        <li>复制 <b>value</b> 列的值（不包含引号）</li>
        </ol>

        <h4>Token格式示例：</h4>
        <p><code>mfa.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX</code></p>
        <p>或</p>
        <p><code>XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX</code></p>

        <h4>常见错误：</h4>
        <ul>
        <li><b>401 Unauthorized</b>: Token无效或已过期</li>
        <li><b>Improper token</b>: Token格式错误</li>
        <li><b>403 Forbidden</b>: Token权限不足</li>
        </ul>

        <p><b>注意：</b>Token会定期过期，建议定期更新。</p>
        """

        QMessageBox.information(self, "Discord Token获取指南",
                               help_text, QMessageBox.StandardButton.Ok)

    def accept_and_validate(self):
        """确定并验证"""
        try:
            self.parse_target_channels()
        except ValueError as exc:
            QMessageBox.warning(self, "频道格式错误", str(exc))
            return

        # 如果还没有验证过，自动验证一次
        if not self.status_label.text() or "未验证" in self.status_label.text():
            self.validate_token()

        # 检查验证结果
        if "❌" in self.status_label.text():
            reply = QMessageBox.question(
                self, "Token无效",
                "Token验证失败，确定要继续保存吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self.accept()

    def parse_target_channels(self) -> List[int]:
        return parse_channel_ids(self.account_channels_input.text())

    def parse_reply_delay_range(self) -> tuple[float, float]:
        return 0.0, 0.0

    def get_account_data(self):
        """获取账号数据"""
        return {
            'token': self.token_input.text().strip(),
            'is_active': self.active_checkbox.isChecked(),
            'is_valid': self.current_is_valid,
            'user_info': self.current_user_info,
            'last_verified': self.current_last_verified,
            'target_channels': self.parse_target_channels(),
            'delay_min': 0.0,
            'delay_max': 0.0,
        }


class ReorderableKeywordList(QListWidget):
    """支持稳定拖拽排序的关键词列表"""
    row_reordered = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setMinimumHeight(120)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropOverwriteMode(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        if event.source() is not self:
            super().dropEvent(event)
            return

        selected_items = self.selectedItems()
        if len(selected_items) != 1:
            event.ignore()
            return

        source_row = self.row(selected_items[0])
        target_row = self._target_row_from_event(event)
        if target_row < 0:
            event.ignore()
            return

        target_row = normalize_reorder_target_row(source_row, target_row, self.count())

        if source_row == target_row:
            event.accept()
            return

        self.row_reordered.emit(source_row, target_row)
        event.accept()

    def _target_row_from_event(self, event) -> int:
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self.indexAt(position)

        if not index.isValid():
            return self.count()

        indicator = self.dropIndicatorPosition()
        if indicator == QAbstractItemView.DropIndicatorPosition.BelowItem:
            return index.row() + 1
        if indicator == QAbstractItemView.DropIndicatorPosition.OnViewport:
            return self.count()
        return index.row()


class RuleDialog(QDialog):
    """规则添加/编辑对话框"""
    def __init__(self, parent=None, rule=None):
        super().__init__(parent)
        self.rule = rule
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("添加规则" if not self.rule else "编辑规则")
        self.setModal(True)
        self.resize(560, 360)

        layout = QVBoxLayout(self)

        # 关键词输入与排序
        keywords_layout = QVBoxLayout()
        keywords_header = QHBoxLayout()
        keywords_header.addWidget(QLabel("关键词:"))
        keywords_header.addStretch()
        keywords_hint = QLabel("支持 Ctrl/Cmd/Shift 多选，双击可直接编辑；单选时可用上下按钮调整顺序")
        keywords_hint.setStyleSheet("color: gray;")
        keywords_header.addWidget(keywords_hint)
        keywords_layout.addLayout(keywords_header)

        keyword_input_layout = QHBoxLayout()
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("输入关键词后回车或点添加，支持逗号/换行批量粘贴")
        self.keyword_input.returnPressed.connect(self.add_keywords_from_input)
        keyword_input_layout.addWidget(self.keyword_input)

        add_keyword_btn = QPushButton("添加")
        add_keyword_btn.clicked.connect(self.add_keywords_from_input)
        keyword_input_layout.addWidget(add_keyword_btn)
        keywords_layout.addLayout(keyword_input_layout)

        self.keywords_list = ReorderableKeywordList()
        self.keywords_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.keywords_list.setDragEnabled(False)
        self.keywords_list.setAcceptDrops(False)
        self.keywords_list.viewport().setAcceptDrops(False)
        self.keywords_list.setDropIndicatorShown(False)
        self.keywords_list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.keywords_list.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed
        )
        keywords_layout.addWidget(self.keywords_list)

        keyword_actions_layout = QHBoxLayout()
        move_up_keyword_btn = QPushButton("上移")
        move_up_keyword_btn.clicked.connect(self.move_selected_keyword_up)
        keyword_actions_layout.addWidget(move_up_keyword_btn)

        move_down_keyword_btn = QPushButton("下移")
        move_down_keyword_btn.clicked.connect(self.move_selected_keyword_down)
        keyword_actions_layout.addWidget(move_down_keyword_btn)

        select_all_keyword_btn = QPushButton("全选")
        select_all_keyword_btn.clicked.connect(self.select_all_keywords)
        keyword_actions_layout.addWidget(select_all_keyword_btn)

        clear_all_keyword_btn = QPushButton("一键清空")
        clear_all_keyword_btn.clicked.connect(self.clear_all_keywords)
        keyword_actions_layout.addWidget(clear_all_keyword_btn)

        keyword_actions_layout.addStretch()
        remove_keyword_btn = QPushButton("删除选中")
        remove_keyword_btn.clicked.connect(self.remove_selected_keyword)
        keyword_actions_layout.addWidget(remove_keyword_btn)
        keywords_layout.addLayout(keyword_actions_layout)

        if self.rule:
            self.add_keywords(self.rule.keywords)

        layout.addLayout(keywords_layout)

        # 回复内容
        reply_layout = QVBoxLayout()
        reply_layout.addWidget(QLabel("回复内容:"))
        self.reply_input = QTextEdit()
        self.reply_input.setMaximumHeight(80)
        if self.rule:
            self.reply_input.setText(self.rule.reply)
        reply_layout.addWidget(self.reply_input)
        layout.addLayout(reply_layout)

        # 匹配类型
        type_layout_row = QHBoxLayout()

        type_layout = QVBoxLayout()
        type_layout.addWidget(QLabel("匹配类型:"))
        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems(["partial - 部分匹配", "exact - 精确匹配", "regex - 正则表达式"])
        if self.rule:
            if self.rule.match_type.value == "partial":
                self.match_type_combo.setCurrentIndex(0)
            elif self.rule.match_type.value == "exact":
                self.match_type_combo.setCurrentIndex(1)
            else:
                self.match_type_combo.setCurrentIndex(2)
        type_layout.addWidget(self.match_type_combo)
        type_layout_row.addLayout(type_layout)

        reply_count_layout = QVBoxLayout()
        reply_count_layout.addWidget(QLabel("回复账号数:"))
        self.reply_account_count_combo = QComboBox()
        self.reply_account_count_combo.addItems(["1个账号", "2个账号", "3个账号"])
        default_reply_account_count = getattr(self.rule, "reply_account_count", 1) if self.rule else 1
        self.reply_account_count_combo.setCurrentIndex(max(0, min(2, default_reply_account_count - 1)))
        reply_count_layout.addWidget(self.reply_account_count_combo)
        type_layout_row.addLayout(reply_count_layout)
        type_layout_row.addStretch()

        layout.addLayout(type_layout_row)

        match_hint = QLabel("部分匹配会在整条消息里找关键词，只要包含就会触发；多关键词之间是“或”关系，不是“且”关系。")
        match_hint.setStyleSheet("color: gray;")
        match_hint.setWordWrap(True)
        layout.addWidget(match_hint)

        # 激活状态
        self.active_checkbox = QCheckBox("启用规则")
        self.active_checkbox.setChecked(True if not self.rule else self.rule.is_active)
        layout.addWidget(self.active_checkbox)

        # 按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setDefault(True)
        buttons_layout.addWidget(self.ok_btn)

        layout.addLayout(buttons_layout)

    def add_keywords(self, keywords: List[str]):
        for keyword in keywords:
            cleaned_keyword = keyword.strip()
            if not cleaned_keyword:
                continue

            self.add_keyword_item(cleaned_keyword)

    def add_keyword_item(self, keyword: str):
        item = QListWidgetItem(keyword)
        item_flags = merge_flag_bits(
            item.flags(),
            Qt.ItemFlag.ItemIsEditable,
            Qt.ItemFlag.ItemIsDragEnabled,
            Qt.ItemFlag.ItemIsDropEnabled,
        )
        item.setFlags(item_flags)
        self.keywords_list.addItem(item)

    def add_keywords_from_input(self):
        keywords = split_keywords(self.keyword_input.text())
        if not keywords:
            return

        self.add_keywords(keywords)
        self.keyword_input.clear()
        self.keywords_list.setCurrentRow(self.keywords_list.count() - 1)

    def select_all_keywords(self):
        if self.keywords_list.count() <= 0:
            return
        self.keywords_list.selectAll()

    def remove_selected_keyword(self):
        selected_rows = sorted({index.row() for index in self.keywords_list.selectedIndexes()})
        if not selected_rows:
            current_row = self.keywords_list.currentRow()
            if current_row >= 0:
                selected_rows = [current_row]

        if not selected_rows:
            return

        keyword_texts = [
            self.keywords_list.item(index).text()
            for index in range(self.keywords_list.count())
        ]
        remaining_keywords = remove_items_by_indices(keyword_texts, selected_rows)
        next_row = min(selected_rows[0], len(remaining_keywords) - 1) if remaining_keywords else -1

        self.keywords_list.clear()
        self.add_keywords(remaining_keywords)

        if next_row >= 0:
            self.keywords_list.setCurrentRow(next_row)

    def clear_all_keywords(self):
        self.keywords_list.clear()
        self.keyword_input.clear()

    def move_selected_keyword_up(self):
        self.move_selected_keyword(-1)

    def move_selected_keyword_down(self):
        self.move_selected_keyword(1)

    def move_selected_keyword(self, step: int):
        item_count = self.keywords_list.count()
        if item_count <= 0:
            return

        current_row = self.keywords_list.currentRow()
        if current_row < 0:
            return

        target_row = get_adjacent_row_index(current_row, item_count, step)
        if target_row == current_row:
            return

        self.move_keyword_row(current_row, target_row)

    def move_keyword_row(self, source_row: int, target_row: int):
        keyword_texts = [self.keywords_list.item(index).text() for index in range(self.keywords_list.count())]
        moved_keywords = move_item_in_list(keyword_texts, source_row, target_row)
        self.keywords_list.clear()
        self.add_keywords(moved_keywords)
        self.keywords_list.setCurrentRow(target_row)

    def get_keywords(self) -> List[str]:
        keywords = []
        for index in range(self.keywords_list.count()):
            keyword = self.keywords_list.item(index).text().strip()
            if keyword:
                keywords.append(keyword)

        pending_keywords = split_keywords(self.keyword_input.text())
        if pending_keywords:
            keywords.extend(pending_keywords)

        return keywords

    def get_rule_data(self):
        """获取规则数据"""
        match_type_map = {
            0: "partial",
            1: "exact",
            2: "regex"
        }

        return {
            'keywords': self.get_keywords(),
            'reply': self.reply_input.toPlainText().strip(),
            'match_type': match_type_map[self.match_type_combo.currentIndex()],
            'reply_account_count': self.reply_account_count_combo.currentIndex() + 1,
            'is_active': self.active_checkbox.isChecked(),
        }


class BlockSettingsDialog(QDialog):
    """整体屏蔽和匹配设置对话框"""

    def __init__(self, parent=None, block_settings=None, accounts=None):
        super().__init__(parent)
        self.block_settings = block_settings or BlockSettings()
        self.accounts = accounts or []
        self.account_checkboxes = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("整体匹配和屏蔽设置")
        self.setModal(True)
        self.resize(760, 760)

        layout = QVBoxLayout(self)

        scope_layout = QHBoxLayout()
        scope_layout.addWidget(QLabel("生效账号:"))
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["全部账号", "指定账号"])
        self.scope_combo.setCurrentIndex(0 if self.block_settings.account_scope == "all" else 1)
        self.scope_combo.currentIndexChanged.connect(self.update_account_scope_state)
        scope_layout.addWidget(self.scope_combo)
        scope_layout.addStretch()
        layout.addLayout(scope_layout)

        match_group = QGroupBox("通用匹配设置")
        match_layout = QVBoxLayout(match_group)
        match_hint = QLabel(
            "这些设置会统一作用到所有规则，也会影响关键词屏蔽的匹配方式。"
            "屏蔽只会跟着账号当前会回复的频道生效；如果账号监听的是全部频道，这里也会覆盖全部频道。"
        )
        match_hint.setStyleSheet("color: gray;")
        match_hint.setWordWrap(True)
        match_layout.addWidget(match_hint)

        match_options_layout = QHBoxLayout()
        self.ignore_replies_checkbox = QCheckBox("忽略回复消息")
        self.ignore_replies_checkbox.setToolTip("启用后，别人回复某条消息时，这类消息不会触发自动回复。")
        self.ignore_replies_checkbox.setChecked(self.block_settings.ignore_replies)
        match_options_layout.addWidget(self.ignore_replies_checkbox)

        self.ignore_mentions_checkbox = QCheckBox("忽略@消息")
        self.ignore_mentions_checkbox.setToolTip("启用后，消息里带 @ 时，这类消息不会触发自动回复。")
        self.ignore_mentions_checkbox.setChecked(self.block_settings.ignore_mentions)
        match_options_layout.addWidget(self.ignore_mentions_checkbox)
        match_options_layout.addStretch()
        match_layout.addLayout(match_options_layout)

        layout.addWidget(match_group)

        keyword_group = QGroupBox("屏蔽关键词")
        keyword_layout = QVBoxLayout(keyword_group)
        keyword_hint = QLabel("命中这些词的消息会被直接跳过，支持逗号、分号或换行分隔。频道范围跟随账号的回复频道设置。")
        keyword_hint.setStyleSheet("color: gray;")
        keyword_hint.setWordWrap(True)
        keyword_layout.addWidget(keyword_hint)
        self.blocked_keywords_input = QTextEdit()
        self.blocked_keywords_input.setReadOnly(False)
        self.blocked_keywords_input.setAcceptRichText(False)
        self.blocked_keywords_input.setMinimumHeight(88)
        self.blocked_keywords_input.setMaximumHeight(96)
        self.blocked_keywords_input.setStyleSheet(
            "QTextEdit { background-color: white; color: #202020; border: 1px solid #c8c8c8; border-radius: 4px; }"
            "QTextEdit:focus { border: 1px solid #0078d4; }"
        )
        self.blocked_keywords_input.setPlaceholderText("例如：http\ndiscord.gg\n广告")
        self.blocked_keywords_input.setPlainText("\n".join(self.block_settings.blocked_keywords))
        keyword_layout.addWidget(self.blocked_keywords_input)
        layout.addWidget(keyword_group)

        channel_group = QGroupBox("屏蔽频道范围")
        channel_layout = QVBoxLayout(channel_group)
        channel_hint = QLabel("留空表示跟随账号当前可回复的频道；填写后，只在这些频道里启用上面的屏蔽关键词和屏蔽用户。")
        channel_hint.setStyleSheet("color: gray;")
        channel_hint.setWordWrap(True)
        channel_layout.addWidget(channel_hint)
        self.blocked_channel_ids_input = QLineEdit()
        self.blocked_channel_ids_input.setPlaceholderText("例如 123456789012345678, 234567890123456789")
        self.blocked_channel_ids_input.setText(", ".join(map(str, self.block_settings.blocked_channel_ids)))
        channel_layout.addWidget(self.blocked_channel_ids_input)
        layout.addWidget(channel_group)

        user_group = QGroupBox("屏蔽用户")
        user_layout = QVBoxLayout(user_group)
        user_hint = QLabel("填 Discord 用户 ID，命中这些用户发的消息就不回复")
        user_hint.setStyleSheet("color: gray;")
        user_hint.setWordWrap(True)
        user_layout.addWidget(user_hint)
        self.blocked_user_ids_input = QTextEdit()
        self.blocked_user_ids_input.setReadOnly(False)
        self.blocked_user_ids_input.setAcceptRichText(False)
        self.blocked_user_ids_input.setMinimumHeight(88)
        self.blocked_user_ids_input.setMaximumHeight(96)
        self.blocked_user_ids_input.setStyleSheet(
            "QTextEdit { background-color: white; color: #202020; border: 1px solid #c8c8c8; border-radius: 4px; }"
            "QTextEdit:focus { border: 1px solid #0078d4; }"
        )
        self.blocked_user_ids_input.setPlaceholderText("一行一个或逗号分隔，例如：\n123456789012345678")
        self.blocked_user_ids_input.setPlainText("\n".join(self.block_settings.blocked_user_ids))
        user_layout.addWidget(self.blocked_user_ids_input)
        layout.addWidget(user_group)

        account_group = QGroupBox("指定生效账号")
        account_layout = QVBoxLayout(account_group)

        self.account_scope_hint_label = QLabel()
        self.account_scope_hint_label.setStyleSheet("color: gray;")
        self.account_scope_hint_label.setWordWrap(True)
        account_layout.addWidget(self.account_scope_hint_label)

        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("按序号选择:"))
        self.account_range_input = QLineEdit()
        self.account_range_input.setPlaceholderText("例如 1-3, 5")
        self.account_range_input.returnPressed.connect(self.select_account_range)
        range_layout.addWidget(self.account_range_input)

        select_range_btn = QPushButton("勾选区间")
        select_range_btn.clicked.connect(self.select_account_range)
        range_layout.addWidget(select_range_btn)

        clear_range_btn = QPushButton("取消区间")
        clear_range_btn.clicked.connect(self.clear_account_range)
        range_layout.addWidget(clear_range_btn)
        account_layout.addLayout(range_layout)

        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        selected_tokens = set(self.block_settings.account_tokens)
        for index, account in enumerate(self.accounts, start=1):
            checkbox = QCheckBox(f"{index}. {account.alias}")
            checkbox.setChecked(account.token in selected_tokens)
            checkbox.setToolTip(f"Token: {account.token[:12]}...")
            self.account_checkboxes.append((account.token, checkbox))
            scroll_layout.addWidget(checkbox)

        if not self.account_checkboxes:
            empty_label = QLabel("当前还没有账号可选")
            empty_label.setStyleSheet("color: gray; font-style: italic;")
            scroll_layout.addWidget(empty_label)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(240)
        scroll_area.setStyleSheet(
            "QScrollArea { background-color: white; border: 1px solid #c8c8c8; border-radius: 4px; }"
        )
        account_layout.addWidget(scroll_area)

        self.account_stats_label = QLabel()
        account_layout.addWidget(self.account_stats_label)

        account_buttons_layout = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(self.select_all_accounts)
        account_buttons_layout.addWidget(select_all_btn)

        clear_all_btn = QPushButton("清空")
        clear_all_btn.clicked.connect(self.clear_all_accounts)
        account_buttons_layout.addWidget(clear_all_btn)
        account_buttons_layout.addStretch()
        account_layout.addLayout(account_buttons_layout)

        layout.addWidget(account_group)
        self.account_group = account_group

        for _, checkbox in self.account_checkboxes:
            checkbox.stateChanged.connect(self.update_account_stats_label)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("确定")
        confirm_btn.clicked.connect(self.accept)
        confirm_btn.setDefault(True)
        buttons_layout.addWidget(confirm_btn)
        layout.addLayout(buttons_layout)

        self.update_account_scope_state()
        self.update_account_stats_label()

    def update_account_scope_state(self):
        is_selected_scope = self.scope_combo.currentIndex() == 1
        if is_selected_scope:
            self.account_scope_hint_label.setText("当前是指定账号生效。下面勾选的账号会真正生效。")
        else:
            self.account_scope_hint_label.setText("当前是全部账号生效。下面的勾选会保留，但现在不会限制生效范围。")

    def update_account_stats_label(self):
        selected_count = sum(1 for _, checkbox in self.account_checkboxes if checkbox.isChecked())
        total_count = len(self.account_checkboxes)
        self.account_stats_label.setText(f"已选择 {selected_count}/{total_count} 个账号")

    def select_all_accounts(self):
        for _, checkbox in self.account_checkboxes:
            checkbox.setChecked(True)

    def clear_all_accounts(self):
        for _, checkbox in self.account_checkboxes:
            checkbox.setChecked(False)

    def select_account_range(self):
        self.apply_account_range(checked=True)

    def clear_account_range(self):
        self.apply_account_range(checked=False)

    def apply_account_range(self, checked: bool):
        if not self.account_checkboxes:
            QMessageBox.information(self, "提示", "当前没有账号可供选择")
            return

        selection_text = self.account_range_input.text().strip()
        if not selection_text:
            QMessageBox.information(self, "提示", "请输入账号序号范围，例如 1-3, 5")
            return

        try:
            row_indices = parse_selection_ranges(selection_text, len(self.account_checkboxes))
        except ValueError as exc:
            QMessageBox.warning(self, "范围格式错误", str(exc))
            return

        current_states = [checkbox.isChecked() for _, checkbox in self.account_checkboxes]
        updated_states = apply_checked_indices(current_states, row_indices, checked=checked)
        for state, (_, checkbox) in zip(updated_states, self.account_checkboxes):
            checkbox.setChecked(state)

        self.update_account_stats_label()

    def get_selected_account_tokens(self) -> List[str]:
        return [token for token, checkbox in self.account_checkboxes if checkbox.isChecked()]

    def get_block_settings(self) -> BlockSettings:
        return BlockSettings(
            blocked_keywords=split_keywords(self.blocked_keywords_input.toPlainText()),
            blocked_user_ids=split_keywords(self.blocked_user_ids_input.toPlainText()),
            blocked_channel_ids=parse_channel_ids(self.blocked_channel_ids_input.text()),
            account_scope="all" if self.scope_combo.currentIndex() == 0 else "selected",
            account_tokens=self.get_selected_account_tokens(),
            ignore_replies=self.ignore_replies_checkbox.isChecked(),
            ignore_mentions=self.ignore_mentions_checkbox.isChecked(),
            case_sensitive=False,
        )

    def accept(self):
        try:
            block_settings = self.get_block_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "频道格式错误", str(exc))
            return

        invalid_user_ids = [user_id for user_id in block_settings.blocked_user_ids if not user_id.isdigit()]
        if invalid_user_ids:
            QMessageBox.warning(self, "格式错误", f"屏蔽用户ID只能填数字：{', '.join(invalid_user_ids)}")
            return

        if block_settings.account_scope == "selected" and not block_settings.account_tokens:
            QMessageBox.warning(self, "缺少账号", "你选择了指定账号生效，但还没有勾选任何账号")
            return

        super().accept()


class RangeSelectableRowsTable(QTableWidget):
    """支持 Shift 单击连续选中的通用行表格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.anchor_row: Optional[int] = None
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def mousePressEvent(self, event):
        clicked_row = self._row_from_event(event)
        is_shift_click = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if is_shift_click and clicked_row >= 0 and self.anchor_row is not None:
            self.select_rows_by_indices(build_row_selection_range(self.anchor_row, clicked_row))
            return

        super().mousePressEvent(event)

        if clicked_row >= 0:
            self.anchor_row = clicked_row

    def select_rows_by_indices(self, row_indices: List[int], clear_existing: bool = True):
        if not row_indices:
            return

        if clear_existing:
            self.clearSelection()

        selection_model = self.selectionModel()
        if selection_model is None:
            return

        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for row_index in row_indices:
            model_index = self.model().index(row_index, 0)
            selection_model.select(model_index, flags)

        self.anchor_row = row_indices[0]
        self.setCurrentCell(row_indices[-1], 0, QItemSelectionModel.SelectionFlag.NoUpdate)

    def _row_from_event(self, event) -> int:
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self.indexAt(position)
        return index.row() if index.isValid() else -1


class AccountEditDialog(QDialog):
    """账号编辑对话框：支持 token 替换与规则范围勾选"""

    on_token_changed = AccountDialog.on_token_changed
    update_validation_status = AccountDialog.update_validation_status
    validate_token_async = AccountDialog.validate_token_async
    validate_token = AccountDialog.validate_token
    show_token_help = AccountDialog.show_token_help
    accept_and_validate = AccountDialog.accept_and_validate
    parse_target_channels = AccountDialog.parse_target_channels
    parse_reply_delay_range = AccountDialog.parse_reply_delay_range

    def __init__(self, parent=None, account=None, rules=None):
        super().__init__(parent)
        self.account = account
        self.rules = rules or []
        self.checkboxes = []
        self.is_validating = False
        self.current_user_info = account.user_info if account else None
        self.current_is_valid = account.is_valid if account else False
        self.current_last_verified = account.last_verified if account else None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"编辑账号 - {self.account.alias}")
        self.setModal(True)
        self.resize(640, 680)
        self.default_all_rules_mode = not self.account.rule_ids

        layout = QVBoxLayout(self)

        token_layout = QHBoxLayout()
        token_layout.addWidget(QLabel("Discord Token:"))
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("输入新的 Discord Token")
        self.token_input.setText(self.account.token)
        self.token_input.textChanged.connect(self.on_token_changed)
        token_layout.addWidget(self.token_input)

        self.validate_btn = QPushButton("验证Token")
        self.validate_btn.clicked.connect(self.validate_token)
        token_layout.addWidget(self.validate_btn)

        help_btn = QPushButton("❓")
        help_btn.setMaximumWidth(30)
        help_btn.setToolTip("如何获取Discord Token")
        help_btn.clicked.connect(self.show_token_help)
        token_layout.addWidget(help_btn)
        layout.addLayout(token_layout)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.active_checkbox = QCheckBox("启用账号")
        self.active_checkbox.setChecked(self.account.is_active)
        layout.addWidget(self.active_checkbox)

        channels_layout = QVBoxLayout()
        channels_layout.addWidget(QLabel("频道ID (可选，可多个):"))
        self.account_channels_input = QLineEdit()
        self.account_channels_input.setPlaceholderText("为空则监听所有频道，多个频道可用逗号、空格或换行分隔")
        self.account_channels_input.setToolTip("支持多个频道ID，留空表示全部频道")
        self.account_channels_input.setText(", ".join(map(str, self.account.target_channels)))
        channels_layout.addWidget(self.account_channels_input)
        channels_hint = QLabel("支持多个频道ID。留空表示全部频道。")
        channels_hint.setStyleSheet("color: gray;")
        channels_layout.addWidget(channels_hint)
        layout.addLayout(channels_layout)

        speed_hint = QLabel("回复速度已固定为 0 秒，命中后立即回复。")
        speed_hint.setStyleSheet("color: gray;")
        layout.addWidget(speed_hint)

        rules_title = QLabel(f"配置账号 '{self.account.alias}' 使用的规则：")
        rules_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(rules_title)

        rules_hint = QLabel("当前如果没有单独指定规则，就默认使用全部关键词。只有勾掉一部分后，才会按指定规则运行。")
        rules_hint.setStyleSheet("color: gray;")
        rules_hint.setWordWrap(True)
        layout.addWidget(rules_hint)

        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("按序号勾选:"))
        self.rule_range_input = QLineEdit()
        self.rule_range_input.setPlaceholderText("例如 1-20, 35, 40-45")
        self.rule_range_input.returnPressed.connect(self.select_rule_range)
        range_layout.addWidget(self.rule_range_input)

        select_range_btn = QPushButton("勾选区间")
        select_range_btn.clicked.connect(self.select_rule_range)
        range_layout.addWidget(select_range_btn)

        clear_range_btn = QPushButton("取消区间")
        clear_range_btn.clicked.connect(self.clear_rule_range)
        range_layout.addWidget(clear_range_btn)
        layout.addLayout(range_layout)

        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        self.checkboxes = []
        for index, rule in enumerate(self.rules, start=1):
            keyword_preview = rule.keywords[0] if rule.keywords else "无关键词"
            reply_preview = rule.reply[:30] + ("..." if len(rule.reply) > 30 else "")
            checkbox = QCheckBox(f"{index}. {keyword_preview} -> {reply_preview}")
            checkbox.setChecked(self.default_all_rules_mode or rule.id in self.account.rule_ids)
            checkbox.setToolTip(
                f"序号: {index}\n关键词: {', '.join(rule.keywords)}\n回复: {rule.reply}"
            )
            self.checkboxes.append((rule.id, checkbox))
            scroll_layout.addWidget(checkbox)

        if not self.rules:
            no_rules_label = QLabel("暂无可用规则，请先添加规则")
            no_rules_label.setStyleSheet("color: gray; font-style: italic;")
            scroll_layout.addWidget(no_rules_label)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        self.stats_label = QLabel()
        self.update_stats_label()
        layout.addWidget(self.stats_label)

        for _, checkbox in self.checkboxes:
            checkbox.stateChanged.connect(lambda _state, dialog=self: dialog.update_stats_label())

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(self.select_all_rules)
        buttons_layout.addWidget(select_all_btn)

        clear_all_btn = QPushButton("清空")
        clear_all_btn.clicked.connect(self.clear_all_rules)
        buttons_layout.addWidget(clear_all_btn)

        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept_and_validate)
        self.ok_btn.setDefault(True)
        buttons_layout.addWidget(self.ok_btn)
        layout.addLayout(buttons_layout)

        self.update_validation_status()

    def update_stats_label(self):
        selected_count = sum(1 for _, checkbox in self.checkboxes if checkbox.isChecked())
        total_count = len(self.checkboxes)
        if total_count > 0 and selected_count == total_count and self.default_all_rules_mode:
            self.stats_label.setText(f"当前默认使用全部规则（{total_count} 条）")
            return
        self.stats_label.setText(f"已选择 {selected_count}/{total_count} 个规则")

    def select_all_rules(self):
        self.default_all_rules_mode = False
        for _, checkbox in self.checkboxes:
            checkbox.setChecked(True)

    def clear_all_rules(self):
        self.default_all_rules_mode = False
        for _, checkbox in self.checkboxes:
            checkbox.setChecked(False)

    def select_rule_range(self):
        self.apply_rule_range(checked=True)

    def clear_rule_range(self):
        self.apply_rule_range(checked=False)

    def apply_rule_range(self, checked: bool):
        if not self.checkboxes:
            QMessageBox.information(self, "提示", "当前没有规则可供选择")
            return

        selection_text = self.rule_range_input.text().strip()
        if not selection_text:
            QMessageBox.information(self, "提示", "请输入规则序号范围，例如 1-20, 35, 40-45")
            return

        try:
            row_indices = parse_selection_ranges(selection_text, len(self.checkboxes))
        except ValueError as exc:
            QMessageBox.warning(self, "范围格式错误", str(exc))
            return

        current_states = [checkbox.isChecked() for _, checkbox in self.checkboxes]
        updated_states = apply_checked_indices(current_states, row_indices, checked=checked)
        self.default_all_rules_mode = False
        for state, (_, checkbox) in zip(updated_states, self.checkboxes):
            checkbox.setChecked(state)

        self.update_stats_label()

    def get_selected_rule_ids(self):
        selected_rule_ids = [rule_id for rule_id, checkbox in self.checkboxes if checkbox.isChecked()]
        if self.default_all_rules_mode and len(selected_rule_ids) == len(self.checkboxes):
            return []
        return selected_rule_ids

    def get_account_data(self):
        return {
            'token': self.token_input.text().strip(),
            'is_active': self.active_checkbox.isChecked(),
            'is_valid': self.current_is_valid,
            'user_info': self.current_user_info,
            'last_verified': self.current_last_verified,
            'selected_rule_ids': self.get_selected_rule_ids(),
            'target_channels': self.parse_target_channels(),
            'delay_min': 0.0,
            'delay_max': 0.0,
        }


class ReorderableRulesTable(RangeSelectableRowsTable):
    """支持整行拖拽排序的规则表格"""
    row_reordered = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropOverwriteMode(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        if event.source() is not self:
            super().dropEvent(event)
            return

        selected_rows = self.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            event.ignore()
            return

        source_row = selected_rows[0].row()
        target_row = self._target_row_from_event(event)
        if target_row < 0:
            event.ignore()
            return

        target_row = normalize_reorder_target_row(source_row, target_row, self.rowCount())

        if source_row == target_row:
            event.accept()
            return

        self.row_reordered.emit(source_row, target_row)
        event.accept()

    def _target_row_from_event(self, event) -> int:
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self.indexAt(position)

        if not index.isValid():
            return self.rowCount()

        indicator = self.dropIndicatorPosition()
        if indicator == QAbstractItemView.DropIndicatorPosition.BelowItem:
            return index.row() + 1
        if indicator == QAbstractItemView.DropIndicatorPosition.OnViewport:
            return self.rowCount()
        return index.row()


class WorkerThread(QThread):
    """工作线程，用于运行异步Discord客户端"""
    status_updated = Signal(dict)
    error_occurred = Signal(str)
    log_message = Signal(str)

    def __init__(self, discord_manager: DiscordManager):
        super().__init__()
        self.discord_manager = discord_manager
        self.running = False

    def run(self):
        """运行异步事件循环"""
        try:
            # 创建一个新的事件循环用于此线程
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

            asyncio.run(self._run_clients())
        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _run_clients(self):
        """启动客户端并定期更新状态"""
        try:
            self.log_message.emit("开始启动Discord客户端...")
            await self.discord_manager.start_all_clients()
            self.running = True

            # 等待所有客户端启动完成
            total_clients = len([acc for acc in self.discord_manager.accounts if acc.is_active and acc.is_valid])

            if total_clients > 0:
                # 简单的等待策略：定期检查客户端状态
                max_wait_time = 15  # 最多等待15秒
                waited_time = 0

                while waited_time < max_wait_time:
                    await asyncio.sleep(1)
                    waited_time += 1

                    # 检查有多少客户端已经启动
                    running_count = len([c for c in self.discord_manager.clients if c.is_running])

                    if running_count == total_clients:
                        # 所有客户端都启动了
                        break
                    elif running_count > 0 and waited_time >= 3:
                        # 至少有一个客户端启动，且已经等待了3秒
                        self.log_message.emit(f"📊 {running_count}/{total_clients} 个客户端已连接...")
                        break

                if waited_time >= max_wait_time:
                    self.log_message.emit("⚠️ 客户端连接超时，但将继续运行")

            # 现在检查最终状态
            status = self.discord_manager.get_status()
            self.status_updated.emit(status)

            running_count = len([acc for acc in status["accounts"] if acc["is_running"]])
            total_count = len(status["accounts"])

            if running_count > 0:
                self.log_message.emit(f"✅ Discord客户端启动完成 - {running_count}/{total_count} 个客户端运行中")
            else:
                self.log_message.emit("❌ Discord客户端启动失败 - 没有客户端成功连接")

            while self.running:
                try:
                    await asyncio.sleep(5)  # 每5秒更新一次状态，与UI定时器同步
                    if self.running:  # 再次检查是否还在运行
                        status = self.discord_manager.get_status()
                        self.status_updated.emit(status)
                except asyncio.CancelledError:
                    # 任务被取消，正常退出
                    break
                except Exception as e:
                    error_msg = f"状态更新出错: {e}"
                    self.log_message.emit(error_msg)
                    # 如果是网络错误，继续运行
                    if "SSL" in str(e) or "Connection" in str(e):
                        self.log_message.emit("检测到网络连接问题，继续监控...")
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            # 任务被取消，正常停止
            self.log_message.emit("接收到停止信号，正在停止客户端...")
        except Exception as e:
            error_msg = f"Discord客户端运行错误: {str(e)}"
            self.log_message.emit(error_msg)

            # 特殊处理SSL错误
            if "SSL" in str(e) or "APPLICATION_DATA_AFTER_CLOSE_NOTIFY" in str(e):
                self.log_message.emit("⚠️ 检测到SSL连接错误，这通常是网络问题，不影响功能")
            else:
                import traceback
                detailed_error = f"详细错误: {traceback.format_exc()}"
                self.log_message.emit(detailed_error)
                self.error_occurred.emit(error_msg)

        finally:
            # 确保在退出时停止所有客户端
            try:
                self.log_message.emit("正在清理资源...")
                await self.discord_manager.stop_all_clients()
                self.log_message.emit("Discord客户端已完全停止")
            except Exception as cleanup_error:
                self.log_message.emit(f"清理资源时出错: {cleanup_error}")

    def stop(self):
        """停止工作线程"""
        print("正在停止Discord工作线程...")
        self.running = False

        # 这种方式并不总是能优雅地停止 asyncio.run()，但在 WorkerThread 模型中，
        # 我们依靠 _run_clients 中的 loop check 和 sleep 来退出
        # 在GUI线程中我们只能等待 QThread 结束
        pass



class MainWindow(QMainWindow):
    # 定义信号
    log_signal = Signal(str, str)  # message, level

    def __init__(self, config_dir: Optional[str] = None, instance_name: Optional[str] = None):
        super().__init__()
        self.instance_name = resolve_runtime_instance_name(instance_name)
        self.runtime_config_dir = resolve_runtime_config_dir(config_dir, instance_name)
        self.discord_manager = DiscordManager(log_callback=self.add_log_thread_safe)
        self.config_manager = ConfigManager(config_dir=self.runtime_config_dir)
        self.data_dir = os.path.abspath(self.config_manager.config_dir)
        self.config_file_path = os.path.abspath(self.config_manager.config_file)

        self.worker_thread = None
        self._updating_accounts_table = False
        self.reply_history_page_size = 20
        self.reply_history_page = 0
        self.reply_history_items = []
        self.external_rule_sync_settings = self.default_external_rule_sync_settings()
        self.external_rule_sync_timer = QTimer(self)
        self.external_rule_sync_timer.timeout.connect(self.sync_rules_from_follow_file)

        self.init_ui()
        self.apply_external_rule_sync_settings_to_ui()
        self.load_config()

        # 连接日志信号
        self.log_signal.connect(self.add_log)

    def build_window_title(self) -> str:
        title = "Discord 自动回复工具"
        if self.instance_name:
            return f"{title} - {self.instance_name}"
        return title

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle(self.build_window_title())
        self.setGeometry(100, 100, 1200, 800)

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建主布局
        main_layout = QVBoxLayout(central_widget)

        # 创建标签页
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # 账号管理标签页
        self.create_accounts_tab()

        # 规则管理标签页
        self.create_rules_tab()

        # 状态监控标签页
        self.create_status_tab()

        # 底部控制栏
        self.create_control_bar(main_layout)

        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: white;
                font-weight: bold;
            }
            QPushButton {
                padding: 8px 16px;
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton#start_button {
                background-color: #107c10;
            }
            QPushButton#start_button:hover {
                background-color: #0b5a0b;
            }
            QPushButton#stop_button {
                background-color: #d13438;
            }
            QPushButton#stop_button:pressed {
                background-color: #a12629;
            }
            QPushButton[compactMoveButton="true"] {
                padding: 0px;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                font-size: 16px;
                font-weight: bold;
                color: #0b4f8a;
                background-color: #e8f3ff;
                border: 1px solid #7aaee6;
                border-radius: 4px;
            }
            QPushButton[compactMoveButton="true"]:hover {
                background-color: #d7ebff;
                border: 1px solid #5f9de0;
            }
            QPushButton[compactMoveButton="true"]:pressed {
                background-color: #c4e1ff;
                border: 1px solid #4a8fd7;
            }
            QPushButton[compactMoveButton="true"]:disabled {
                color: #90a4b7;
                background-color: #eef3f8;
                border: 1px solid #c8d5e3;
            }
        """)

    def create_accounts_tab(self):
        """创建账号管理标签页"""
        accounts_widget = QWidget()
        layout = QVBoxLayout(accounts_widget)

        # 标题和操作按钮
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Discord 账号管理"))

        header_layout.addWidget(QLabel("批量选择:"))
        self.account_range_input = QLineEdit()
        self.account_range_input.setPlaceholderText("例如 1-50, 80, 100-120")
        self.account_range_input.setToolTip("按表格序号批量选择账号，序号从 1 开始")
        self.account_range_input.returnPressed.connect(self.select_accounts_by_range)
        self.account_range_input.setMaximumWidth(260)
        header_layout.addWidget(self.account_range_input)

        select_range_btn = QPushButton("选择区间")
        select_range_btn.clicked.connect(self.select_accounts_by_range)
        header_layout.addWidget(select_range_btn)

        clear_selection_btn = QPushButton("清空选择")
        clear_selection_btn.clicked.connect(self.clear_account_selection)
        header_layout.addWidget(clear_selection_btn)

        header_layout.addStretch()

        revalidate_all_btn = QPushButton("重新验证所有")
        revalidate_all_btn.clicked.connect(self.revalidate_all_accounts)
        header_layout.addWidget(revalidate_all_btn)

        add_account_btn = QPushButton("添加账号")
        add_account_btn.clicked.connect(self.add_account)
        header_layout.addWidget(add_account_btn)

        layout.addLayout(header_layout)

        # 账号表格
        self.accounts_table = RangeSelectableRowsTable()
        self.accounts_table.setColumnCount(6)
        self.accounts_table.setHorizontalHeaderLabels(["用户名", "Token状态", "应用规则", "频道", "冷却", "操作"])
        accounts_header = self.accounts_table.horizontalHeader()
        accounts_header.setStretchLastSection(False)
        accounts_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        accounts_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        accounts_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        accounts_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        accounts_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        accounts_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.accounts_table.setAlternatingRowColors(True)
        self.accounts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.accounts_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.accounts_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.accounts_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.accounts_table.customContextMenuRequested.connect(self.show_accounts_context_menu)
        self.accounts_table.itemChanged.connect(self.handle_accounts_table_item_changed)
        layout.addWidget(self.accounts_table)

        # 统计信息
        self.accounts_stats_label = QLabel("总账号数: 0 | 启用账号数: 0")
        layout.addWidget(self.accounts_stats_label)

        self.tab_widget.addTab(accounts_widget, "账号管理")

    def create_rules_tab(self):
        """创建规则管理标签页"""
        rules_widget = QWidget()
        layout = QVBoxLayout(rules_widget)

        follow_group = QGroupBox("关键词文件跟随")
        follow_layout = QVBoxLayout(follow_group)

        follow_top_row = QHBoxLayout()
        self.external_rule_sync_enabled_checkbox = QCheckBox("启用文件跟随")
        self.external_rule_sync_enabled_checkbox.stateChanged.connect(self.on_external_rule_sync_settings_changed)
        follow_top_row.addWidget(self.external_rule_sync_enabled_checkbox)
        follow_top_row.addStretch()
        follow_layout.addLayout(follow_top_row)

        follow_path_row = QHBoxLayout()
        follow_path_row.addWidget(QLabel("文件路径"))
        self.external_rule_sync_path_input = QLineEdit()
        self.external_rule_sync_path_input.setPlaceholderText("选择要跟随的 xlsx/csv 文件")
        self.external_rule_sync_path_input.editingFinished.connect(self.on_external_rule_sync_settings_changed)
        follow_path_row.addWidget(self.external_rule_sync_path_input)

        self.external_rule_sync_browse_btn = QPushButton("选择文件")
        self.external_rule_sync_browse_btn.clicked.connect(self.browse_external_rule_sync_file)
        follow_path_row.addWidget(self.external_rule_sync_browse_btn)
        follow_layout.addLayout(follow_path_row)

        follow_interval_row = QHBoxLayout()
        follow_interval_row.addWidget(QLabel("检查间隔"))
        self.external_rule_sync_interval_spin = QSpinBox()
        self.external_rule_sync_interval_spin.setRange(5, 86400)
        self.external_rule_sync_interval_spin.setSuffix("秒")
        self.external_rule_sync_interval_spin.valueChanged.connect(self.on_external_rule_sync_settings_changed)
        follow_interval_row.addWidget(self.external_rule_sync_interval_spin)

        self.external_rule_sync_now_btn = QPushButton("立即同步")
        self.external_rule_sync_now_btn.clicked.connect(lambda: self.sync_rules_from_follow_file(force=True))
        follow_interval_row.addWidget(self.external_rule_sync_now_btn)
        follow_interval_row.addStretch()
        follow_layout.addLayout(follow_interval_row)

        self.external_rule_sync_status_label = QLabel("未启用文件跟随")
        self.external_rule_sync_status_label.setWordWrap(True)
        self.external_rule_sync_status_label.setStyleSheet("color: gray;")
        follow_layout.addWidget(self.external_rule_sync_status_label)
        layout.addWidget(follow_group)

        block_group = QGroupBox("整体匹配和屏蔽设置")
        block_layout = QVBoxLayout(block_group)
        self.block_settings_summary_label = QLabel()
        self.block_settings_summary_label.setWordWrap(True)
        block_layout.addWidget(self.block_settings_summary_label)

        block_controls_layout = QHBoxLayout()
        edit_block_settings_btn = QPushButton("编辑整体设置")
        edit_block_settings_btn.clicked.connect(self.edit_block_settings)
        block_controls_layout.addWidget(edit_block_settings_btn)
        block_controls_layout.addStretch()
        block_layout.addLayout(block_controls_layout)
        layout.addWidget(block_group)

        # 标题和添加按钮
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("自动回复规则管理（点击上下按钮调整优先级）"))

        # 搜索框
        self.rule_search_input = QLineEdit()
        self.rule_search_input.setPlaceholderText("搜索关键词...")
        self.rule_search_input.textChanged.connect(self.filter_rules)
        header_layout.addWidget(self.rule_search_input)

        header_layout.addStretch()

        import_rules_btn = QPushButton("Excel导入")
        import_rules_btn.clicked.connect(self.import_rules_from_excel)
        header_layout.addWidget(import_rules_btn)

        export_rules_btn = QPushButton("导出表格")
        export_rules_btn.clicked.connect(self.export_rules_table)
        header_layout.addWidget(export_rules_btn)

        add_rule_btn = QPushButton("添加规则")
        add_rule_btn.clicked.connect(self.add_rule)
        header_layout.addWidget(add_rule_btn)

        layout.addLayout(header_layout)

        batch_layout = QHBoxLayout()
        batch_layout.addWidget(QLabel("批量选择:"))
        self.rule_range_input = QLineEdit()
        self.rule_range_input.setPlaceholderText("例如 1-20, 35, 40-45")
        self.rule_range_input.setToolTip("按当前列表序号批量选择规则；如果正在搜索，则按筛选后的可见顺序计算")
        self.rule_range_input.returnPressed.connect(self.select_rules_by_range)
        self.rule_range_input.setMaximumWidth(260)
        batch_layout.addWidget(self.rule_range_input)

        select_rule_range_btn = QPushButton("选择区间")
        select_rule_range_btn.clicked.connect(self.select_rules_by_range)
        batch_layout.addWidget(select_rule_range_btn)

        select_all_rules_btn = QPushButton("全选")
        select_all_rules_btn.clicked.connect(self.select_all_rules)
        batch_layout.addWidget(select_all_rules_btn)

        clear_rule_selection_btn = QPushButton("清空选择")
        clear_rule_selection_btn.clicked.connect(self.clear_rule_selection)
        batch_layout.addWidget(clear_rule_selection_btn)

        delete_selected_rules_btn = QPushButton("删除选中")
        delete_selected_rules_btn.clicked.connect(self.remove_selected_rules)
        batch_layout.addWidget(delete_selected_rules_btn)

        batch_layout.addSpacing(12)
        batch_layout.addWidget(QLabel("全部规则回复账号数"))
        self.bulk_reply_account_count_combo = QComboBox()
        self.bulk_reply_account_count_combo.addItems(["1个账号", "2个账号", "3个账号"])
        batch_layout.addWidget(self.bulk_reply_account_count_combo)

        apply_bulk_reply_count_btn = QPushButton("应用到全部")
        apply_bulk_reply_count_btn.clicked.connect(self.apply_reply_account_count_to_all_rules)
        batch_layout.addWidget(apply_bulk_reply_count_btn)

        batch_layout.addStretch()
        batch_hint = QLabel("支持 Ctrl/Cmd/Shift 多选")
        batch_hint.setStyleSheet("color: gray;")
        batch_layout.addWidget(batch_hint)
        layout.addLayout(batch_layout)

        # 规则表格
        self.rules_table = ReorderableRulesTable()
        self.rules_table.setColumnCount(5)
        self.rules_table.setHorizontalHeaderLabels(["关键词", "回复内容", "匹配类型", "回复账号数", "操作"])
        rules_header = self.rules_table.horizontalHeader()
        rules_header.setStretchLastSection(False)
        rules_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        rules_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in range(2, 4):
            rules_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        rules_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.rules_table.setColumnWidth(4, 220)
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rules_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.rules_table.setDragEnabled(False)
        self.rules_table.setAcceptDrops(False)
        self.rules_table.viewport().setAcceptDrops(False)
        self.rules_table.setDropIndicatorShown(False)
        self.rules_table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.rules_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.rules_table.customContextMenuRequested.connect(self.show_rules_context_menu)
        layout.addWidget(self.rules_table)

        # 统计信息
        self.rules_overview_label = QLabel("总规则数: 0 | 启用规则数: 0")
        layout.addWidget(self.rules_overview_label)

        self.tab_widget.addTab(rules_widget, "规则管理")

    def create_status_tab(self):
        """创建状态监控标签页"""
        status_widget = QWidget()
        layout = QVBoxLayout(status_widget)

        # 账号状态表格
        accounts_group = QGroupBox("账号状态")
        accounts_layout = QVBoxLayout(accounts_group)

        self.status_accounts_table = QTableWidget()
        self.status_accounts_table.setColumnCount(5)
        self.status_accounts_table.setHorizontalHeaderLabels(["别名", "状态", "运行状态", "回复数", "冷却"])
        self.status_accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        accounts_layout.addWidget(self.status_accounts_table)

        layout.addWidget(accounts_group)

        history_group = QGroupBox("最近回复记录")
        history_layout = QVBoxLayout(history_group)
        self.reply_history_table = QTableWidget()
        self.reply_history_table.setColumnCount(6)
        self.reply_history_table.setHorizontalHeaderLabels(["时间", "账号", "触发关键词", "客户消息", "消息链接", "机器人回复"])
        history_header = self.reply_history_table.horizontalHeader()
        history_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        history_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        history_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.reply_history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.reply_history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.reply_history_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.reply_history_table.cellClicked.connect(self.open_reply_history_message_link)
        history_layout.addWidget(self.reply_history_table)

        history_controls = QHBoxLayout()
        self.copy_reply_history_btn = QPushButton("复制选中内容")
        self.copy_reply_history_btn.clicked.connect(self.copy_selected_reply_history_text)
        history_controls.addWidget(self.copy_reply_history_btn)

        history_controls.addStretch()

        self.reply_history_prev_btn = QPushButton("上一页")
        self.reply_history_prev_btn.clicked.connect(self.show_previous_reply_history_page)
        history_controls.addWidget(self.reply_history_prev_btn)

        self.reply_history_page_label = QLabel("第 1/1 页")
        history_controls.addWidget(self.reply_history_page_label)

        self.reply_history_next_btn = QPushButton("下一页")
        self.reply_history_next_btn.clicked.connect(self.show_next_reply_history_page)
        history_controls.addWidget(self.reply_history_next_btn)
        history_layout.addLayout(history_controls)
        layout.addWidget(history_group)

        # 规则统计
        rules_group = QGroupBox("规则统计")
        rules_layout = QVBoxLayout(rules_group)

        self.status_rules_stats_label = QLabel("总规则数: 0 | 激活规则数: 0")
        rules_layout.addWidget(self.status_rules_stats_label)

        layout.addWidget(rules_group)

        storage_group = QGroupBox("数据存储")
        storage_layout = QVBoxLayout(storage_group)

        self.data_dir_label = QLabel()
        self.data_dir_label.setWordWrap(True)
        self.data_dir_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        storage_layout.addWidget(self.data_dir_label)

        storage_controls = QHBoxLayout()
        open_data_dir_btn = QPushButton("打开数据目录")
        open_data_dir_btn.clicked.connect(self.open_data_directory)
        storage_controls.addWidget(open_data_dir_btn)

        copy_data_dir_btn = QPushButton("复制路径")
        copy_data_dir_btn.clicked.connect(self.copy_data_directory_path)
        storage_controls.addWidget(copy_data_dir_btn)
        storage_controls.addStretch()
        storage_layout.addLayout(storage_controls)
        layout.addWidget(storage_group)

        # 轮换设置
        rotation_group = QGroupBox("账号轮换设置")
        rotation_layout = QVBoxLayout(rotation_group)

        # 启用轮换
        self.rotation_enabled_checkbox = QCheckBox("启用账号轮换")
        self.rotation_enabled_checkbox.setToolTip("启用后，每次只会由一个账号发送，发送后进入冷却，下次自动切换到没冷却的账号。")
        self.rotation_enabled_checkbox.stateChanged.connect(self.on_rotation_enabled_changed)
        rotation_layout.addWidget(self.rotation_enabled_checkbox)

        # 轮换间隔设置
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("账号冷却时间(秒):"))
        self.rotation_interval_spin = QSpinBox()
        self.rotation_interval_spin.setRange(1, 3600)  # 1秒到1小时
        self.rotation_interval_spin.setValue(10)  # 默认10秒
        self.rotation_interval_spin.setSuffix("秒")
        self.rotation_interval_spin.setEnabled(False)  # 默认禁用
        self.rotation_interval_spin.valueChanged.connect(self.on_rotation_interval_changed)
        interval_layout.addWidget(self.rotation_interval_spin)
        interval_layout.addStretch()
        rotation_layout.addLayout(interval_layout)

        # 轮换状态
        self.rotation_status_label = QLabel("轮换模式: 未启用")
        rotation_layout.addWidget(self.rotation_status_label)

        layout.addWidget(rotation_group)

        # 日志显示
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)

        # 日志控制按钮
        log_controls = QHBoxLayout()
        log_controls.addWidget(QLabel("日志:"))

        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.clicked.connect(self.clear_log)
        log_controls.addWidget(clear_log_btn)

        log_controls.addStretch()

        auto_scroll_checkbox = QCheckBox("自动滚动")
        auto_scroll_checkbox.setChecked(True)
        self.auto_scroll_log = auto_scroll_checkbox.isChecked()
        auto_scroll_checkbox.stateChanged.connect(self.toggle_auto_scroll)
        log_controls.addWidget(auto_scroll_checkbox)

        log_layout.addLayout(log_controls)

        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 12))  # 等宽字体，便于查看
        self.log_text.document().setMaximumBlockCount(1000)
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)
        self.refresh_data_directory_status()

        self.tab_widget.addTab(status_widget, "状态监控")

    def create_control_bar(self, parent_layout):
        """创建底部控制栏"""
        control_layout = QHBoxLayout()

        # 启动按钮
        self.start_button = QPushButton("启动")
        self.start_button.setObjectName("start_button")
        self.start_button.clicked.connect(self.start_bot)
        control_layout.addWidget(self.start_button)

        # 停止按钮
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stop_button")
        self.stop_button.clicked.connect(self.stop_bot)
        self.stop_button.setEnabled(False)
        control_layout.addWidget(self.stop_button)

        # 配置导入导出
        control_layout.addStretch()

        export_btn = QPushButton("导出配置")
        export_btn.clicked.connect(self.export_config)
        control_layout.addWidget(export_btn)

        import_btn = QPushButton("导入配置")
        import_btn.clicked.connect(self.import_config)
        control_layout.addWidget(import_btn)

        parent_layout.addLayout(control_layout)

    def load_config(self):
        """加载配置"""
        accounts, rules, block_settings = self.config_manager.load_config()
        self.discord_manager.accounts = accounts
        self.discord_manager.rules = rules
        self.discord_manager.block_settings = block_settings
        self.external_rule_sync_settings = self.normalize_external_rule_sync_settings(
            self.config_manager.external_rule_sync_settings
        )
        self.apply_external_rule_sync_settings_to_ui()

        # 加载轮换设置（暂时使用默认值，后续可以扩展配置文件）
        # TODO: 从配置文件加载轮换设置

        self.prune_block_settings_account_tokens()
        self.update_accounts_list()
        self.update_rules_list()
        self.update_status()

        if self.external_rule_sync_settings.get("enabled") and self.external_rule_sync_settings.get("file_path"):
            self.sync_rules_from_follow_file(force=False)

    def save_config(self):
        """保存配置"""
        self.prune_block_settings_account_tokens()
        self.config_manager.save_config(
            self.discord_manager.accounts,
            self.discord_manager.rules,
            self.discord_manager.block_settings,
            external_rule_sync_settings=self.external_rule_sync_settings,
        )

    def default_external_rule_sync_settings(self):
        return self.config_manager._default_external_rule_sync_settings()

    def normalize_external_rule_sync_settings(self, settings=None):
        return self.config_manager._normalize_external_rule_sync_settings(settings)

    def set_external_rule_sync_status(self, text: str, color: str = "gray"):
        if not hasattr(self, "external_rule_sync_status_label"):
            return
        self.external_rule_sync_status_label.setText(text)
        self.external_rule_sync_status_label.setStyleSheet(f"color: {color};")

    def refresh_external_rule_sync_timer(self):
        settings = self.normalize_external_rule_sync_settings(self.external_rule_sync_settings)
        self.external_rule_sync_settings = settings

        should_run = bool(settings.get("enabled") and settings.get("file_path"))
        interval_ms = max(5000, int(settings.get("interval_seconds", 60)) * 1000)

        if should_run:
            self.external_rule_sync_timer.start(interval_ms)
        else:
            self.external_rule_sync_timer.stop()

        if hasattr(self, "external_rule_sync_now_btn"):
            self.external_rule_sync_now_btn.setEnabled(should_run)

    def apply_external_rule_sync_settings_to_ui(self):
        settings = self.normalize_external_rule_sync_settings(self.external_rule_sync_settings)
        self.external_rule_sync_settings = settings

        widget_updates = [
            (getattr(self, "external_rule_sync_enabled_checkbox", None), lambda widget: widget.setChecked(settings["enabled"])),
            (getattr(self, "external_rule_sync_path_input", None), lambda widget: widget.setText(settings["file_path"])),
            (getattr(self, "external_rule_sync_interval_spin", None), lambda widget: widget.setValue(settings["interval_seconds"])),
        ]

        for widget, update in widget_updates:
            if widget is None:
                continue
            widget.blockSignals(True)
            try:
                update(widget)
            finally:
                widget.blockSignals(False)

        if hasattr(self, "external_rule_sync_interval_spin"):
            self.external_rule_sync_interval_spin.setEnabled(settings["enabled"])

        self.refresh_external_rule_sync_timer()

        if not settings["enabled"]:
            self.set_external_rule_sync_status("未启用文件跟随", "gray")
        elif not settings["file_path"]:
            self.set_external_rule_sync_status("已启用文件跟随，但还没有选择文件", "gray")
        else:
            self.set_external_rule_sync_status(
                f"已启用文件跟随，等待检查：{os.path.basename(settings['file_path'])}",
                "gray",
            )

    def on_external_rule_sync_settings_changed(self):
        previous_settings = dict(self.external_rule_sync_settings)
        updated_settings = self.normalize_external_rule_sync_settings({
            "enabled": self.external_rule_sync_enabled_checkbox.isChecked(),
            "file_path": self.external_rule_sync_path_input.text().strip(),
            "interval_seconds": self.external_rule_sync_interval_spin.value(),
            "last_signature": previous_settings.get("last_signature", ""),
        })
        self.external_rule_sync_settings = updated_settings
        self.apply_external_rule_sync_settings_to_ui()
        self.save_config()

        file_changed = previous_settings.get("file_path", "") != updated_settings.get("file_path", "")
        enabled_now = updated_settings.get("enabled") and updated_settings.get("file_path")
        enabled_before = previous_settings.get("enabled") and previous_settings.get("file_path")
        if enabled_now and (file_changed or not enabled_before):
            self.sync_rules_from_follow_file(force=True)

    def browse_external_rule_sync_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择要跟随的关键词文件",
            "",
            "Excel / CSV 文件 (*.xlsx *.csv)",
        )
        if not filename:
            return

        self.external_rule_sync_path_input.setText(filename)
        self.on_external_rule_sync_settings_changed()

    @staticmethod
    def _normalize_follow_rule_keywords(keywords: List[str]) -> tuple[str, ...]:
        return tuple(
            keyword.strip().lower()
            for keyword in keywords or []
            if str(keyword).strip()
        )

    def _build_external_rule_sync_signature(self, imported_rules: List[dict]) -> str:
        payload = "\n".join(
            f"{chr(31).join(item.get('keywords', []))}{chr(30)}{item.get('reply', '')}"
            for item in imported_rules
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def sync_rules_from_follow_file(self, force: bool = False):
        settings = self.normalize_external_rule_sync_settings(self.external_rule_sync_settings)
        self.external_rule_sync_settings = settings

        if not settings.get("enabled"):
            self.refresh_external_rule_sync_timer()
            self.set_external_rule_sync_status("未启用文件跟随", "gray")
            return False

        file_path = settings.get("file_path", "").strip()
        if not file_path:
            self.refresh_external_rule_sync_timer()
            self.set_external_rule_sync_status("已启用文件跟随，但还没有选择文件", "gray")
            return False

        if not os.path.exists(file_path):
            self.refresh_external_rule_sync_timer()
            self.set_external_rule_sync_status(f"跟随文件不存在：{file_path}", "red")
            return False

        try:
            imported_rules, skipped_rows = parse_rule_import_file(file_path)
        except Exception as exc:
            self.refresh_external_rule_sync_timer()
            self.set_external_rule_sync_status(f"读取跟随文件失败：{exc}", "red")
            self.add_log(f"关键词文件跟随读取失败: {exc}", "error")
            return False

        signature = self._build_external_rule_sync_signature(imported_rules)
        if not force and signature == settings.get("last_signature", ""):
            self.refresh_external_rule_sync_timer()
            self.set_external_rule_sync_status(
                f"文件无变化：{os.path.basename(file_path)}",
                "gray",
            )
            return False

        manual_rules = [
            rule for rule in self.discord_manager.rules
            if getattr(rule, "sync_source", "") != "follow_file"
        ]
        existing_follow_rules = [
            rule for rule in self.discord_manager.rules
            if getattr(rule, "sync_source", "") == "follow_file"
        ]

        existing_follow_rule_map = {}
        existing_occurrence_map = {}
        for rule in existing_follow_rules:
            keyword_key = self._normalize_follow_rule_keywords(rule.keywords)
            occurrence_index = existing_occurrence_map.get(keyword_key, 0)
            existing_follow_rule_map[(keyword_key, occurrence_index)] = rule
            existing_occurrence_map[keyword_key] = occurrence_index + 1

        synced_rules = []
        imported_occurrence_map = {}
        for item in imported_rules:
            keywords = [keyword.strip() for keyword in item.get("keywords", []) if keyword.strip()]
            reply_text = str(item.get("reply", "") or "").strip()
            if not keywords or not reply_text:
                continue

            keyword_key = self._normalize_follow_rule_keywords(keywords)
            occurrence_index = imported_occurrence_map.get(keyword_key, 0)
            imported_occurrence_map[keyword_key] = occurrence_index + 1

            existing_rule = existing_follow_rule_map.get((keyword_key, occurrence_index))
            if existing_rule is not None:
                existing_rule.keywords = keywords
                existing_rule.reply = reply_text
                existing_rule.match_type = MatchType.PARTIAL
                existing_rule.target_channels = []
                existing_rule.delay_min = 0.0
                existing_rule.delay_max = 0.0
                existing_rule.case_sensitive = False
                existing_rule.sync_source = "follow_file"
                synced_rules.append(existing_rule)
                continue

            synced_rules.append(Rule(
                id=f"follow_{int(time.time() * 1000)}_{len(synced_rules)}",
                keywords=keywords,
                reply=reply_text,
                match_type=MatchType.PARTIAL,
                target_channels=[],
                delay_min=0.0,
                delay_max=0.0,
                is_active=True,
                ignore_replies=True,
                ignore_mentions=True,
                case_sensitive=False,
                exclude_keywords=[],
                reply_account_count=1,
                sync_source="follow_file",
            ))

        self.discord_manager.rules = manual_rules + synced_rules

        valid_rule_ids = {rule.id for rule in self.discord_manager.rules}
        for account in self.discord_manager.accounts:
            if account.rule_ids:
                account.rule_ids = [rule_id for rule_id in account.rule_ids if rule_id in valid_rule_ids]

        settings["last_signature"] = signature
        self.external_rule_sync_settings = self.normalize_external_rule_sync_settings(settings)

        self.update_rules_list()
        self.update_accounts_list()
        self.save_config()
        self.refresh_external_rule_sync_timer()

        status_text = f"已同步 {len(synced_rules)} 条关键词，来源：{os.path.basename(file_path)}"
        if skipped_rows:
            status_text += f"，跳过 {skipped_rows} 行"
        self.set_external_rule_sync_status(status_text, "green")
        self.add_log(status_text, "success")
        return True

    def update_accounts_list(self):
        """更新账号表格显示"""
        self._updating_accounts_table = True
        try:
            self.accounts_table.setRowCount(len(self.discord_manager.accounts))

            for row, account in enumerate(self.discord_manager.accounts):
                # 用户名
                username = account.alias  # 使用alias属性，它会自动生成用户名
                username_item = QTableWidgetItem(username)
                username_item.setData(Qt.ItemDataRole.UserRole, account.token)  # 使用token作为标识
                username_item.setFlags(username_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.accounts_table.setItem(row, 0, username_item)

                # Token状态
                token_type = account.user_info.get('token_type') if account.user_info and isinstance(account.user_info, dict) else None
                if account.is_valid:
                    if token_type == 'bot':
                        token_status = "有效 (Bot)"
                        bg_color = QColor(144, 238, 144)  # 浅绿色
                    elif token_type == 'user':
                        token_status = "有效 (用户)"
                        bg_color = QColor(255, 255, 224)  # 浅黄色 - 警告色
                    else:
                        token_status = "有效"
                        bg_color = QColor(144, 238, 144)  # 浅绿色
                else:
                    token_status = "无效"
                    bg_color = QColor(255, 182, 193)  # 浅红色

                token_status_item = QTableWidgetItem(token_status)
                token_status_item.setBackground(bg_color)
                token_status_item.setFlags(token_status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                # 添加工具提示
                if token_type == 'user':
                    token_status_item.setToolTip("用户Token可以验证但无法连接，请使用Bot Token")
                elif token_type == 'bot':
                    token_status_item.setToolTip("Bot Token，完全支持连接和消息处理")

                self.accounts_table.setItem(row, 1, token_status_item)

                # 应用规则（显示关联的规则数量）
                total_rules = len(self.discord_manager.rules)
                uses_all_rules = total_rules > 0 and not account.rule_ids
                applied_rules = total_rules if uses_all_rules else len(account.rule_ids)
                rules_text = f"全部({total_rules})" if uses_all_rules else f"{applied_rules}/{total_rules}"
                rules_item = QTableWidgetItem(rules_text)
                rules_item.setFlags(rules_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if applied_rules > 0:
                    rules_item.setBackground(QColor(173, 216, 230))  # 浅蓝色
                else:
                    rules_item.setBackground(QColor(240, 240, 240))  # 浅灰色
                if uses_all_rules:
                    rules_item.setToolTip("当前没有单独指定规则，默认使用全部规则")
                rules_item.setData(Qt.ItemDataRole.UserRole, account.rule_ids)  # 存储规则ID列表
                self.accounts_table.setItem(row, 2, rules_item)

                # 频道范围
                channel_text = self.format_account_channels(account.target_channels)
                channel_item = QTableWidgetItem(channel_text)
                channel_item.setToolTip("双击可直接编辑。留空或输入“全部”表示所有频道。")
                self.accounts_table.setItem(row, 3, channel_item)

                # 冷却状态
                cooldown_item = self.build_account_cooldown_item(account.cooldown_until)
                self.accounts_table.setItem(row, 4, cooldown_item)

                # 操作按钮
                edit_btn = QPushButton("编辑")
                edit_btn.clicked.connect(lambda checked, token=account.token: self.edit_account_by_token(token))

                validate_btn = QPushButton("验证")
                validate_btn.clicked.connect(lambda checked, token=account.token: self.revalidate_account_by_token(token))

                delete_btn = QPushButton("删除")
                delete_btn.clicked.connect(lambda checked, token=account.token: self.remove_account_by_token(token))

                # 创建按钮容器
                button_widget = QWidget()
                button_layout = QHBoxLayout(button_widget)
                button_layout.setContentsMargins(2, 2, 2, 2)
                button_layout.addWidget(edit_btn)
                button_layout.addWidget(validate_btn)
                button_layout.addWidget(delete_btn)

                self.accounts_table.setCellWidget(row, 5, button_widget)
        finally:
            self._updating_accounts_table = False

        # 更新统计信息
        total_accounts = len(self.discord_manager.accounts)
        active_accounts = len([acc for acc in self.discord_manager.accounts if acc.is_active])
        self.accounts_stats_label.setText(f"总账号数: {total_accounts} | 启用账号数: {active_accounts}")
        self.update_block_settings_summary()

    @staticmethod
    def format_account_channels(channel_ids: List[int]) -> str:
        if not channel_ids:
            return "全部"
        return ", ".join(map(str, channel_ids))

    @staticmethod
    def build_account_cooldown_item(cooldown_until: Optional[float]) -> QTableWidgetItem:
        cooldown_text = format_remaining_duration(cooldown_until, current_time=time.time())
        cooldown_item = QTableWidgetItem(cooldown_text)
        cooldown_item.setFlags(cooldown_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if cooldown_text == "可用":
            cooldown_item.setBackground(QColor(226, 239, 218))
        else:
            cooldown_item.setBackground(QColor(255, 242, 204))
        return cooldown_item

    def update_account_cooldown_cells(self, status_accounts: Optional[List[dict]] = None):
        if not hasattr(self, "accounts_table"):
            return

        status_by_token = {
            account_status["token"]: account_status
            for account_status in (status_accounts or [])
        }

        for row, account in enumerate(self.discord_manager.accounts):
            cooldown_until = account.cooldown_until
            if account.token in status_by_token:
                cooldown_until = status_by_token[account.token].get("cooldown_until")

            cooldown_item = self.build_account_cooldown_item(cooldown_until)
            self.accounts_table.setItem(row, 4, cooldown_item)

    def handle_accounts_table_item_changed(self, item):
        if self._updating_accounts_table or item is None:
            return

        if item.column() != 3:
            return

        token_item = self.accounts_table.item(item.row(), 0)
        if token_item is None:
            return

        account_token = token_item.data(Qt.ItemDataRole.UserRole)
        account = next((acc for acc in self.discord_manager.accounts if acc.token == account_token), None)
        if account is None:
            return

        raw_text = item.text().strip()
        normalized_text = raw_text.lower()

        try:
            if not raw_text or normalized_text in {"全部", "all", "*"}:
                parsed_channels = []
            else:
                parsed_channels = parse_channel_ids(raw_text)
        except ValueError as exc:
            self._updating_accounts_table = True
            try:
                item.setText(self.format_account_channels(account.target_channels))
            finally:
                self._updating_accounts_table = False
            QMessageBox.warning(self, "频道格式错误", str(exc))
            return

        account.target_channels = parsed_channels
        self.save_config()

        self._updating_accounts_table = True
        try:
            item.setText(self.format_account_channels(account.target_channels))
            item.setToolTip("双击可直接编辑。留空或输入“全部”表示所有频道。")
        finally:
            self._updating_accounts_table = False

        self.add_log(f"账号 '{account.alias}' 的频道设置已更新", "success")

    def update_rules_list(self):
        """更新规则表格显示"""
        self.discord_manager.invalidate_rule_matcher()
        self.rules_table.setRowCount(len(self.discord_manager.rules))

        for row, rule in enumerate(self.discord_manager.rules):
            # 关键词
            keywords_str = ", ".join(rule.keywords[:2])
            if len(rule.keywords) > 2:
                keywords_str += "..."
            keywords_item = QTableWidgetItem(keywords_str)
            keywords_item.setData(Qt.ItemDataRole.UserRole, rule.id)
            keywords_item.setToolTip(", ".join(rule.keywords))  # 悬停显示所有关键词
            self.rules_table.setItem(row, 0, keywords_item)

            # 回复内容
            reply_display = rule.reply[:30] + "..." if len(rule.reply) > 30 else rule.reply
            reply_item = QTableWidgetItem(reply_display)
            reply_item.setToolTip(rule.reply)  # 悬停显示完整回复
            self.rules_table.setItem(row, 1, reply_item)

            # 匹配类型
            match_type_name = {
                "partial": "部分匹配",
                "exact": "精确匹配",
                "regex": "正则表达式"
            }[rule.match_type.value]
            match_item = QTableWidgetItem(match_type_name)
            self.rules_table.setItem(row, 2, match_item)

            # 回复账号数
            reply_account_count = max(1, min(3, int(getattr(rule, "reply_account_count", 1) or 1)))
            reply_count_item = QTableWidgetItem(f"{reply_account_count}个账号")
            reply_count_item.setToolTip("命中这条规则后，会由几个账号一起回复")
            self.rules_table.setItem(row, 3, reply_count_item)

            # 操作按钮
            move_up_btn = QPushButton("↑")
            move_up_btn.setProperty("compactMoveButton", True)
            move_up_btn.setToolTip("上移一位")
            move_up_btn.setFixedSize(28, 28)
            move_up_btn.setEnabled(can_move_adjacent_row(row, len(self.discord_manager.rules), -1))
            move_up_btn.clicked.connect(lambda checked, rule_id=rule.id: self.move_rule_by_id(rule_id, -1))

            move_down_btn = QPushButton("↓")
            move_down_btn.setProperty("compactMoveButton", True)
            move_down_btn.setToolTip("下移一位")
            move_down_btn.setFixedSize(28, 28)
            move_down_btn.setEnabled(can_move_adjacent_row(row, len(self.discord_manager.rules), 1))
            move_down_btn.clicked.connect(lambda checked, rule_id=rule.id: self.move_rule_by_id(rule_id, 1))

            edit_btn = QPushButton("编辑")
            edit_btn.setMinimumWidth(48)
            edit_btn.clicked.connect(lambda checked, rule_id=rule.id: self.edit_rule_by_id(rule_id))

            delete_btn = QPushButton("删除")
            delete_btn.setMinimumWidth(48)
            delete_btn.clicked.connect(lambda checked, rule_id=rule.id: self.remove_rule_by_id(rule_id))

            # 创建按钮容器
            button_widget = QWidget()
            button_layout = QHBoxLayout(button_widget)
            button_layout.setContentsMargins(2, 2, 2, 2)
            button_layout.setSpacing(4)
            button_layout.addWidget(move_up_btn)
            button_layout.addWidget(move_down_btn)
            button_layout.addWidget(edit_btn)
            button_layout.addWidget(delete_btn)

            self.rules_table.setCellWidget(row, 4, button_widget)

        # 更新统计信息
        total_rules = len(self.discord_manager.rules)
        active_rules = len([rule for rule in self.discord_manager.rules if rule.is_active])
        self.rules_overview_label.setText(f"总规则数: {total_rules} | 启用规则数: {active_rules}")

        # 应用当前搜索过滤
        self.filter_rules()
        self.update_block_settings_summary()

    def prune_block_settings_account_tokens(self):
        valid_tokens = {account.token for account in self.discord_manager.accounts}
        current_tokens = getattr(self.discord_manager.block_settings, "account_tokens", [])
        self.discord_manager.block_settings.account_tokens = [
            token for token in current_tokens if token in valid_tokens
        ]

    def sync_block_settings_account_token(self, old_token: str, new_token: str):
        current_tokens = list(getattr(self.discord_manager.block_settings, "account_tokens", []))
        if old_token not in current_tokens:
            return

        updated_tokens = []
        for token in current_tokens:
            updated_token = new_token if token == old_token else token
            if updated_token not in updated_tokens:
                updated_tokens.append(updated_token)
        self.discord_manager.block_settings.account_tokens = updated_tokens

    def update_block_settings_summary(self):
        if not hasattr(self, "block_settings_summary_label"):
            return

        block_settings = self.discord_manager.block_settings
        keyword_count = len(block_settings.blocked_keywords)
        user_count = len(block_settings.blocked_user_ids)
        channel_count = len(block_settings.blocked_channel_ids)

        if block_settings.account_scope == "all":
            scope_text = "全部账号"
        else:
            selected_accounts = [
                account.alias
                for account in self.discord_manager.accounts
                if account.token in block_settings.account_tokens
            ]
            if selected_accounts:
                if len(selected_accounts) <= 3:
                    scope_text = "指定账号：" + "、".join(selected_accounts)
                else:
                    scope_text = f"指定账号：{len(selected_accounts)} 个"
            else:
                scope_text = "指定账号：0 个"

        summary_parts = [
            f"屏蔽关键词 {keyword_count} 项",
            f"屏蔽用户ID {user_count} 个",
            f"屏蔽频道 {channel_count} 个" if channel_count else "屏蔽频道 跟随账号范围",
            "忽略回复消息 开启" if block_settings.ignore_replies else "忽略回复消息 关闭",
            "忽略@消息 开启" if block_settings.ignore_mentions else "忽略@消息 关闭",
            f"生效范围 {scope_text}",
        ]

        if keyword_count == 0 and user_count == 0:
            summary_parts.insert(0, "当前还没有设置屏蔽关键词或屏蔽用户")

        self.block_settings_summary_label.setText(" | ".join(summary_parts))

    def edit_block_settings(self):
        dialog = BlockSettingsDialog(
            self,
            block_settings=self.discord_manager.block_settings,
            accounts=self.discord_manager.accounts,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.discord_manager.block_settings = dialog.get_block_settings()
        self.save_config()
        self.update_block_settings_summary()
        QMessageBox.information(self, "成功", "整体设置已更新")

    def move_rule_by_step(self, source_row: int, step: int):
        total_rules = len(self.discord_manager.rules)
        if not can_move_adjacent_row(source_row, total_rules, step):
            return

        target_row = get_adjacent_row_index(source_row, total_rules, step)
        self.move_rule_row(source_row, target_row)

    def get_rule_index_by_id(self, rule_id: str) -> int:
        return find_item_index_by_id(self.discord_manager.rules, rule_id)

    def move_rule_by_id(self, rule_id: str, step: int):
        rule_index = self.get_rule_index_by_id(rule_id)
        if rule_index < 0:
            QMessageBox.warning(self, "错误", "规则不存在，列表将刷新")
            self.update_rules_list()
            return

        self.move_rule_by_step(rule_index, step)

    def move_rule_row(self, source_row: int, target_row: int):
        """更新底层规则顺序"""
        if self.rule_search_input.text().strip():
            QMessageBox.information(self, "提示", "请先清空搜索条件，再调整规则排序")
            self.update_rules_list()
            return

        total_rules = len(self.discord_manager.rules)
        if not (0 <= source_row < total_rules and 0 <= target_row < total_rules):
            return

        self.discord_manager.rules = move_item_in_list(
            self.discord_manager.rules,
            source_row,
            target_row,
        )

        self.update_rules_list()
        self.save_config()
        self.rules_table.selectRow(target_row)
        target_item = self.rules_table.item(target_row, 0)
        if target_item:
            self.rules_table.scrollToItem(target_item, QAbstractItemView.ScrollHint.PositionAtCenter)

        self.add_log(f"规则顺序已更新：第 {source_row + 1} 行 -> 第 {target_row + 1} 行", "info")

    def filter_rules(self):
        """根据搜索关键词过滤规则显示"""
        search_text = self.rule_search_input.text().strip().lower()

        for row in range(self.rules_table.rowCount()):
            show_row = True
            if search_text:
                # 检查关键词列是否包含搜索文本
                keywords_item = self.rules_table.item(row, 0)
                if keywords_item:
                    keywords = keywords_item.toolTip().lower() if keywords_item.toolTip() else keywords_item.text().lower()
                    if search_text not in keywords:
                        show_row = False

            self.rules_table.setRowHidden(row, not show_row)

    def update_status(self):
        """更新状态显示"""
        try:
            status = self.discord_manager.get_status()
            self.update_account_cooldown_cells(status["accounts"])

            # 更新账号表格
            account_count = len(status["accounts"])
            self.status_accounts_table.setRowCount(account_count)

            for i, acc in enumerate(status["accounts"]):
                # 只在数据真正改变时才更新，避免不必要的UI重绘
                current_alias = self.status_accounts_table.item(i, 0)
                if not current_alias or current_alias.text() != acc["alias"]:
                    self.status_accounts_table.setItem(i, 0, QTableWidgetItem(acc["alias"]))

                current_active = self.status_accounts_table.item(i, 1)
                active_text = "启用" if acc["is_active"] else "禁用"
                if not current_active or current_active.text() != active_text:
                    self.status_accounts_table.setItem(i, 1, QTableWidgetItem(active_text))

                running_status = "运行中" if acc["is_running"] else "未运行"
                current_running = self.status_accounts_table.item(i, 2)
                if not current_running or current_running.text() != running_status:
                    item = QTableWidgetItem(running_status)
                    if acc["is_running"]:
                        item.setBackground(QColor(144, 238, 144))  # 浅绿色
                    else:
                        item.setBackground(QColor(255, 182, 193))  # 浅红色
                    self.status_accounts_table.setItem(i, 2, item)

                reply_count_text = str(acc.get("reply_count", 0))
                current_reply_count = self.status_accounts_table.item(i, 3)
                if not current_reply_count or current_reply_count.text() != reply_count_text:
                    self.status_accounts_table.setItem(i, 3, QTableWidgetItem(reply_count_text))

                cooldown_text = format_remaining_duration(acc.get("cooldown_until"), current_time=time.time())
                current_cooldown = self.status_accounts_table.item(i, 4)
                if not current_cooldown or current_cooldown.text() != cooldown_text:
                    self.status_accounts_table.setItem(i, 4, QTableWidgetItem(cooldown_text))

            self.update_reply_history_table(status.get("recent_replies", []))

            # 更新规则统计
            rules_text = f"总规则数: {status['rules_count']} | 激活规则数: {status['active_rules']}"
            if self.status_rules_stats_label.text() != rules_text:
                self.status_rules_stats_label.setText(rules_text)

        except Exception as e:
            # 静默处理状态更新错误，避免影响用户体验
            print(f"状态更新错误: {e}")

    def update_reply_history_table(self, reply_history_items):
        self.reply_history_items = list(reply_history_items or [])
        total_items = len(self.reply_history_items)
        total_pages = max(1, (total_items + self.reply_history_page_size - 1) // self.reply_history_page_size)
        if self.reply_history_page >= total_pages:
            self.reply_history_page = total_pages - 1

        start_index = self.reply_history_page * self.reply_history_page_size
        end_index = start_index + self.reply_history_page_size
        visible_items = self.reply_history_items[start_index:end_index]

        self.reply_history_table.setRowCount(len(visible_items))
        for row, item_data in enumerate(visible_items):
            self.reply_history_table.setItem(row, 0, QTableWidgetItem(item_data.get("time_text", "")))
            self.reply_history_table.setItem(row, 1, QTableWidgetItem(item_data.get("account_alias", "")))
            self.reply_history_table.setItem(row, 2, QTableWidgetItem(item_data.get("keyword", "")))
            self.reply_history_table.setItem(row, 3, QTableWidgetItem(item_data.get("customer_message", "")))
            self.reply_history_table.setItem(row, 4, self.create_reply_history_link_item(item_data.get("message_link", "")))
            self.reply_history_table.setItem(row, 5, QTableWidgetItem(item_data.get("reply_content", "")))

        self.reply_history_page_label.setText(f"第 {self.reply_history_page + 1}/{total_pages} 页")
        self.reply_history_prev_btn.setEnabled(self.reply_history_page > 0)
        self.reply_history_next_btn.setEnabled(self.reply_history_page + 1 < total_pages)

    def show_previous_reply_history_page(self):
        if self.reply_history_page <= 0:
            return
        self.reply_history_page -= 1
        self.update_reply_history_table(self.reply_history_items)

    def show_next_reply_history_page(self):
        total_items = len(self.reply_history_items)
        total_pages = max(1, (total_items + self.reply_history_page_size - 1) // self.reply_history_page_size)
        if self.reply_history_page + 1 >= total_pages:
            return
        self.reply_history_page += 1
        self.update_reply_history_table(self.reply_history_items)

    def copy_selected_reply_history_text(self):
        selected_indexes = sorted(
            self.reply_history_table.selectedIndexes(),
            key=lambda index: (index.row(), index.column()),
        )
        if not selected_indexes:
            QMessageBox.information(self, "提示", "请先选中要复制的内容")
            return

        row_text_map = {}
        for index in selected_indexes:
            table_item = self.reply_history_table.item(index.row(), index.column())
            cell_text = str(index.data() or "")
            if table_item is not None:
                link_value = str(table_item.data(Qt.ItemDataRole.UserRole) or "").strip()
                if link_value:
                    cell_text = link_value
            row_text_map.setdefault(index.row(), []).append(cell_text)

        copied_text = "\n".join("\t".join(cells) for _, cells in sorted(row_text_map.items()))
        QApplication.clipboard().setText(copied_text)
        self.add_log("已复制选中的回复记录内容", "info")

    def create_reply_history_link_item(self, message_link: str) -> QTableWidgetItem:
        link_value = str(message_link or "").strip()
        display_text = "打开消息" if link_value else "-"
        link_item = QTableWidgetItem(display_text)
        link_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        link_item.setData(Qt.ItemDataRole.UserRole, link_value)
        if link_value:
            font = link_item.font()
            font.setUnderline(True)
            link_item.setFont(font)
            link_item.setForeground(QColor("#0b63ce"))
            link_item.setToolTip(link_value)
        return link_item

    def open_reply_history_message_link(self, row: int, column: int):
        if column != 4:
            return

        link_item = self.reply_history_table.item(row, column)
        if link_item is None:
            return

        message_link = str(link_item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not message_link:
            return

        QDesktopServices.openUrl(QUrl(message_link))

    def refresh_data_directory_status(self):
        if not hasattr(self, "data_dir_label"):
            return

        instance_text = self.instance_name if self.instance_name else "默认共享目录"
        summary_lines = [
            f"当前实例: {instance_text}",
            f"当前数据目录: {self.data_dir}",
            f"配置文件: {self.config_file_path}",
            "多开时可用 --instance 名称，或设置 DISCORD_REPLY_DATA_DIR 到独立目录。",
        ]
        self.data_dir_label.setText("\n".join(summary_lines))
        self.data_dir_label.setToolTip(self.config_file_path)

    def open_data_directory(self):
        self.config_manager.ensure_config_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.data_dir))

    def copy_data_directory_path(self):
        QApplication.clipboard().setText(self.data_dir)
        self.add_log("数据目录路径已复制", "info")

    def show_accounts_context_menu(self, position):
        """显示账号右键菜单"""
        selected_rows = set()
        for item in self.accounts_table.selectedItems():
            selected_rows.add(item.row())

        menu = QMenu()

        if len(selected_rows) == 1:
            # 单个账号的菜单
            edit_action = menu.addAction("编辑账号")
            validate_action = menu.addAction("重新验证")
            delete_action = menu.addAction("删除账号")
        elif len(selected_rows) > 1:
            # 多个账号的菜单
            delete_multiple_action = menu.addAction(f"删除选中的 {len(selected_rows)} 个账号")
        else:
            # 没有选中账号时的菜单
            return

        action = menu.exec(self.accounts_table.mapToGlobal(position))

        if len(selected_rows) == 1:
            current_row = list(selected_rows)[0]
            if action == edit_action:
                token_item = self.accounts_table.item(current_row, 0)
                if token_item:
                    token = token_item.data(Qt.ItemDataRole.UserRole)
                    self.edit_account_by_token(token)
            elif action == validate_action:
                token_item = self.accounts_table.item(current_row, 0)
                if token_item:
                    token = token_item.data(Qt.ItemDataRole.UserRole)
                    self.revalidate_account_by_token(token)
            elif action == delete_action:
                token_item = self.accounts_table.item(current_row, 0)
                if token_item:
                    token = token_item.data(Qt.ItemDataRole.UserRole)
                    self.remove_account_by_token(token)
        elif len(selected_rows) > 1:
            if action == delete_multiple_action:
                self.remove_multiple_accounts(list(selected_rows))

    def clear_account_selection(self):
        """清空账号表格选择"""
        self.accounts_table.clearSelection()

    def select_accounts_by_range(self):
        """按序号区间批量选择账号"""
        total_accounts = len(self.discord_manager.accounts)
        if total_accounts == 0:
            QMessageBox.information(self, "提示", "当前没有账号可供选择")
            return

        selection_text = self.account_range_input.text().strip()
        if not selection_text:
            QMessageBox.information(self, "提示", "请输入要选择的序号范围，例如 1-50, 80, 100-120")
            return

        try:
            row_indices = parse_selection_ranges(selection_text, total_accounts)
        except ValueError as exc:
            QMessageBox.warning(self, "范围格式错误", str(exc))
            return

        if not row_indices:
            QMessageBox.information(self, "提示", "没有匹配到可选择的账号序号")
            return

        self.accounts_table.select_rows_by_indices(row_indices)

        first_item = self.accounts_table.item(row_indices[0], 0)
        if first_item:
            self.accounts_table.scrollToItem(first_item, QAbstractItemView.ScrollHint.PositionAtTop)

        self.add_log(f"已按序号批量选择 {len(row_indices)} 个账号", "info")

    def show_rules_context_menu(self, position):
        """显示规则右键菜单"""
        selected_rows = set()
        for item in self.rules_table.selectedItems():
            selected_rows.add(item.row())

        menu = QMenu()

        if len(selected_rows) == 1:
            # 单个规则的菜单
            current_row = list(selected_rows)[0]
            edit_action = menu.addAction("编辑规则")
            delete_action = menu.addAction("删除规则")
        elif len(selected_rows) > 1:
            # 多个规则的菜单
            delete_multiple_action = menu.addAction(f"删除选中的 {len(selected_rows)} 个规则")
        else:
            # 没有选中规则时的菜单
            return

        action = menu.exec(self.rules_table.mapToGlobal(position))

        if len(selected_rows) == 1:
            current_row = list(selected_rows)[0]
            if action == edit_action:
                self.edit_rule_by_index(current_row)
            elif action == delete_action:
                self.remove_rule_by_index(current_row)
        elif len(selected_rows) > 1:
            if action == delete_multiple_action:
                self.remove_multiple_rules(list(selected_rows))

    def get_visible_rule_row_indices(self) -> List[int]:
        return [
            row_index
            for row_index in range(self.rules_table.rowCount())
            if not self.rules_table.isRowHidden(row_index)
        ]

    def clear_rule_selection(self):
        self.rules_table.clearSelection()

    def select_all_rules(self):
        visible_row_indices = self.get_visible_rule_row_indices()
        if not visible_row_indices:
            QMessageBox.information(self, "提示", "当前没有可供选择的规则")
            return

        self.rules_table.select_rows_by_indices(visible_row_indices)

        first_item = self.rules_table.item(visible_row_indices[0], 0)
        if first_item:
            self.rules_table.scrollToItem(first_item, QAbstractItemView.ScrollHint.PositionAtTop)

        self.add_log(f"已选择 {len(visible_row_indices)} 条规则", "info")

    def select_rules_by_range(self):
        visible_row_indices = self.get_visible_rule_row_indices()
        if not visible_row_indices:
            QMessageBox.information(self, "提示", "当前没有规则可供选择")
            return

        selection_text = self.rule_range_input.text().strip()
        if not selection_text:
            QMessageBox.information(self, "提示", "请输入要选择的序号范围，例如 1-20, 35, 40-45")
            return

        try:
            visible_selection_indices = parse_selection_ranges(selection_text, len(visible_row_indices))
        except ValueError as exc:
            QMessageBox.warning(self, "范围格式错误", str(exc))
            return

        if not visible_selection_indices:
            QMessageBox.information(self, "提示", "没有匹配到可选择的规则序号")
            return

        target_row_indices = [visible_row_indices[index] for index in visible_selection_indices]
        self.rules_table.select_rows_by_indices(target_row_indices)

        first_item = self.rules_table.item(target_row_indices[0], 0)
        if first_item:
            self.rules_table.scrollToItem(first_item, QAbstractItemView.ScrollHint.PositionAtTop)

        self.add_log(f"已按序号选择 {len(target_row_indices)} 条规则", "info")

    def remove_selected_rules(self):
        selected_rows = sorted({model_index.row() for model_index in self.rules_table.selectionModel().selectedRows()})
        if not selected_rows:
            QMessageBox.information(self, "提示", "请先选中要删除的规则")
            return

        self.remove_multiple_rules(selected_rows)

    def apply_reply_account_count_to_all_rules(self):
        if not self.discord_manager.rules:
            QMessageBox.information(self, "提示", "当前没有规则可供修改")
            return

        reply_account_count = self.bulk_reply_account_count_combo.currentIndex() + 1
        for rule in self.discord_manager.rules:
            rule.reply_account_count = reply_account_count

        self.update_rules_list()
        self.save_config()
        self.add_log(f"已将全部规则的回复账号数改为 {reply_account_count} 个账号", "success")
        QMessageBox.information(self, "成功", f"已将全部规则改为 {reply_account_count} 个账号回复")

    def add_account(self):
        """添加新账号"""
        dialog = AccountDialog(self, discord_manager=self.discord_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_account_data()

            if not data['token']:
                QMessageBox.warning(self, "错误", "Token不能为空")
                return

            # 检查Token是否重复
            if any(acc.token == data['token'] for acc in self.discord_manager.accounts):
                QMessageBox.warning(self, "错误", "该Token已存在")
                return

            # 使用异步方法添加账号
            import asyncio
            try:
                async def add_account_async():
                    success, message = await self.discord_manager.add_account_async(data['token'])
                    # 设置激活状态
                    if success and data['token'] in [acc.token for acc in self.discord_manager.accounts]:
                        for acc in self.discord_manager.accounts:
                            if acc.token == data['token']:
                                acc.is_active = data['is_active']
                                acc.target_channels = data.get('target_channels', [])
                                break
                    return success, message

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success, message = loop.run_until_complete(add_account_async())

                if success:
                    self.add_log(message, "success")
                    self.update_accounts_list()
                    self.save_config()
                    QMessageBox.information(self, "成功", message)
                else:
                    self.log_text.append(f"❌ {message}")
                    QMessageBox.warning(self, "添加失败", message)

            except Exception as e:
                error_msg = f"添加账号时出错: {str(e)}"
                self.add_log(error_msg, "error")
                QMessageBox.critical(self, "错误", error_msg)

    def edit_account_by_token(self, token: str):
        """编辑账号：支持替换 token 与配置规则"""
        account_index = next((index for index, acc in enumerate(self.discord_manager.accounts) if acc.token == token), -1)
        if account_index < 0:
            QMessageBox.warning(self, "错误", "账号不存在")
            return

        account = self.discord_manager.accounts[account_index]

        dialog = AccountEditDialog(self, account, self.discord_manager.rules)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_account_data()
            new_token = data['token']

            if not new_token:
                QMessageBox.warning(self, "错误", "Token不能为空")
                return

            if any(
                acc.token == new_token and index != account_index
                for index, acc in enumerate(self.discord_manager.accounts)
            ):
                QMessageBox.warning(self, "错误", "该Token已存在")
                return

            replacement_account = Account(
                token=new_token,
                is_active=data['is_active'],
                is_valid=data.get('is_valid', False),
                last_verified=data.get('last_verified'),
                user_info=data.get('user_info'),
                rule_ids=data.get('selected_rule_ids', list(account.rule_ids)),
                target_channels=data.get('target_channels', list(account.target_channels)),
                delay_min=0.0,
                delay_max=0.0,
                last_sent_time=account.last_sent_time if new_token == account.token else None,
                cooldown_until=account.cooldown_until if new_token == account.token else None,
                rate_limit_until=account.rate_limit_until if new_token == account.token else None,
                reply_count=account.reply_count if new_token == account.token else 0,
            )

            self.discord_manager.accounts = replace_item_preserving_order(
                self.discord_manager.accounts,
                account_index,
                replacement_account,
            )
            self.sync_block_settings_account_token(account.token, new_token)

            self.add_log(f"账号位置 {account_index + 1} 编辑成功，顺序保持不变", "success")
            self.update_accounts_list()
            self.save_config()
            QMessageBox.information(self, "成功", f"账号已更新，并保留在第 {account_index + 1} 位")

    def replace_account_by_token(self, token: str):
        """兼容旧入口：替换账号"""
        self.edit_account_by_token(token)

    def edit_account_by_alias(self, alias):
        """兼容旧入口：通过别名编辑账号"""
        account = next((acc for acc in self.discord_manager.accounts if acc.alias == alias), None)
        if not account:
            QMessageBox.warning(self, "错误", "账号不存在")
            return

        self.edit_account_by_token(account.token)

    def edit_account_rules(self, token: str):
        """兼容旧入口：编辑账号应用的规则"""
        self.edit_account_by_token(token)

    def revalidate_all_accounts(self):
        """重新验证所有账号"""
        if not self.discord_manager.accounts:
            QMessageBox.information(self, "提示", "没有账号需要验证")
            return

        self.add_log("开始重新验证所有账号的Token", "info")

        # 在新的事件循环中运行异步验证
        import asyncio
        try:
            async def revalidate_all():
                results = await self.discord_manager.revalidate_all_accounts()
                return results

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(revalidate_all())

            success_count = 0
            fail_count = 0

            for result in results:
                alias = result['alias']
                is_valid = result['is_valid']
                error_msg = result['error_msg']

                if is_valid:
                    user_info = result['user_info']
                    if user_info and isinstance(user_info, dict):
                        username = f"{user_info.get('name', 'Unknown')}#{user_info.get('discriminator', '0000')}"
                        self.add_log(f"账号 '{alias}' 验证成功 - 用户名: {username}", "success")
                    else:
                        self.add_log(f"账号 '{alias}' 验证成功", "success")
                    success_count += 1
                else:
                    self.add_log(f"账号 '{alias}' 验证失败: {error_msg}", "error")
                    fail_count += 1

            self.add_log(f"批量验证完成 - 成功: {success_count}, 失败: {fail_count}", "info")
            self.update_accounts_list()
            self.save_config()

            QMessageBox.information(
                self, "批量验证完成",
                f"验证完成\n成功: {success_count}\n失败: {fail_count}"
            )

        except Exception as e:
            error_msg = f"批量验证过程中出错: {str(e)}"
            self.add_log(error_msg, "error")
            QMessageBox.critical(self, "验证错误", error_msg)

    def revalidate_account_by_token(self, token: str):
        """重新验证账号Token"""
        account = next((acc for acc in self.discord_manager.accounts if acc.token == token), None)
        if account:
            self.add_log(f"正在重新验证账号 '{account.alias}' 的Token", "info")
        else:
            self.add_log("账号不存在", "error")
            return

        # 在新的事件循环中运行异步验证
        import asyncio
        try:
            async def revalidate():
                success, message = await self.discord_manager.revalidate_account(account.token)
                return success, message

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, message = loop.run_until_complete(revalidate())

            if success:
                self.add_log(message, "success")
                QMessageBox.information(self, "验证成功", message)
            else:
                self.log_text.append(f"❌ {message}")
                QMessageBox.warning(self, "验证失败", message)

            self.update_accounts_list()
            self.save_config()

        except Exception as e:
            error_msg = f"验证过程中出错: {str(e)}"
            self.add_log(error_msg, "error")
            QMessageBox.critical(self, "验证错误", error_msg)

    def revalidate_account_by_alias(self, alias):
        """兼容旧入口：通过别名重新验证账号"""
        account = next((acc for acc in self.discord_manager.accounts if acc.alias == alias), None)
        if not account:
            self.add_log("账号不存在", "error")
            return

        self.revalidate_account_by_token(account.token)

    def remove_account_by_token(self, token):
        """通过token删除账号"""
        account = next((acc for acc in self.discord_manager.accounts if acc.token == token), None)
        if not account:
            QMessageBox.warning(self, "错误", "账号不存在")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除账号 '{account.alias}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.remove_account(token)
            self.prune_block_settings_account_tokens()
            self.add_log(f"账号 '{account.alias}' 已删除", "info")
            self.update_accounts_list()
            self.save_config()

    def remove_account_by_alias(self, alias):
        """通过别名删除账号"""
        account = next((acc for acc in self.discord_manager.accounts if acc.alias == alias), None)
        if not account:
            QMessageBox.warning(self, "错误", "账号不存在")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除账号 '{alias}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.remove_account(account.token)
            self.prune_block_settings_account_tokens()
            self.update_accounts_list()
            self.save_config()

    def remove_multiple_accounts(self, indices):
        """批量删除多个账号"""
        indices.sort(reverse=True)  # 从大到小排序，避免删除时索引变化

        reply = QMessageBox.question(
            self, "确认批量删除",
            f"确定要删除选中的 {len(indices)} 个账号吗？\n此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            for index in indices:
                try:
                    # 获取账号信息用于日志
                    if index < len(self.discord_manager.accounts):
                        account = self.discord_manager.accounts[index]
                        account_name = account.alias
                        self.discord_manager.remove_account(account.token)
                        deleted_count += 1
                        self.add_log(f"账号 '{account_name}' 已删除", "info")
                except (IndexError, ValueError) as e:
                    # 账号可能已经被删除，跳过
                    continue

            self.prune_block_settings_account_tokens()
            self.update_accounts_list()
            self.save_config()
            self.add_log(f"成功删除 {deleted_count} 个账号", "success")


    def add_rule(self):
        """添加新规则"""
        dialog = RuleDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_rule_data()

            if not data['keywords'] or not data['reply']:
                QMessageBox.warning(self, "错误", "关键词和回复内容不能为空")
                return

            self.discord_manager.add_rule(
                data['keywords'],
                data['reply'],
                MatchType(data['match_type']),
                reply_account_count=data.get('reply_account_count', 1),
            )

            # 设置激活状态
            if self.discord_manager.rules:
                self.discord_manager.rules[-1].is_active = data['is_active']

            self.update_rules_list()
            self.save_config()
            QMessageBox.information(self, "成功", "规则添加成功")

    def edit_rule_by_index(self, index):
        """通过索引编辑规则"""
        if not 0 <= index < len(self.discord_manager.rules):
            QMessageBox.warning(self, "错误", "规则不存在，列表将刷新")
            self.update_rules_list()
            return

        rule = self.discord_manager.rules[index]
        dialog = RuleDialog(self, rule)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_rule_data()

            if not data['keywords'] or not data['reply']:
                QMessageBox.warning(self, "错误", "关键词和回复内容不能为空")
                return

            self.discord_manager.update_rule(
                index,
                keywords=data['keywords'],
                reply=data['reply'],
                match_type=MatchType(data['match_type']),
                reply_account_count=data.get('reply_account_count', 1),
                is_active=data['is_active'],
            )

            self.update_rules_list()
            self.save_config()
            QMessageBox.information(self, "成功", "规则编辑成功")

    def import_rules_from_excel(self):
        """通过 Excel 或 CSV 批量导入规则"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "导入规则",
            "",
            "Excel 文件 (*.xlsx);;CSV 文件 (*.csv)",
        )
        if not filename:
            return

        try:
            imported_rules, skipped_rows = parse_rule_import_file(filename)
        except ValueError as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", f"读取文件时出错：{exc}")
            return

        if not imported_rules:
            QMessageBox.warning(self, "导入失败", "没有读到可导入的规则，请检查前两列是否分别为关键词和回复内容。")
            return

        imported_count = 0
        for item in imported_rules:
            self.discord_manager.add_rule(
                item["keywords"],
                item["reply"],
                MatchType.PARTIAL,
                reply_account_count=1,
            )
            if self.discord_manager.rules:
                self.discord_manager.rules[-1].is_active = True
                imported_count += 1

        self.update_rules_list()
        self.save_config()

        message = f"成功导入 {imported_count} 条规则"
        if skipped_rows:
            message += f"，跳过 {skipped_rows} 行空值或缺列数据"
        QMessageBox.information(self, "成功", message)

    def export_rules_table(self):
        """导出规则表格为 CSV"""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "导出规则表格",
            "rules.csv",
            "CSV 文件 (*.csv)",
        )
        if not filename:
            return

        rows = []
        for index, rule in enumerate(self.discord_manager.rules, start=1):
            match_type_name = {
                "partial": "部分匹配",
                "exact": "精确匹配",
                "regex": "正则表达式",
            }[rule.match_type.value]
            rows.append([
                index,
                " | ".join(rule.keywords),
                rule.reply,
                match_type_name,
                f"{getattr(rule, 'reply_account_count', 1)}个账号",
                "是" if rule.is_active else "否",
            ])

        try:
            with open(filename, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["序号", "关键词", "回复内容", "匹配类型", "回复账号数", "是否启用"])
                writer.writerows(rows)
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", f"导出规则表格时出错：{exc}")
            return

        QMessageBox.information(self, "成功", f"规则表格已导出到：{filename}")

    def edit_rule_by_id(self, rule_id: str):
        rule_index = self.get_rule_index_by_id(rule_id)
        if rule_index < 0:
            QMessageBox.warning(self, "错误", "规则不存在，列表将刷新")
            self.update_rules_list()
            return

        self.edit_rule_by_index(rule_index)

    def remove_rule_by_index(self, index):
        """通过索引删除规则"""
        if not 0 <= index < len(self.discord_manager.rules):
            QMessageBox.warning(self, "错误", "规则不存在，列表将刷新")
            self.update_rules_list()
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除规则 {index+1} 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.remove_rule(index)
            self.update_rules_list()
            self.save_config()

    def remove_rule_by_id(self, rule_id: str):
        rule_index = self.get_rule_index_by_id(rule_id)
        if rule_index < 0:
            QMessageBox.warning(self, "错误", "规则不存在，列表将刷新")
            self.update_rules_list()
            return

        self.remove_rule_by_index(rule_index)

    def remove_multiple_rules(self, indices):
        """批量删除多个规则"""
        indices.sort(reverse=True)  # 从大到小排序，避免删除时索引变化

        reply = QMessageBox.question(
            self, "确认批量删除",
            f"确定要删除选中的 {len(indices)} 个规则吗？\n此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            for index in indices:
                try:
                    self.discord_manager.remove_rule(index)
                    deleted_count += 1
                except IndexError:
                    # 规则可能已经被删除，跳过
                    continue

            self.update_rules_list()
            self.save_config()
            self.add_log(f"成功删除 {deleted_count} 个规则", "success")




    def start_bot(self):
        """启动机器人"""
        self.add_log("🔄 正在检查启动条件...", "info")

        if not self.discord_manager.accounts:
            self.add_log("❌ 启动失败：请先添加至少一个账号", "error")
            QMessageBox.warning(self, "错误", "请先添加至少一个账号")
            return

        if not self.discord_manager.rules:
            self.add_log("❌ 启动失败：请先添加至少一个规则", "error")
            QMessageBox.warning(self, "错误", "请先添加至少一个规则")
            return

        # 检查是否有有效的账号
        valid_accounts = [acc for acc in self.discord_manager.accounts if acc.is_active and acc.is_valid]
        if not valid_accounts:
            self.add_log("❌ 启动失败：没有有效的账号（请先验证Token）", "error")
            QMessageBox.warning(self, "错误", "没有有效的账号，请先验证Token")
            return

        try:
            self.add_log("🚀 正在启动Discord机器人...", "info")

            self.worker_thread = WorkerThread(self.discord_manager)
            self.worker_thread.status_updated.connect(self.update_status)
            self.worker_thread.error_occurred.connect(self.on_error)
            self.worker_thread.log_message.connect(self.add_log)
            self.worker_thread.start()

            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)

            self.add_log("✅ 机器人启动命令已发送，正在连接Discord服务器...", "success")

        except Exception as e:
            error_msg = f"启动失败: {str(e)}"
            self.add_log(f"❌ {error_msg}", "error")
            QMessageBox.critical(self, "错误", error_msg)

    def stop_bot(self):
        """停止机器人"""
        if self.worker_thread:
            self.add_log("正在停止机器人...", "info")

            # 设置停止标志
            self.worker_thread.running = False

            # 等待线程完成，最多等待12秒（增加等待时间）
            if self.worker_thread.wait(12000):  # 增加等待时间到12秒
                self.add_log("机器人停止完成", "success")
            else:
                self.add_log("机器人停止超时，但后台清理将继续进行", "warning")

            # 清理线程
            self.worker_thread = None

            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

            # 强制更新状态显示
            self.update_status()

            # 添加最终日志
            self.add_log("机器人已停止", "info")

    def add_log(self, message, level="info"):
        """添加日志"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        safe_message = html.escape(str(message))

        # 根据级别设置颜色和前缀
        if level == "error":
            colored_msg = f'<span style="color: red;">[{timestamp}] ❌ {safe_message}</span>'
        elif level == "warning":
            colored_msg = f'<span style="color: orange;">[{timestamp}] ⚠️ {safe_message}</span>'
        elif level == "success":
            colored_msg = f'<span style="color: green;">[{timestamp}] ✅ {safe_message}</span>'
        elif level == "info":
            colored_msg = f'<span style="color: blue;">[{timestamp}] ℹ️ {safe_message}</span>'
        else:
            colored_msg = f'[{timestamp}] {safe_message}'

        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        if not self.log_text.document().isEmpty():
            cursor.insertBlock()
        cursor.insertHtml(colored_msg)
        self.log_text.setTextCursor(cursor)

        # 自动滚动到底部
        if self.auto_scroll_log:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.log_text.setTextCursor(cursor)

    def add_log_thread_safe(self, message, level="info"):
        """线程安全的日志添加"""
        self.log_signal.emit(message, level)

    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self.add_log("日志已清空", "info")

    def toggle_auto_scroll(self, state):
        """切换自动滚动"""
        self.auto_scroll_log = state == 2  # 2表示选中状态

    def on_rotation_enabled_changed(self, state):
        """轮换启用状态改变"""
        enabled = state == 2  # 2表示选中状态
        self.rotation_interval_spin.setEnabled(enabled)

        # 更新DiscordManager设置
        self.discord_manager.rotation_enabled = enabled
        if enabled:
            self.discord_manager.rotation_interval = self.rotation_interval_spin.value()  # 直接使用秒
            self.rotation_status_label.setText(f"轮换模式: 已启用 (冷却{self.rotation_interval_spin.value()}秒)")
        else:
            self.rotation_status_label.setText("轮换模式: 未启用")

        # 保存配置
        self.save_config()

        status = "启用" if enabled else "禁用"
        self.add_log(f"账号轮换模式已{status}", "info")

    def on_rotation_interval_changed(self, value):
        """轮换冷却时间改变时立即生效"""
        self.discord_manager.rotation_interval = value
        if self.rotation_enabled_checkbox.isChecked():
            self.rotation_status_label.setText(f"轮换模式: 已启用 (冷却{value}秒)")
            self.save_config()
            self.add_log(f"账号轮换冷却时间已更新为 {value} 秒", "info")

    def on_error(self, error_msg):
        """错误处理"""
        QMessageBox.critical(self, "错误", f"运行时错误: {error_msg}")
        self.add_log(f"运行时错误: {error_msg}", "error")

    def export_config(self):
        """导出配置"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出配置", "", "JSON 文件 (*.json)"
        )
        if filename:
            self.config_manager.external_rule_sync_settings = self.normalize_external_rule_sync_settings(
                self.external_rule_sync_settings
            )
            if self.config_manager.export_config(
                filename,
                self.discord_manager.accounts,
                self.discord_manager.rules,
                self.discord_manager.block_settings,
            ):
                QMessageBox.information(self, "成功", "配置导出成功")
            else:
                QMessageBox.warning(self, "错误", "配置导出失败")

    def import_config(self):
        """导入配置"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "导入配置", "", "JSON 文件 (*.json)"
        )
        if filename:
            accounts, rules, block_settings = self.config_manager.import_config(filename)
            if (
                accounts or
                rules or
                block_settings.blocked_keywords or
                block_settings.blocked_user_ids or
                block_settings.blocked_channel_ids or
                not block_settings.ignore_replies or
                not block_settings.ignore_mentions or
                self.config_manager.external_rule_sync_settings.get("enabled") or
                bool(self.config_manager.external_rule_sync_settings.get("file_path"))
            ):
                self.discord_manager.accounts = accounts
                self.discord_manager.rules = rules
                self.discord_manager.block_settings = block_settings
                self.external_rule_sync_settings = self.normalize_external_rule_sync_settings(
                    self.config_manager.external_rule_sync_settings
                )
                self.apply_external_rule_sync_settings_to_ui()
                self.prune_block_settings_account_tokens()
                self.update_accounts_list()
                self.update_rules_list()
                self.save_config()
                QMessageBox.information(self, "成功", "配置导入成功")
            else:
                QMessageBox.warning(self, "错误", "配置导入失败")


def parse_runtime_options(argv: Optional[List[str]] = None) -> tuple[List[str], str, str]:
    raw_args = list(argv if argv is not None else sys.argv)
    if not raw_args:
        raw_args = ["discord-reply"]

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--data-dir", dest="data_dir")
    parser.add_argument("--instance", dest="instance_name")
    parsed_args, remaining_args = parser.parse_known_args(raw_args[1:])

    qt_args = [raw_args[0], *remaining_args]
    config_dir = resolve_runtime_config_dir(parsed_args.data_dir, parsed_args.instance_name)
    instance_name = resolve_runtime_instance_name(parsed_args.instance_name)
    return qt_args, config_dir, instance_name


def main(argv: Optional[List[str]] = None):
    """主函数"""
    qt_args, config_dir, instance_name = parse_runtime_options(argv)
    app = QApplication(qt_args)
    app.setStyle('Fusion')  # 使用更现代的样式

    # 设置应用程序属性，确保在macOS上正确显示
    app.setApplicationName("Discord Auto Reply")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("DiscordAutoReply")

    window = MainWindow(config_dir=config_dir, instance_name=instance_name)
    window.show()
    window.raise_()  # 确保窗口在前台显示
    window.activateWindow()  # 激活窗口

    # 创建定时器定期更新状态
    timer = QTimer()
    timer.timeout.connect(window.update_status)
    timer.start(5000)  # 每5秒更新一次

    # 运行Qt应用程序事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
