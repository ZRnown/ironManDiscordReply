import sys
import asyncio
import os
import time
from typing import List, Optional
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QListWidget, QListWidgetItem, QPushButton, QLabel,
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFileDialog, QSplitter, QProgressBar,
    QDialog, QMenu, QScrollArea, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QItemSelectionModel
from PySide6.QtGui import QFont, QIcon, QColor

# 添加src目录到Python路径（确保打包后能找到模块）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from discord_client import DiscordManager, Account, Rule, MatchType
from config_manager import ConfigManager
from gui_helpers import (
    apply_checked_indices,
    build_row_selection_range,
    can_move_adjacent_row,
    find_item_index_by_id,
    get_adjacent_row_index,
    merge_flag_bits,
    move_item_in_list,
    normalize_reorder_target_row,
    parse_selection_ranges,
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
        self.resize(500, 250)

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

    def get_account_data(self):
        """获取账号数据"""
        return {
            'token': self.token_input.text().strip(),
            'is_active': self.active_checkbox.isChecked(),
            'is_valid': self.current_is_valid,
            'user_info': self.current_user_info,
            'last_verified': self.current_last_verified,
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
        self.resize(560, 460)

        layout = QVBoxLayout(self)

        # 关键词输入与排序
        keywords_layout = QVBoxLayout()
        keywords_header = QHBoxLayout()
        keywords_header.addWidget(QLabel("关键词:"))
        keywords_header.addStretch()
        keywords_hint = QLabel("选中后可用上下按钮调整顺序，双击可直接编辑")
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

        # 匹配类型和频道ID
        type_channel_layout = QHBoxLayout()

        # 匹配类型
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
        type_channel_layout.addLayout(type_layout)

        # 目标频道
        channel_layout = QVBoxLayout()
        channel_layout.addWidget(QLabel("频道ID (可选):"))
        self.channels_input = QLineEdit()
        self.channels_input.setPlaceholderText("为空则监听所有频道")
        if self.rule:
            self.channels_input.setText(", ".join(map(str, self.rule.target_channels)))
        channel_layout.addWidget(self.channels_input)
        type_channel_layout.addLayout(channel_layout)

        layout.addLayout(type_channel_layout)

        # 延迟设置
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("回复延迟:"))
        self.delay_min_spin = QDoubleSpinBox()
        self.delay_min_spin.setRange(0.1, 30.0)
        self.delay_min_spin.setValue(0.1 if not self.rule else self.rule.delay_min)
        self.delay_min_spin.setSuffix("秒")
        delay_layout.addWidget(self.delay_min_spin)

        delay_layout.addWidget(QLabel("-"))

        self.delay_max_spin = QDoubleSpinBox()
        self.delay_max_spin.setRange(0.1, 30.0)
        self.delay_max_spin.setValue(1.0 if not self.rule else self.rule.delay_max)
        self.delay_max_spin.setSuffix("秒")
        delay_layout.addWidget(self.delay_max_spin)

        layout.addLayout(delay_layout)

        # 激活状态
        self.active_checkbox = QCheckBox("启用规则")
        self.active_checkbox.setChecked(True if not self.rule else self.rule.is_active)
        layout.addWidget(self.active_checkbox)

        # 忽略回复消息
        self.ignore_replies_checkbox = QCheckBox("忽略回复消息")
        self.ignore_replies_checkbox.setToolTip("启用后，当有人回复别人的消息时，不会再回复这条回复消息")
        self.ignore_replies_checkbox.setChecked(True if not self.rule else getattr(self.rule, 'ignore_replies', False))
        layout.addWidget(self.ignore_replies_checkbox)

        # 忽略@消息
        self.ignore_mentions_checkbox = QCheckBox("忽略@消息")
        self.ignore_mentions_checkbox.setToolTip("启用后，当消息中包含@他人时，不会回复这条消息")
        self.ignore_mentions_checkbox.setChecked(True if not self.rule else getattr(self.rule, 'ignore_mentions', False))
        layout.addWidget(self.ignore_mentions_checkbox)

        # 过滤关键词
        exclude_layout = QVBoxLayout()
        exclude_layout.addWidget(QLabel("过滤关键词 (可选):"))
        self.exclude_keywords_input = QLineEdit()
        self.exclude_keywords_input.setPlaceholderText("逗号分隔（支持中文逗号），如 http, discord.gg")
        if self.rule:
            self.exclude_keywords_input.setText(", ".join(getattr(self.rule, 'exclude_keywords', [])))
        exclude_layout.addWidget(self.exclude_keywords_input)
        layout.addLayout(exclude_layout)

        # 大小写敏感
        self.case_sensitive_checkbox = QCheckBox("区分大小写")
        self.case_sensitive_checkbox.setToolTip("启用后，关键词和过滤词匹配将区分大小写")
        self.case_sensitive_checkbox.setChecked(False if not self.rule else getattr(self.rule, 'case_sensitive', False))
        layout.addWidget(self.case_sensitive_checkbox)

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

    def remove_selected_keyword(self):
        current_row = self.keywords_list.currentRow()
        if current_row >= 0:
            self.keywords_list.takeItem(current_row)

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

        # 解析频道ID
        channels_text = self.channels_input.text().strip()
        target_channels = []
        if channels_text:
            try:
                target_channels = [int(c.strip()) for c in channels_text.split(",") if c.strip()]
            except ValueError:
                pass  # 忽略无效的频道ID

        return {
            'keywords': self.get_keywords(),
            'reply': self.reply_input.toPlainText().strip(),
            'match_type': match_type_map[self.match_type_combo.currentIndex()],
            'target_channels': target_channels,
            'delay_min': self.delay_min_spin.value(),
            'delay_max': self.delay_max_spin.value(),
            'is_active': self.active_checkbox.isChecked(),
            'ignore_replies': self.ignore_replies_checkbox.isChecked(),
            'ignore_mentions': self.ignore_mentions_checkbox.isChecked(),
            'case_sensitive': self.case_sensitive_checkbox.isChecked(),
            'exclude_keywords': split_keywords(self.exclude_keywords_input.text()),
        }


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

        self.setCurrentCell(row_indices[-1], 0)

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
        self.resize(620, 620)

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

        rules_title = QLabel(f"配置账号 '{self.account.alias}' 使用的规则：")
        rules_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(rules_title)

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
            checkbox.setChecked(rule.id in self.account.rule_ids)
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
        self.stats_label.setText(f"已选择 {selected_count}/{total_count} 个规则")

    def select_all_rules(self):
        for _, checkbox in self.checkboxes:
            checkbox.setChecked(True)

    def clear_all_rules(self):
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
        for state, (_, checkbox) in zip(updated_states, self.checkboxes):
            checkbox.setChecked(state)

        self.update_stats_label()

    def get_selected_rule_ids(self):
        return [rule_id for rule_id, checkbox in self.checkboxes if checkbox.isChecked()]

    def get_account_data(self):
        return {
            'token': self.token_input.text().strip(),
            'is_active': self.active_checkbox.isChecked(),
            'is_valid': self.current_is_valid,
            'user_info': self.current_user_info,
            'last_verified': self.current_last_verified,
            'selected_rule_ids': self.get_selected_rule_ids(),
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

    def __init__(self):
        super().__init__()
        self.discord_manager = DiscordManager(log_callback=self.add_log_thread_safe)
        self.config_manager = ConfigManager()

        self.worker_thread = None

        self.init_ui()
        self.load_config()

        # 连接日志信号
        self.log_signal.connect(self.add_log)

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("Discord 自动回复工具")
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
        self.accounts_table.setColumnCount(4)
        self.accounts_table.setHorizontalHeaderLabels(["用户名", "Token状态", "应用规则", "操作"])
        self.accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.accounts_table.setAlternatingRowColors(True)
        self.accounts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.accounts_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.accounts_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.accounts_table.customContextMenuRequested.connect(self.show_accounts_context_menu)
        layout.addWidget(self.accounts_table)

        # 统计信息
        self.accounts_stats_label = QLabel("总账号数: 0 | 启用账号数: 0")
        layout.addWidget(self.accounts_stats_label)

        self.tab_widget.addTab(accounts_widget, "账号管理")

    def create_rules_tab(self):
        """创建规则管理标签页"""
        rules_widget = QWidget()
        layout = QVBoxLayout(rules_widget)

        # 标题和添加按钮
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("自动回复规则管理（点击上下按钮调整优先级）"))

        # 搜索框
        self.rule_search_input = QLineEdit()
        self.rule_search_input.setPlaceholderText("搜索关键词...")
        self.rule_search_input.textChanged.connect(self.filter_rules)
        header_layout.addWidget(self.rule_search_input)

        header_layout.addStretch()

        add_rule_btn = QPushButton("添加规则")
        add_rule_btn.clicked.connect(self.add_rule)
        header_layout.addWidget(add_rule_btn)

        layout.addLayout(header_layout)

        # 规则表格
        self.rules_table = ReorderableRulesTable()
        self.rules_table.setColumnCount(9)
        self.rules_table.setHorizontalHeaderLabels(["关键词", "回复内容", "匹配类型", "频道", "延迟", "忽略回复", "忽略@", "过滤关键词", "操作"])
        rules_header = self.rules_table.horizontalHeader()
        rules_header.setStretchLastSection(False)
        rules_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        rules_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in range(2, 8):
            rules_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        rules_header.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive)
        self.rules_table.setColumnWidth(8, 220)
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
        self.rules_stats_label = QLabel("总规则数: 0 | 启用规则数: 0")
        layout.addWidget(self.rules_stats_label)

        self.tab_widget.addTab(rules_widget, "规则管理")

    def create_status_tab(self):
        """创建状态监控标签页"""
        status_widget = QWidget()
        layout = QVBoxLayout(status_widget)

        # 账号状态表格
        accounts_group = QGroupBox("账号状态")
        accounts_layout = QVBoxLayout(accounts_group)

        self.status_accounts_table = QTableWidget()
        self.status_accounts_table.setColumnCount(3)
        self.status_accounts_table.setHorizontalHeaderLabels(["别名", "状态", "运行状态"])
        self.status_accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        accounts_layout.addWidget(self.status_accounts_table)

        layout.addWidget(accounts_group)

        # 规则统计
        rules_group = QGroupBox("规则统计")
        rules_layout = QVBoxLayout(rules_group)

        self.rules_stats_label = QLabel("总规则数: 0 | 激活规则数: 0")
        rules_layout.addWidget(self.rules_stats_label)

        layout.addWidget(rules_group)

        # 轮换设置
        rotation_group = QGroupBox("账号轮换设置")
        rotation_layout = QVBoxLayout(rotation_group)

        # 启用轮换
        self.rotation_enabled_checkbox = QCheckBox("启用账号轮换")
        self.rotation_enabled_checkbox.setToolTip("启用后，当账号被频率限制时会自动切换到其他账号发送消息")
        self.rotation_enabled_checkbox.stateChanged.connect(self.on_rotation_enabled_changed)
        rotation_layout.addWidget(self.rotation_enabled_checkbox)

        # 轮换间隔设置
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("轮换间隔(秒):"))
        self.rotation_interval_spin = QSpinBox()
        self.rotation_interval_spin.setRange(1, 3600)  # 1秒到1小时
        self.rotation_interval_spin.setValue(10)  # 默认10秒
        self.rotation_interval_spin.setSuffix("秒")
        self.rotation_interval_spin.setEnabled(False)  # 默认禁用
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
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)

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
        accounts, rules = self.config_manager.load_config()
        self.discord_manager.accounts = accounts
        self.discord_manager.rules = rules

        # 加载轮换设置（暂时使用默认值，后续可以扩展配置文件）
        # TODO: 从配置文件加载轮换设置

        self.update_accounts_list()
        self.update_rules_list()
        self.update_status()

    def save_config(self):
        """保存配置"""
        self.config_manager.save_config(
            self.discord_manager.accounts,
            self.discord_manager.rules
        )

    def update_accounts_list(self):
        """更新账号表格显示"""
        self.accounts_table.setRowCount(len(self.discord_manager.accounts))

        for row, account in enumerate(self.discord_manager.accounts):
            # 用户名
            username = account.alias  # 使用alias属性，它会自动生成用户名
            username_item = QTableWidgetItem(username)
            username_item.setData(Qt.ItemDataRole.UserRole, account.token)  # 使用token作为标识
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

            # 添加工具提示
            if token_type == 'user':
                token_status_item.setToolTip("用户Token可以验证但无法连接，请使用Bot Token")
            elif token_type == 'bot':
                token_status_item.setToolTip("Bot Token，完全支持连接和消息处理")

            self.accounts_table.setItem(row, 1, token_status_item)

            # 应用规则（显示关联的规则数量）
            applied_rules = len(account.rule_ids)
            total_rules = len(self.discord_manager.rules)
            rules_text = f"{applied_rules}/{total_rules}"
            rules_item = QTableWidgetItem(rules_text)
            if applied_rules > 0:
                rules_item.setBackground(QColor(173, 216, 230))  # 浅蓝色
            else:
                rules_item.setBackground(QColor(240, 240, 240))  # 浅灰色
            rules_item.setData(Qt.ItemDataRole.UserRole, account.rule_ids)  # 存储规则ID列表
            self.accounts_table.setItem(row, 2, rules_item)

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

            self.accounts_table.setCellWidget(row, 3, button_widget)

        # 更新统计信息
        total_accounts = len(self.discord_manager.accounts)
        active_accounts = len([acc for acc in self.discord_manager.accounts if acc.is_active])
        self.accounts_stats_label.setText(f"总账号数: {total_accounts} | 启用账号数: {active_accounts}")

    def update_rules_list(self):
        """更新规则表格显示"""
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

            # 频道信息
            channels_info = f"{len(rule.target_channels)}个频道" if rule.target_channels else "全部频道"
            channels_display = ", ".join(map(str, rule.target_channels[:2]))
            if len(rule.target_channels) > 2:
                channels_display += "..."
            channels_item = QTableWidgetItem(channels_display if rule.target_channels else "全部")
            channels_item.setToolTip(", ".join(map(str, rule.target_channels)) if rule.target_channels else "监听所有频道")
            self.rules_table.setItem(row, 3, channels_item)

            # 延迟
            delay_info = f"{rule.delay_min:.1f}-{rule.delay_max:.1f}秒"
            delay_item = QTableWidgetItem(delay_info)
            self.rules_table.setItem(row, 4, delay_item)

            # 忽略回复
            ignore_replies_status = "是" if getattr(rule, 'ignore_replies', False) else "否"
            ignore_item = QTableWidgetItem(ignore_replies_status)
            ignore_item.setData(Qt.ItemDataRole.ToolTipRole, "是否忽略回复他人的消息")
            self.rules_table.setItem(row, 5, ignore_item)

            # 忽略@
            ignore_mentions_status = "是" if getattr(rule, 'ignore_mentions', False) else "否"
            mentions_item = QTableWidgetItem(ignore_mentions_status)
            mentions_item.setData(Qt.ItemDataRole.ToolTipRole, "是否忽略包含@他人的消息")
            self.rules_table.setItem(row, 6, mentions_item)

            # 过滤关键词
            exclude_keywords = getattr(rule, 'exclude_keywords', [])
            if exclude_keywords:
                exclude_display = ", ".join(exclude_keywords[:2])
                if len(exclude_keywords) > 2:
                    exclude_display += "..."
            else:
                exclude_display = "无"
            exclude_item = QTableWidgetItem(exclude_display)
            exclude_item.setToolTip(", ".join(exclude_keywords) if exclude_keywords else "无过滤关键词")
            self.rules_table.setItem(row, 7, exclude_item)

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

            self.rules_table.setCellWidget(row, 8, button_widget)

        # 更新统计信息
        total_rules = len(self.discord_manager.rules)
        active_rules = len([rule for rule in self.discord_manager.rules if rule.is_active])
        self.rules_stats_label.setText(f"总规则数: {total_rules} | 启用规则数: {active_rules}")

        # 应用当前搜索过滤
        self.filter_rules()

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

            # 更新规则统计
            rules_text = f"总规则数: {status['rules_count']} | 激活规则数: {status['active_rules']}"
            if self.rules_stats_label.text() != rules_text:
                self.rules_stats_label.setText(rules_text)

        except Exception as e:
            # 静默处理状态更新错误，避免影响用户体验
            print(f"状态更新错误: {e}")

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
                last_sent_time=account.last_sent_time if new_token == account.token else None,
                rate_limit_until=account.rate_limit_until if new_token == account.token else None,
            )

            self.discord_manager.accounts = replace_item_preserving_order(
                self.discord_manager.accounts,
                account_index,
                replacement_account,
            )

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
            self.add_log(f"账号 '{account.alias}' 已删除", "info")
            self.update_accounts_list()
            self.save_config()

    def remove_account_by_alias(self, alias):
        """通过别名删除账号"""
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除账号 '{alias}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.discord_manager.remove_account(alias)
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
                data['target_channels'],
                data['delay_min'],
                data['delay_max'],
                data.get('ignore_replies', False),
                data.get('ignore_mentions', False),
                data.get('case_sensitive', False),
                data.get('exclude_keywords', [])
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
                target_channels=data['target_channels'],
                delay_min=data['delay_min'],
                delay_max=data['delay_max'],
                is_active=data['is_active'],
                ignore_replies=data.get('ignore_replies', False),
                ignore_mentions=data.get('ignore_mentions', False),
                case_sensitive=data.get('case_sensitive', False),
                exclude_keywords=data.get('exclude_keywords', [])
            )

            self.update_rules_list()
            self.save_config()
            QMessageBox.information(self, "成功", "规则编辑成功")

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

        # 根据级别设置颜色和前缀
        if level == "error":
            colored_msg = f'<span style="color: red;">[{timestamp}] ❌ {message}</span>'
        elif level == "warning":
            colored_msg = f'<span style="color: orange;">[{timestamp}] ⚠️ {message}</span>'
        elif level == "success":
            colored_msg = f'<span style="color: green;">[{timestamp}] ✅ {message}</span>'
        elif level == "info":
            colored_msg = f'<span style="color: blue;">[{timestamp}] ℹ️ {message}</span>'
        else:
            colored_msg = f'[{timestamp}] {message}'

        # 添加到日志文本框，增加行距
        current_text = self.log_text.toHtml()
        if current_text:
            new_text = current_text + '<div style="margin: 2px 0;">' + colored_msg + '</div>'
        else:
            new_text = '<div style="margin: 2px 0;">' + colored_msg + '</div>'

        self.log_text.setHtml(new_text)

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
            self.rotation_status_label.setText(f"轮换模式: 已启用 (间隔{self.rotation_interval_spin.value()}秒)")
        else:
            self.rotation_status_label.setText("轮换模式: 未启用")

        # 保存配置
        self.save_config()

        if self.log_callback:
            status = "启用" if enabled else "禁用"
            self.log_callback(f"账号轮换模式已{status}")

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
            if self.config_manager.export_config(
                filename, self.discord_manager.accounts, self.discord_manager.rules
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
            accounts, rules = self.config_manager.import_config(filename)
            if accounts or rules:
                self.discord_manager.accounts = accounts
                self.discord_manager.rules = rules
                self.update_accounts_list()
                self.update_rules_list()
                self.save_config()
                QMessageBox.information(self, "成功", "配置导入成功")
            else:
                QMessageBox.warning(self, "错误", "配置导入失败")


def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 使用更现代的样式

    # 设置应用程序属性，确保在macOS上正确显示
    app.setApplicationName("Discord Auto Reply")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("DiscordAutoReply")

    window = MainWindow()
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
    asyncio.run(main())
