import asyncio
import discord
import hashlib
import re
import random
import time
import logging
from functools import lru_cache
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

# discord.py-self 不需要Intents


class MatchType(Enum):
    PARTIAL = "partial"
    EXACT = "exact"
    REGEX = "regex"


MATCH_RELEVANT_RULE_FIELDS = {
    "keywords",
    "match_type",
    "is_active",
    "ignore_replies",
    "ignore_mentions",
    "case_sensitive",
}


@dataclass
class Account:
    token: str
    is_active: bool = True
    is_valid: bool = False  # Token验证状态
    last_verified: Optional[float] = None  # 最后验证时间
    user_info: Optional[Dict] = None  # 用户信息
    rule_ids: List[str] = None  # 关联的规则ID列表
    target_channels: List[int] = None  # 账号生效频道列表，空表示全部频道
    delay_min: float = 0.0  # 兼容旧配置，当前固定为最快回复
    delay_max: float = 0.0  # 兼容旧配置，当前固定为最快回复
    last_sent_time: Optional[float] = None  # 最后发送消息时间
    cooldown_until: Optional[float] = None  # 轮换冷却到期时间
    rate_limit_until: Optional[float] = None  # 频率限制到期时间
    reply_count: int = 0  # 当前账号累计回复数量

    def __post_init__(self):
        if self.rule_ids is None:
            self.rule_ids = []
        if self.target_channels is None:
            self.target_channels = []
        else:
            self.target_channels = self._normalize_channel_ids(self.target_channels)
        self.delay_min, self.delay_max = 0.0, 0.0
        self.reply_count = max(0, int(self.reply_count or 0))

    @property
    def alias(self) -> str:
        """获取账号别名（使用用户名）"""
        if self.user_info and isinstance(self.user_info, dict):
            return f"{self.user_info.get('name', 'Unknown')}#{self.user_info.get('discriminator', '0000')}"
        return f"Token-{self.token[:8]}..."

    @staticmethod
    def _normalize_channel_ids(channel_ids: Optional[List[int]]) -> List[int]:
        normalized_ids = []
        seen_ids = set()

        for channel_id in channel_ids or []:
            try:
                cleaned_id = int(str(channel_id).strip())
            except (TypeError, ValueError):
                continue

            if cleaned_id in seen_ids:
                continue
            normalized_ids.append(cleaned_id)
            seen_ids.add(cleaned_id)

        return normalized_ids

    @staticmethod
    def _normalize_delay_range(delay_min: Optional[float], delay_max: Optional[float]) -> tuple[float, float]:
        try:
            normalized_min = float(delay_min)
        except (TypeError, ValueError):
            normalized_min = 0.1

        try:
            normalized_max = float(delay_max)
        except (TypeError, ValueError):
            normalized_max = 1.0

        normalized_min = max(0.0, normalized_min)
        normalized_max = max(0.0, normalized_max)
        if normalized_max < normalized_min:
            normalized_min, normalized_max = normalized_max, normalized_min
        return normalized_min, normalized_max

    def allows_channel(self, channel_id: Optional[int]) -> bool:
        if not self.target_channels:
            return True
        if channel_id is None:
            return False
        return int(channel_id) in self.target_channels


@dataclass
class Rule:
    id: str  # 规则唯一标识
    keywords: List[str]
    reply: str
    match_type: MatchType
    target_channels: List[int]
    delay_min: float = 0.0
    delay_max: float = 0.0
    is_active: bool = True
    ignore_replies: bool = True  # 是否忽略回复他人的消息
    ignore_mentions: bool = True  # 是否忽略包含@他人的消息
    case_sensitive: bool = False  # 是否区分大小写，False表示不区分大小写
    exclude_keywords: List[str] = field(default_factory=list)  # 触发后不回复的过滤关键词
    reply_account_count: int = 1  # 命中后由几个账号回复，支持 1-3
    sync_source: str = ""  # 跟随文件同步时标记来源
    _match_revision: int = field(default=0, init=False, repr=False, compare=False)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name in MATCH_RELEVANT_RULE_FIELDS:
            object.__setattr__(self, "_match_revision", getattr(self, "_match_revision", 0) + 1)

    def __post_init__(self):
        self.target_channels = Account._normalize_channel_ids(self.target_channels)
        self.delay_min, self.delay_max = 0.0, 0.0
        try:
            normalized_count = int(self.reply_account_count)
        except (TypeError, ValueError):
            normalized_count = 1
        self.reply_account_count = max(1, min(3, normalized_count))


@dataclass
class BlockSettings:
    blocked_keywords: List[str] = field(default_factory=list)
    blocked_user_ids: List[str] = field(default_factory=list)
    blocked_channel_ids: List[int] = field(default_factory=list)
    account_scope: str = "all"  # all | selected
    account_tokens: List[str] = field(default_factory=list)
    ignore_replies: bool = True
    ignore_mentions: bool = True
    reply_delay_min: float = 0.0
    reply_delay_max: float = 0.0
    case_sensitive: bool = False

    def __post_init__(self):
        self.blocked_keywords = self._normalize_values(self.blocked_keywords)
        self.blocked_user_ids = self._normalize_values(self.blocked_user_ids)
        self.blocked_channel_ids = Account._normalize_channel_ids(self.blocked_channel_ids)
        self.account_tokens = self._normalize_values(self.account_tokens)
        self.reply_delay_min, self.reply_delay_max = self._normalize_delay_range(
            self.reply_delay_min,
            self.reply_delay_max,
        )
        self.case_sensitive = False
        if self.account_scope not in {"all", "selected"}:
            self.account_scope = "all"

    @staticmethod
    def _normalize_values(values: Optional[List[str]]) -> List[str]:
        normalized_values = []
        seen_values = set()

        for value in values or []:
            cleaned_value = str(value).strip()
            if not cleaned_value or cleaned_value in seen_values:
                continue
            normalized_values.append(cleaned_value)
            seen_values.add(cleaned_value)

        return normalized_values

    @staticmethod
    def _normalize_delay_range(delay_min: Optional[float], delay_max: Optional[float]) -> tuple[float, float]:
        try:
            normalized_min = float(delay_min)
        except (TypeError, ValueError):
            normalized_min = 0.0

        try:
            normalized_max = float(delay_max)
        except (TypeError, ValueError):
            normalized_max = 0.0

        normalized_min = max(0.0, normalized_min)
        normalized_max = max(0.0, normalized_max)
        if normalized_max < normalized_min:
            normalized_min, normalized_max = normalized_max, normalized_min
        return normalized_min, normalized_max

    def applies_to_account(self, account: Account) -> bool:
        if self.account_scope != "selected":
            return True
        return account.token in self.account_tokens

    def blocks_content(self, content: str) -> bool:
        if not content or not self.blocked_keywords:
            return False

        content_lower = content.lower()
        return any(keyword.lower() in content_lower for keyword in self.blocked_keywords)

    def blocks_user(self, author_id: Optional[str]) -> bool:
        if author_id is None:
            return False
        return str(author_id).strip() in self.blocked_user_ids

    def applies_to_channel(self, channel_id: Optional[int]) -> bool:
        if not self.blocked_channel_ids:
            return True
        if channel_id is None:
            return False
        return int(channel_id) in self.blocked_channel_ids

    def should_block_message(
        self,
        account: Account,
        content: str,
        author_id: Optional[str],
        channel_id: Optional[int] = None,
    ) -> bool:
        if not self.applies_to_account(account):
            return False
        if not self.applies_to_channel(channel_id):
            return False
        if self.blocks_user(author_id):
            return True
        return self.blocks_content(content)

    def should_ignore_reply_message(self, message_reference) -> bool:
        return self.ignore_replies and message_reference is not None

    def should_ignore_mention_message(self, mentions) -> bool:
        return self.ignore_mentions and bool(mentions)

    def choose_reply_delay_seconds(self) -> float:
        if self.reply_delay_min <= 0 and self.reply_delay_max <= 0:
            return 0.0
        if self.reply_delay_min == self.reply_delay_max:
            return self.reply_delay_min
        return random.uniform(self.reply_delay_min, self.reply_delay_max)


def _get_message_author_label(message) -> str:
    author = getattr(message, "author", None)
    if author is None:
        return "未知用户"

    for attribute in ("display_name", "global_name", "name"):
        value = getattr(author, attribute, None)
        if value:
            return str(value)

    author_id = getattr(author, "id", None)
    if author_id is not None:
        return str(author_id)
    return "未知用户"


def _build_reply_log_message(account_alias: str, message) -> str:
    return f"{account_alias} 回复了 {_get_message_author_label(message)}"


def _build_reply_thread_name(message) -> str:
    author_label = re.sub(r"\s+", " ", _get_message_author_label(message)).strip() or "用户"
    author_label = author_label[:40]
    message_id = str(getattr(message, "id", "") or "").strip()
    base_name = f"回复-{author_label}"

    if not message_id:
        return base_name[:100]

    max_base_length = max(1, 100 - len(message_id) - 1)
    trimmed_base = base_name[:max_base_length].rstrip(" -")
    return f"{trimmed_base}-{message_id}"[:100]


def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _is_ascii_word_char(character: str) -> bool:
    if not character:
        return False

    code = ord(character)
    return (
        48 <= code <= 57 or
        65 <= code <= 90 or
        97 <= code <= 122
    )


def _has_keyword_boundaries(text: str, start_index: int, end_index: int) -> bool:
    previous_character = text[start_index - 1] if start_index > 0 else ""
    next_character = text[end_index] if end_index < len(text) else ""
    return not _is_ascii_word_char(previous_character) and not _is_ascii_word_char(next_character)


@lru_cache(maxsize=4096)
def _compile_partial_keyword_pattern(keyword: str):
    normalized_keyword = _normalize_match_text(keyword)
    if not normalized_keyword:
        return None

    escaped_keyword = re.escape(normalized_keyword).replace(r"\ ", r"\s+")
    if re.search(r"[A-Za-z0-9]", normalized_keyword):
        pattern = rf"(?<![A-Za-z0-9]){escaped_keyword}(?![A-Za-z0-9])"
    else:
        pattern = escaped_keyword
    return re.compile(pattern, re.IGNORECASE)


class LiteralKeywordAutomaton:
    def __init__(self):
        self.nodes = [{"children": {}, "fail": 0, "outputs": []}]

    def add(self, keyword: str, payload):
        state = 0
        for character in keyword:
            children = self.nodes[state]["children"]
            next_state = children.get(character)
            if next_state is None:
                next_state = len(self.nodes)
                children[character] = next_state
                self.nodes.append({"children": {}, "fail": 0, "outputs": []})
            state = next_state
        self.nodes[state]["outputs"].append(payload)

    def build(self):
        queue = list(self.nodes[0]["children"].values())
        queue_index = 0

        while queue_index < len(queue):
            state = queue[queue_index]
            queue_index += 1

            for character, next_state in self.nodes[state]["children"].items():
                queue.append(next_state)
                fail_state = self.nodes[state]["fail"]

                while fail_state and character not in self.nodes[fail_state]["children"]:
                    fail_state = self.nodes[fail_state]["fail"]

                self.nodes[next_state]["fail"] = self.nodes[fail_state]["children"].get(character, 0)
                self.nodes[next_state]["outputs"].extend(
                    self.nodes[self.nodes[next_state]["fail"]]["outputs"]
                )

    def iter_matches(self, text: str):
        state = 0

        for character_index, character in enumerate(text):
            while state and character not in self.nodes[state]["children"]:
                state = self.nodes[state]["fail"]

            state = self.nodes[state]["children"].get(character, 0)
            outputs = self.nodes[state]["outputs"]
            if outputs:
                for payload in outputs:
                    yield character_index, payload


class RuleSetMatcher:
    def __init__(self, rules: List[Rule]):
        self.rules = list(rules)
        self.partial_automaton = None
        self.exact_keyword_map: Dict[str, List[Tuple[str, int, int, str, int]]] = {}
        self.regex_keyword_entries: List[Tuple[str, int, int, str, Optional[re.Pattern], int]] = []
        self._build()

    def _build(self):
        partial_automaton = LiteralKeywordAutomaton()
        partial_keyword_count = 0

        for rule_index, rule in enumerate(self.rules):
            if not rule.is_active:
                continue

            for keyword_index, keyword in enumerate(rule.keywords):
                normalized_keyword = _normalize_match_text(keyword)
                if not normalized_keyword:
                    continue

                if rule.match_type == MatchType.PARTIAL:
                    partial_automaton.add(
                        normalized_keyword.lower(),
                        (
                            rule.id,
                            rule_index,
                            keyword_index,
                            keyword,
                            len(normalized_keyword),
                            any(_is_ascii_word_char(character) for character in normalized_keyword),
                        ),
                    )
                    partial_keyword_count += 1
                elif rule.match_type == MatchType.EXACT:
                    self.exact_keyword_map.setdefault(normalized_keyword.lower(), []).append(
                        (rule.id, rule_index, keyword_index, keyword, len(normalized_keyword))
                    )
                elif rule.match_type == MatchType.REGEX:
                    try:
                        compiled_pattern = re.compile(keyword, re.IGNORECASE)
                    except re.error:
                        compiled_pattern = None
                    self.regex_keyword_entries.append(
                        (rule.id, rule_index, keyword_index, keyword, compiled_pattern, len(normalized_keyword))
                    )

        if partial_keyword_count > 0:
            partial_automaton.build()
            self.partial_automaton = partial_automaton

    @staticmethod
    def _update_best_match(
        matched_keywords: Dict[str, str],
        matched_ranks: Dict[str, Tuple[int, int]],
        rule_id: str,
        keyword_index: int,
        keyword: str,
        keyword_length: int,
    ):
        new_rank = (-keyword_length, keyword_index)
        current_rank = matched_ranks.get(rule_id)
        if current_rank is None or new_rank < current_rank:
            matched_ranks[rule_id] = new_rank
            matched_keywords[rule_id] = keyword

    def match_content(self, content: str) -> Dict[str, str]:
        if not content:
            return {}

        normalized_content = _normalize_match_text(content)
        if not normalized_content:
            return {}

        normalized_lower_content = normalized_content.lower()
        matched_keywords: Dict[str, str] = {}
        matched_ranks: Dict[str, Tuple[int, int]] = {}

        if self.partial_automaton is not None:
            for end_index, payload in self.partial_automaton.iter_matches(normalized_lower_content):
                rule_id, rule_index, keyword_index, keyword, keyword_length, requires_boundary = payload
                start_index = end_index - keyword_length + 1
                if requires_boundary and not _has_keyword_boundaries(normalized_lower_content, start_index, end_index + 1):
                    continue

                self._update_best_match(
                    matched_keywords,
                    matched_ranks,
                    rule_id,
                    keyword_index,
                    keyword,
                    keyword_length,
                )

        for rule_id, _rule_index, keyword_index, keyword, keyword_length in self.exact_keyword_map.get(normalized_lower_content, []):
            self._update_best_match(
                matched_keywords,
                matched_ranks,
                rule_id,
                keyword_index,
                keyword,
                keyword_length,
            )

        for rule_id, _rule_index, keyword_index, keyword, compiled_pattern, keyword_length in self.regex_keyword_entries:
            if compiled_pattern is None or compiled_pattern.search(normalized_content) is None:
                continue

            self._update_best_match(
                matched_keywords,
                matched_ranks,
                rule_id,
                keyword_index,
                keyword,
                keyword_length,
            )

        return matched_keywords


class AutoReplyClient(discord.Client):
    def __init__(self, account: Account, rules: List[Rule], log_callback=None, discord_manager=None, *args, **kwargs):
        # 修正: discord.py-self 不需要也不支持 intents 参数
        # 直接调用父类构造函数即可
        super().__init__(*args, **kwargs)

        self.account = account
        self.rules = rules
        self.is_running = False
        self.log_callback = log_callback
        self.discord_manager = discord_manager
        self.startup_complete = asyncio.Event()
        self.startup_error: Optional[str] = None
        self.local_rule_matcher: Optional[RuleSetMatcher] = None
        self.local_rule_signature = None
        if self.discord_manager is not None and getattr(self.discord_manager, "log_callback", None) is None and log_callback is not None:
            self.discord_manager.log_callback = log_callback

    async def on_ready(self):
        try:
            # 确保self.user不为None
            if self.user is None:
                error_msg = f"[{self.account.alias}] 用户信息获取失败：client.user为None"
                print(error_msg)
                if self.log_callback:
                    self.log_callback(error_msg)
                self.is_running = False
                return

            self.is_running = True
            username = getattr(self.user, 'name', 'Unknown')
            discriminator = getattr(self.user, 'discriminator', '0000')
            display_name = f"{username}#{discriminator}"
            message = f"[{self.account.alias}] 登录成功: {display_name}"
            print(message)
            if self.log_callback:
                self.log_callback(message)

            # 更新账号信息
            self.account.user_info = {
                'id': str(self.user.id),
                'name': username,
                'discriminator': discriminator,
                'bot': getattr(self.user, 'bot', False)
            }
            self.startup_error = None
            self.startup_complete.set()

        except Exception as e:
            error_msg = f"[{self.account.alias}] on_ready事件错误: {e}"
            print(error_msg)
            if self.log_callback:
                self.log_callback(error_msg)
            self.startup_error = error_msg
            self.startup_complete.set()
            self.is_running = False

    async def on_message(self, message):
        # 不要回复自己
        if message.author.id == self.user.id:
            return

        # 检查是否是被屏蔽的用户
        try:
            # Discord.py-self 可能有 blocked 属性
            if hasattr(message.author, 'blocked') and message.author.blocked:
                return
        except:
            pass  # 如果无法检查，跳过

        if not self.account.allows_channel(getattr(message.channel, "id", None)):
            return

        block_settings = self._get_block_settings()
        if block_settings is not None:
            if block_settings.should_ignore_reply_message(getattr(message, "reference", None)):
                return
            if block_settings.should_ignore_mention_message(getattr(message, "mentions", [])):
                return

        matched_keywords = self._get_matched_keywords_for_message(message)
        if not matched_keywords:
            return

        for rule in self.rules:
            if not rule.is_active:
                continue

            if block_settings is None and self._should_ignore_reply_message(message, rule):
                continue

            if block_settings is None and self._should_ignore_mention_message(message, rule):
                continue

            matched_keyword = matched_keywords.get(rule.id)
            if matched_keyword is not None:
                if self._is_blocked_message(message):
                    break

                try:
                    target_reply_count = max(1, min(3, int(getattr(rule, "reply_account_count", 1) or 1)))
                    # 检查是否启用轮换模式
                    if (self.discord_manager and
                        self.discord_manager.rotation_enabled and
                        self.account.allows_channel(getattr(message.channel, "id", None)) and
                        target_reply_count == 1):
                        # 使用轮换模式
                        await self.discord_manager.send_rotated_reply(
                            message,
                            rule.reply,
                            matched_keyword,
                        )
                    elif self.discord_manager:
                        await self.discord_manager.send_rule_replies(
                            message,
                            rule,
                            matched_keyword=matched_keyword,
                            preferred_account=self.account,
                            preferred_client=self,
                        )
                    else:
                        # 使用普通回复
                        await self._wait_before_direct_reply_if_needed()
                        await message.reply(rule.reply)
                        success_msg = _build_reply_log_message(self.account.alias, message)
                        print(success_msg)
                        if self.log_callback:
                            self.log_callback(success_msg)

                    break # 只处理第一个匹配规则

                except Exception as e:
                    error_msg = f"{self.account.alias} 回复失败: {e}"
                    print(error_msg)
                    if self.log_callback:
                        self.log_callback(error_msg)

                break

    def _build_local_rule_signature(self):
        return tuple((id(rule), getattr(rule, "_match_revision", 0)) for rule in self.rules)

    def _get_local_rule_matcher(self) -> RuleSetMatcher:
        current_signature = self._build_local_rule_signature()
        if self.local_rule_matcher is None or current_signature != self.local_rule_signature:
            self.local_rule_matcher = RuleSetMatcher(self.rules)
            self.local_rule_signature = current_signature
        return self.local_rule_matcher

    def _get_matched_keywords_for_message(self, message) -> Dict[str, str]:
        content = getattr(message, "content", "") or ""
        if not content or not self.rules:
            return {}

        if self.discord_manager is not None and getattr(self.discord_manager, "rules", None):
            return self.discord_manager.get_message_rule_matches(message, content)

        return self._get_local_rule_matcher().match_content(content)

    def _find_matched_keyword(self, content: str, rule: Rule) -> Optional[str]:
        """检查消息内容是否匹配规则"""
        if not content or rule is None:
            return None

        return self._get_local_rule_matcher().match_content(content).get(rule.id)

    def _check_match(self, content: str, rule: Rule) -> bool:
        return self._find_matched_keyword(content, rule) is not None

    def _get_block_settings(self) -> Optional[BlockSettings]:
        return getattr(self.discord_manager, "block_settings", None)

    def _should_ignore_reply_message(self, message, rule: Rule) -> bool:
        block_settings = self._get_block_settings()
        if block_settings is not None:
            return block_settings.should_ignore_reply_message(getattr(message, "reference", None))
        return getattr(rule, "ignore_replies", False) and getattr(message, "reference", None) is not None

    def _should_ignore_mention_message(self, message, rule: Rule) -> bool:
        block_settings = self._get_block_settings()
        if block_settings is not None:
            return block_settings.should_ignore_mention_message(getattr(message, "mentions", []))
        return getattr(rule, "ignore_mentions", False) and bool(getattr(message, "mentions", []))

    def _is_rule_match_case_sensitive(self, rule: Rule) -> bool:
        return False

    def _is_blocked_message(self, message) -> bool:
        block_settings = getattr(self.discord_manager, "block_settings", None)
        if not block_settings:
            return False

        author_id = getattr(message.author, "id", None)
        content = getattr(message, "content", "") or ""
        channel_id = getattr(getattr(message, "channel", None), "id", None)
        return block_settings.should_block_message(self.account, content, author_id, channel_id=channel_id)

    async def _wait_before_direct_reply_if_needed(self):
        block_settings = self._get_block_settings()
        if block_settings is None:
            return

        delay_seconds = block_settings.choose_reply_delay_seconds()
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    async def start_client(self):
        self.is_running = False
        self.startup_error = None
        self.startup_complete.clear()

        try:
            await self.start(self.account.token)

            if not self.startup_complete.is_set():
                self.startup_complete.set()

        except discord.LoginFailure as e:
            error_msg = f"[{self.account.alias}] 登录失败: Token无效 - {e}"
            print(error_msg)
            if self.log_callback:
                self.log_callback(error_msg)
            self.startup_error = error_msg
            self.startup_complete.set()
            self.is_running = False

        except asyncio.CancelledError:
            if not self.startup_complete.is_set():
                self.startup_complete.set()
            self.is_running = False
            raise

        except Exception as e:
            error_msg = f"[{self.account.alias}] 启动失败: {e}"
            print(error_msg)
            if self.log_callback:
                self.log_callback(error_msg)
            self.startup_error = error_msg
            self.startup_complete.set()
            self.is_running = False

        finally:
            if self.is_closed():
                self.is_running = False

    async def wait_for_startup(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self.startup_complete.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            error_msg = f"[{self.account.alias}] 连接超时：{int(timeout)}秒内未完成登录"
            print(error_msg)
            if self.log_callback:
                self.log_callback(error_msg)
            self.startup_error = error_msg
            self.is_running = False
            self.startup_complete.set()
            if not self.is_closed():
                await self.close()
            return False

        return self.is_running

    async def stop_client(self):
        """停止客户端"""
        self.is_running = False
        if not self.startup_complete.is_set():
            self.startup_complete.set()
        if not self.is_closed():
            await self.close()


class TokenValidator:
    """Discord Token验证器"""

    # 注意: TokenValidator 中使用了 discord.Client() 进行验证
    # 也需要移除 intents 参数

    @staticmethod
    async def validate_token(token: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        token = token.strip()
        if not token:
            return False, None, "Token为空"

        # 1. 先尝试 HTTP 验证 (更稳)
        try:
            http_res = await TokenValidator._validate_token_http(token)
            if http_res[0] is not None:
                return http_res
        except Exception as e:
            # HTTP验证完全失败，继续WebSocket验证
            pass

        # 2. 备选: WebSocket 验证
        try:
            ws_res = await TokenValidator._validate_token_websocket(token)
            return ws_res
        except Exception as e:
            return False, None, "所有验证方法都失败，请检查Token和网络连接"

    @staticmethod
    def _detect_token_type(token: str) -> str:
        token = token.strip()
        if len(token) > 70: return "bot"
        if token.startswith("mfa.") or len(token) < 70: return "user"
        return "unknown"

    @staticmethod
    async def _validate_token_http(token: str) -> Tuple[Optional[bool], Optional[Dict], Optional[str]]:
        import aiohttp
        token = token.strip()
        if not token: return False, None, "Token为空"

        headers = {'Authorization': token, 'User-Agent': 'DiscordBot/1.0'}
        timeout = aiohttp.ClientTimeout(total=10)  # 设置10秒超时
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get('https://discord.com/api/v10/users/@me', headers=headers) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            if not data:
                                return False, None, "响应数据为空"
                            user_info = {
                                'id': data.get('id'),
                                'name': data.get('username'),
                                'discriminator': data.get('discriminator', '0000'),
                                'avatar_url': f"https://cdn.discordapp.com/avatars/{data.get('id', 'unknown')}/{data.get('avatar', 'unknown')}.png" if data.get('avatar') else None,
                                'bot': data.get('bot', False),
                                'token_type': 'bot' if data.get('bot') else 'user'
                            }
                            return True, user_info, None
                        except Exception as json_error:
                            return False, None, f"解析响应失败: {str(json_error)}"
                    elif resp.status == 401:
                        return False, None, "Token无效"
                    elif resp.status == 403:
                        return False, None, "Token权限不足"
                    elif resp.status == 429:
                        return False, None, "请求过于频繁，请稍后再试"
                    else:
                        return False, None, f"HTTP {resp.status}"
        except asyncio.TimeoutError:
            return None, None, "连接超时，请检查网络"
        except aiohttp.ClientError as client_error:
            return None, None, f"网络连接错误: {str(client_error)}"
        except Exception as e:
            # 避免返回复杂的错误对象，只返回字符串
            error_msg = str(e)
            # 如果错误信息太长或包含特殊字符，简化它
            if len(error_msg) > 100 or "'" in error_msg or '"' in error_msg:
                return None, None, "验证请求失败"
            return None, None, error_msg

    @staticmethod
    async def _validate_token_websocket(token: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        使用WebSocket验证Token（备选方案）
        """
        client = None
        try:
            # 创建临时客户端进行验证
            client = discord.Client()

            user_info = None
            error = None

            @client.event
            async def on_ready():
                nonlocal user_info
                try:
                    u = client.user
                    user_info = {
                        'id': str(u.id),
                        'name': u.name,
                        'discriminator': getattr(u, 'discriminator', '0000'),
                        'avatar_url': str(u.avatar.url) if u.avatar else None,
                        'bot': getattr(u, 'bot', False)
                    }
                except Exception as e:
                    pass
                await client.close()

            # 启动客户端并设置超时
            try:
                await asyncio.wait_for(client.start(token), timeout=15.0)  # 15秒超时
            except asyncio.TimeoutError:
                return False, None, "WebSocket连接超时"

            # 等待ready事件，最多等待10秒
            try:
                await asyncio.wait_for(client.wait_for('ready', timeout=10.0), timeout=10.0)
            except asyncio.TimeoutError:
                return False, None, "等待ready事件超时"

            if user_info:
                return True, user_info, None
            return False, None, "无法获取用户信息"

        except asyncio.TimeoutError:
            return False, None, "WebSocket连接超时"
        except discord.LoginFailure:
            return False, None, "Token登录失败"
        except Exception as e:
            error_msg = str(e)
            # 简化错误信息，避免返回复杂的内部错误
            if len(error_msg) > 50 or "sequence" in error_msg or "NoneType" in error_msg:
                return False, None, "WebSocket验证失败"
            return False, None, f"验证失败: {error_msg}"
        finally:
            if client and not client.is_closed():
                await client.close()


class DiscordManager:
    def __init__(self, log_callback=None):
        self.clients: List[AutoReplyClient] = []
        self.client_tasks: Dict[str, asyncio.Task] = {}
        self.accounts: List[Account] = []
        self.rules: List[Rule] = []
        self.block_settings = BlockSettings()
        self.is_running = False
        self.validator = TokenValidator()
        self.log_callback = log_callback
        self.max_parallel_starts: int = 10
        self.startup_timeout: float = 20.0

        # 轮换设置
        self.rotation_enabled: bool = False  # 是否启用账号轮换
        self.rotation_interval: int = 10  # 轮换间隔（秒），默认10秒
        self.current_rotation_index: int = 0  # 当前使用的账号索引
        self.reply_in_thread_mode: bool = False  # 是否启用子区回复模式

        # 消息去重跟踪 - 存储已回复的消息ID，避免重复回复
        self.replied_messages: Set[int] = set()
        self.max_replied_messages: int = 1000  # 最多跟踪1000条消息
        self.rotation_lock: Optional[asyncio.Lock] = None
        self.reply_locks: Dict[Tuple[int, str], asyncio.Lock] = {}
        self.rule_reply_accounts: Dict[Tuple[int, str], Set[str]] = {}
        self.rule_reply_order: List[Tuple[int, str]] = []
        self.max_rule_reply_records: int = 2000
        self.recent_replies: List[Dict] = []
        self.max_recent_replies: int = 1000
        self.rule_matcher: Optional[RuleSetMatcher] = None
        self.message_rule_matches: Dict[Tuple[int, str], Dict[str, str]] = {}
        self.message_rule_match_order: List[Tuple[int, str]] = []
        self.max_message_rule_matches: int = 2000

    async def _wait_before_reply_if_needed(self):
        block_settings = getattr(self, "block_settings", None)
        if block_settings is None:
            return

        delay_seconds = block_settings.choose_reply_delay_seconds()
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    def invalidate_rule_matcher(self):
        self.rule_matcher = None
        self.message_rule_matches.clear()
        self.message_rule_match_order.clear()

    def _ensure_rule_matcher(self) -> RuleSetMatcher:
        if self.rule_matcher is None:
            self.rule_matcher = RuleSetMatcher(self.rules)
        return self.rule_matcher

    def _trim_message_rule_matches(self):
        if len(self.message_rule_match_order) <= self.max_message_rule_matches:
            return

        remove_count = len(self.message_rule_match_order) // 2
        expired_keys = self.message_rule_match_order[:remove_count]
        self.message_rule_match_order = self.message_rule_match_order[remove_count:]
        for cache_key in expired_keys:
            self.message_rule_matches.pop(cache_key, None)

    def get_message_rule_matches(self, message, content: str) -> Dict[str, str]:
        if not content or not self.rules:
            return {}

        message_id = getattr(message, "id", 0) or 0
        normalized_content = _normalize_match_text(content).lower()
        cache_key = (message_id, hashlib.sha1(normalized_content.encode("utf-8")).hexdigest())

        cached_matches = self.message_rule_matches.get(cache_key)
        if cached_matches is not None:
            return cached_matches

        matched_keywords = self._ensure_rule_matcher().match_content(content)
        self.message_rule_matches[cache_key] = matched_keywords
        self.message_rule_match_order.append(cache_key)
        self._trim_message_rule_matches()
        return matched_keywords

    def _rule_matches_account(self, account: Account, rule: Rule) -> bool:
        return not account.rule_ids or rule.id in account.rule_ids

    def _get_available_accounts(self, channel_id: Optional[int] = None, rule: Optional[Rule] = None) -> List[Account]:
        return [
            acc for acc in self.accounts
            if acc.is_active
            and acc.is_valid
            and acc.allows_channel(channel_id)
            and (rule is None or self._rule_matches_account(acc, rule))
        ]

    @staticmethod
    def _can_account_send_now(account: Account, current_time: Optional[float] = None) -> bool:
        current_time = time.time() if current_time is None else current_time
        cooldown_until = getattr(account, "cooldown_until", None)
        if cooldown_until is not None and current_time < cooldown_until:
            return False
        if account.rate_limit_until is not None and current_time < account.rate_limit_until:
            return False
        return True

    @staticmethod
    def _build_message_reference(message):
        if not hasattr(message, "to_reference"):
            return None

        try:
            return message.to_reference(fail_if_not_exists=False)
        except TypeError:
            try:
                return message.to_reference()
            except Exception:
                return None
        except Exception:
            return None

    def _find_client_for_account(self, account: Account) -> Optional[AutoReplyClient]:
        return next((client for client in self.clients if client.account.token == account.token), None)

    async def _prepare_reply_thread(self, thread):
        if thread is None:
            return None

        if getattr(thread, "locked", False):
            return None

        if getattr(thread, "archived", False) and not getattr(thread, "locked", False):
            edit_method = getattr(thread, "edit", None)
            if callable(edit_method):
                try:
                    thread = await edit_method(archived=False)
                except Exception:
                    pass

        join_method = getattr(thread, "join", None)
        if callable(join_method):
            try:
                await join_method()
            except Exception:
                pass

        return thread

    async def _get_existing_reply_thread(self, message):
        thread = getattr(message, "thread", None)
        if thread is not None:
            return await self._prepare_reply_thread(thread)

        fetch_thread = getattr(message, "fetch_thread", None)
        if not callable(fetch_thread):
            return None

        try:
            thread = await fetch_thread()
        except (discord.NotFound, ValueError):
            return None
        except Exception:
            return None

        return await self._prepare_reply_thread(thread)

    async def _ensure_reply_thread(self, message):
        existing_thread = await self._get_existing_reply_thread(message)
        if existing_thread is not None:
            return existing_thread

        create_thread = getattr(message, "create_thread", None)
        if not callable(create_thread):
            return None

        try:
            thread = await create_thread(name=_build_reply_thread_name(message))
        except Exception:
            return await self._get_existing_reply_thread(message)

        return await self._prepare_reply_thread(thread)

    def _get_rotation_ordered_accounts(self, candidate_accounts: List[Account]) -> List[Account]:
        if not candidate_accounts:
            return []

        start_index = self.current_rotation_index % len(candidate_accounts)
        return candidate_accounts[start_index:] + candidate_accounts[:start_index]

    def _mark_rotation_cooldown(self, account: Account, sent_time: Optional[float] = None):
        if not self.rotation_enabled:
            return

        if self.rotation_interval > 0:
            account.cooldown_until = (sent_time or time.time()) + self.rotation_interval
        else:
            account.cooldown_until = None

    def _advance_rotation_index_after_account(self, candidate_accounts: List[Account], account: Account):
        if not self.rotation_enabled or not candidate_accounts:
            return

        for index, candidate in enumerate(candidate_accounts):
            if candidate.token == account.token:
                self.current_rotation_index = (index + 1) % len(candidate_accounts)
                return

    def _trim_replied_messages(self):
        if len(self.replied_messages) <= self.max_replied_messages:
            return

        sorted_messages = sorted(self.replied_messages)
        remove_count = len(sorted_messages) // 2
        for msg_id in sorted_messages[:remove_count]:
            self.replied_messages.remove(msg_id)

    def _trim_rule_reply_records(self):
        if len(self.rule_reply_order) <= self.max_rule_reply_records:
            return

        remove_count = len(self.rule_reply_order) // 2
        expired_keys = self.rule_reply_order[:remove_count]
        self.rule_reply_order = self.rule_reply_order[remove_count:]
        for reply_key in expired_keys:
            self.rule_reply_accounts.pop(reply_key, None)
            self.reply_locks.pop(reply_key, None)

    @staticmethod
    def _build_message_link(message) -> str:
        jump_url = getattr(message, "jump_url", None)
        if jump_url:
            return str(jump_url)

        channel_id = getattr(getattr(message, "channel", None), "id", None)
        message_id = getattr(message, "id", None)
        guild_id = getattr(getattr(message, "guild", None), "id", None)
        if channel_id is None or message_id is None:
            return ""

        guild_segment = str(guild_id) if guild_id is not None else "@me"
        return f"https://discord.com/channels/{guild_segment}/{channel_id}/{message_id}"

    def _remember_rule_reply(self, reply_key: Tuple[int, str], account_token: str):
        if reply_key not in self.rule_reply_accounts:
            self.rule_reply_accounts[reply_key] = set()
            self.rule_reply_order.append(reply_key)
            self._trim_rule_reply_records()

        self.rule_reply_accounts[reply_key].add(account_token)

    def _record_reply(self, account: Account, message, keyword: str, reply_text: str):
        account.reply_count = max(0, int(getattr(account, "reply_count", 0))) + 1
        account.last_sent_time = time.time()
        message_link = self._build_message_link(message)

        self.recent_replies.append({
            "timestamp": account.last_sent_time,
            "time_text": time.strftime("%H:%M:%S", time.localtime(account.last_sent_time)),
            "account_alias": account.alias,
            "keyword": keyword,
            "target": _get_message_author_label(message),
            "customer_message": getattr(message, "content", "") or "",
            "message_link": message_link,
            "reply_content": reply_text,
        })
        if len(self.recent_replies) > self.max_recent_replies:
            self.recent_replies = self.recent_replies[-self.max_recent_replies:]

        if self.log_callback:
            self.log_callback(_build_reply_log_message(account.alias, message))

    async def _send_reply_with_account(
        self,
        account: Account,
        message,
        reply_text: str,
        *,
        client=None,
        use_message_reply: bool = False,
        reply_thread=None,
    ) -> bool:
        current_time = time.time()
        if not self._can_account_send_now(account, current_time):
            return False

        try:
            if reply_thread is not None:
                if use_message_reply and hasattr(reply_thread, "send"):
                    await reply_thread.send(reply_text, mention_author=False)
                    return True

                client = client or self._find_client_for_account(account)
                if client is None:
                    return False

                thread_id = getattr(reply_thread, "id", None)
                guild_id = getattr(getattr(message, "guild", None), "id", None)
                if thread_id is None:
                    return False

                target_channel = client.get_partial_messageable(thread_id, guild_id=guild_id)
                await target_channel.send(reply_text, mention_author=False)
                return True

            if use_message_reply:
                await message.reply(reply_text)
                return True

            client = client or self._find_client_for_account(account)
            if client is None:
                return False

            channel_id = getattr(getattr(message, "channel", None), "id", None)
            guild_id = getattr(getattr(message, "guild", None), "id", None)
            if channel_id is None:
                return False

            target_channel = client.get_partial_messageable(channel_id, guild_id=guild_id)
            send_kwargs = {"mention_author": False}
            message_reference = self._build_message_reference(message)
            if message_reference is not None:
                send_kwargs["reference"] = message_reference
            await target_channel.send(reply_text, **send_kwargs)
            return True

        except discord.HTTPException as e:
            if e.code == 20016:  # 慢速模式
                account.rate_limit_until = current_time + 600
                if self.log_callback:
                    self.log_callback(f"[{account.alias}] 触发慢速模式，当前账号暂时跳过")
                return False
            if self.log_callback:
                self.log_callback(f"[{account.alias}] 发送失败: HTTP {e.code}")
            return False
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"[{account.alias}] 发送异常: {str(e)}")
            return False

    async def send_rule_replies(
        self,
        message,
        rule: Rule,
        *,
        matched_keyword: str,
        preferred_account: Optional[Account] = None,
        preferred_client=None,
    ) -> int:
        if self.rotation_enabled:
            if self.rotation_lock is None:
                self.rotation_lock = asyncio.Lock()

            async with self.rotation_lock:
                return await self._send_rule_replies_locked(
                    message,
                    rule,
                    matched_keyword=matched_keyword,
                    preferred_account=preferred_account,
                    preferred_client=preferred_client,
                )

        return await self._send_rule_replies_locked(
            message,
            rule,
            matched_keyword=matched_keyword,
            preferred_account=preferred_account,
            preferred_client=preferred_client,
        )

    async def _send_rule_replies_locked(
        self,
        message,
        rule: Rule,
        *,
        matched_keyword: str,
        preferred_account: Optional[Account] = None,
        preferred_client=None,
    ) -> int:
        reply_key = (getattr(message, "id", 0), rule.id)
        reply_lock = self.reply_locks.setdefault(reply_key, asyncio.Lock())

        async with reply_lock:
            already_replied_tokens = set(self.rule_reply_accounts.get(reply_key, set()))
            target_reply_count = max(1, min(3, int(getattr(rule, "reply_account_count", 1) or 1)))

            if len(already_replied_tokens) >= target_reply_count:
                return 0

            channel_id = getattr(getattr(message, "channel", None), "id", None)
            candidate_accounts = self._get_available_accounts(channel_id, rule)
            if not candidate_accounts:
                return 0

            await self._wait_before_reply_if_needed()
            reply_thread = await self._ensure_reply_thread(message) if self.reply_in_thread_mode else None
            if self.rotation_enabled:
                ordered_accounts = self._get_rotation_ordered_accounts(candidate_accounts)
            else:
                ordered_accounts = []
                if preferred_account is not None:
                    ordered_accounts.extend(
                        account for account in candidate_accounts
                        if account.token == preferred_account.token
                    )
                ordered_accounts.extend(
                    account for account in candidate_accounts
                    if preferred_account is None or account.token != preferred_account.token
                )

            success_count = 0
            primary_token = preferred_account.token if preferred_account is not None else None
            last_success_account: Optional[Account] = None

            for account in ordered_accounts:
                if account.token in already_replied_tokens:
                    continue

                use_message_reply = account.token == primary_token
                if use_message_reply:
                    send_success = await self._send_reply_with_account(
                        account,
                        message,
                        rule.reply,
                        client=preferred_client,
                        use_message_reply=True,
                        reply_thread=reply_thread,
                    )
                else:
                    send_success = await self._send_reply_with_account(
                        account,
                        message,
                        rule.reply,
                        reply_thread=reply_thread,
                    )

                if not send_success:
                    continue

                self._remember_rule_reply(reply_key, account.token)
                already_replied_tokens.add(account.token)
                sent_time = time.time()
                self._mark_rotation_cooldown(account, sent_time=sent_time)
                self._record_reply(account, message, matched_keyword, rule.reply)
                success_count += 1
                last_success_account = account

                if len(already_replied_tokens) >= target_reply_count:
                    break

            if last_success_account is not None:
                self._advance_rotation_index_after_account(candidate_accounts, last_success_account)

            return success_count

    async def add_account_async(self, token: str) -> Tuple[bool, Optional[str]]:
        if any(acc.token == token for acc in self.accounts):
            return False, "Token已存在"

        is_valid, user_info, msg = await self.validator.validate_token(token)

        # 即使验证失败也允许添加 (可能是网络问题)，但在UI显示无效
        account = Account(
            token=token,
            is_active=True,
            is_valid=is_valid or False,
            last_verified=time.time(),
            user_info=user_info,
            target_channels=[],
        )

        self.accounts.append(account)

        return True, "账号添加成功" + (f" ({user_info.get('name', 'Unknown')})" if user_info and isinstance(user_info, dict) else "")


    def remove_account(self, token: str):
        """移除账号"""
        self.accounts = [acc for acc in self.accounts if acc.token != token]

    def add_rule(self, keywords: List[str], reply: str, match_type: MatchType,
                 delay_min: float = 0.1, delay_max: float = 1.0,
                 ignore_replies: bool = True, ignore_mentions: bool = True,
                 case_sensitive: bool = False, exclude_keywords: Optional[List[str]] = None,
                 reply_account_count: int = 1):
        """添加规则"""
        # 生成唯一的规则ID
        import time
        rule_id = f"rule_{int(time.time() * 1000)}_{len(self.rules)}"

        rule = Rule(
            id=rule_id,
            keywords=keywords,
            reply=reply,
            match_type=match_type,
            target_channels=[],
            delay_min=delay_min,
            delay_max=delay_max,
            ignore_replies=ignore_replies,
            ignore_mentions=ignore_mentions,
            case_sensitive=case_sensitive,
            exclude_keywords=exclude_keywords or [],
            reply_account_count=reply_account_count,
        )
        self.rules.append(rule)
        self.invalidate_rule_matcher()

    def remove_rule(self, index: int):
        """移除规则"""
        if 0 <= index < len(self.rules):
            self.rules.pop(index)
            self.invalidate_rule_matcher()

    def update_rule(self, index: int, **kwargs):
        """更新规则"""
        if 0 <= index < len(self.rules):
            rule = self.rules[index]
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
            self.invalidate_rule_matcher()

    async def start_all_clients(self):
        if self.is_running:
            return

        await self.stop_all_clients()
        self.clients.clear()

        self.is_running = True

        active_clients: List[AutoReplyClient] = []

        for acc in self.accounts:
            if acc.is_active and acc.is_valid:
                rules = [r for r in self.rules if self._rule_matches_account(acc, r)]
                client = AutoReplyClient(acc, rules, self.log_callback, self)
                self.clients.append(client)
                active_clients.append(client)

        total_clients = len(active_clients)
        if total_clients == 0:
            self.is_running = False
            return

        for batch_start in range(0, total_clients, self.max_parallel_starts):
            batch_clients = active_clients[batch_start:batch_start + self.max_parallel_starts]

            for client in batch_clients:
                task = asyncio.create_task(client.start_client())
                self._track_client_task(client.account.token, task)

            await asyncio.gather(
                *(client.wait_for_startup(self.startup_timeout) for client in batch_clients),
                return_exceptions=True,
            )

            completed_count = min(batch_start + len(batch_clients), total_clients)
            if completed_count < total_clients and self.log_callback:
                self.log_callback(
                    f"📦 已完成 {completed_count}/{total_clients} 个账号连接尝试，继续分批启动..."
                )

    async def stop_all_clients(self):
        self.is_running = False

        tracked_tasks = list(self.client_tasks.values())

        for c in self.clients:
            try:
                await c.stop_client()
            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"停止账号 {c.account.alias} 时出错: {e}")

        if tracked_tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tracked_tasks, return_exceptions=True), timeout=10.0)
            except asyncio.TimeoutError:
                for task in tracked_tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tracked_tasks, return_exceptions=True)

        self.client_tasks.clear()
        self.clients.clear()

    def _track_client_task(self, token: str, task: asyncio.Task):
        self.client_tasks[token] = task

        def _cleanup(completed_task: asyncio.Task, account_token: str = token):
            self.client_tasks.pop(account_token, None)

        task.add_done_callback(_cleanup)

    async def revalidate_all_accounts(self) -> List[Dict]:
        """重新验证所有账号的Token"""
        results = []

        for account in self.accounts:
            is_valid, user_info, error_msg = await self.validator.validate_token(account.token)

            # 更新账号状态
            account.is_valid = is_valid
            account.last_verified = time.time()
            account.user_info = user_info

            results.append({
                'alias': account.alias,
                'is_valid': is_valid,
                'user_info': user_info,
                'error_msg': error_msg
            })

        return results

    def get_next_available_account(self, channel_id: Optional[int] = None) -> Optional[Account]:
        """获取下一个可用的账号（用于轮换）"""
        if not self.rotation_enabled or not self.accounts:
            return None

        available_accounts = self._get_available_accounts(channel_id)

        if not available_accounts:
            return None

        current_time = time.time()
        start_index = self.current_rotation_index % len(available_accounts)

        for offset in range(len(available_accounts)):
            next_index = (start_index + offset) % len(available_accounts)
            account = available_accounts[next_index]
            if self._can_account_send_now(account, current_time):
                self.current_rotation_index = next_index
                return account

        return None

    async def send_rotated_reply(self, message, reply_text: str, rule_name: str = "") -> bool:
        """使用轮换账号发送回复"""
        if not self.rotation_enabled:
            return False

        if self.rotation_lock is None:
            self.rotation_lock = asyncio.Lock()

        async with self.rotation_lock:
            return await self._send_rotated_reply_locked(message, reply_text, rule_name)

    async def _send_rotated_reply_locked(self, message, reply_text: str, rule_name: str = "") -> bool:
        """在轮换锁内发送回复，避免同一时刻多个账号同时发送"""
        if not self.rotation_enabled:
            return False

        # 检查这条消息是否已经被回复过
        if message.id in self.replied_messages:
            if self.log_callback:
                self.log_callback(f"⚠️ 消息 {message.id} 已被回复，跳过轮换回复")
            return False

        channel_id = getattr(getattr(message, "channel", None), "id", None)
        if channel_id is None:
            if self.log_callback:
                self.log_callback("❌ 无法识别消息频道，跳过轮换回复")
            return False

        available_accounts = self._get_available_accounts(channel_id)
        if not available_accounts:
            if self.log_callback:
                self.log_callback("❌ 没有可用于当前频道的轮换账号")
            return False

        await self._wait_before_reply_if_needed()
        start_index = self.current_rotation_index % len(available_accounts)
        message_reference = self._build_message_reference(message)
        guild_id = getattr(getattr(message, "guild", None), "id", None)
        reply_thread = await self._ensure_reply_thread(message) if self.reply_in_thread_mode else None

        for offset in range(len(available_accounts)):
            account_index = (start_index + offset) % len(available_accounts)
            account = available_accounts[account_index]
            current_time = time.time()

            if not self._can_account_send_now(account, current_time):
                continue

            client = self._find_client_for_account(account)
            if not client:
                if self.log_callback:
                    self.log_callback(f"❌ 找不到账号 {account.alias} 的客户端")
                continue

            try:
                target_channel_id = getattr(reply_thread, "id", None) if reply_thread is not None else channel_id
                target_channel = client.get_partial_messageable(target_channel_id, guild_id=guild_id)
                send_kwargs = {"mention_author": False}
                if reply_thread is None and message_reference is not None:
                    send_kwargs["reference"] = message_reference
                await target_channel.send(reply_text, **send_kwargs)

                self.replied_messages.add(message.id)
                self._trim_replied_messages()

                if self.rotation_interval > 0:
                    account.cooldown_until = current_time + self.rotation_interval
                self.current_rotation_index = (account_index + 1) % len(available_accounts)

                self._record_reply(account, message, rule_name, reply_text)

                return True

            except discord.HTTPException as e:
                if e.code == 20016:  # 慢速模式
                    account.rate_limit_until = current_time + 600  # 10分钟限制
                    if self.log_callback:
                        self.log_callback(f"⚠️ [{account.alias}] 触发慢速模式，切换下一个账号继续发送")
                elif e.code == 50035:  # 无效表单内容
                    if self.log_callback:
                        self.log_callback(f"❌ [{account.alias}] 发送失败: 无效内容")
                    return False
                else:
                    if self.log_callback:
                        self.log_callback(f"❌ [{account.alias}] 发送失败: HTTP {e.code}")

            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"❌ [{account.alias}] 发送异常: {str(e)}")

        if self.log_callback:
            self.log_callback("❌ 当前没有可立即发送的轮换账号，可能都在冷却或受限")
        return False

    async def revalidate_account(self, token: str) -> Tuple[bool, Optional[str]]:
        """重新验证指定账号的Token"""
        account = next((acc for acc in self.accounts if acc.token == token), None)
        if not account:
            return False, "账号不存在"

        is_valid, user_info, error_msg = await self.validator.validate_token(account.token)

        # 更新账号状态
        account.is_valid = is_valid
        account.last_verified = time.time()
        account.user_info = user_info

        if is_valid and user_info and isinstance(user_info, dict):
            username = f"{user_info.get('name', 'Unknown')}#{user_info.get('discriminator', '0000')}"
            return True, f"验证成功，用户名: {username}"
        else:
            return False, f"验证失败: {error_msg}"

    def get_status(self) -> Dict:
        """获取当前状态"""
        current_time = time.time()
        return {
            "is_running": self.is_running,
            "accounts": [
                {
                    "token": acc.token,
                    "alias": acc.alias,  # 现在是只读属性
                    "is_active": acc.is_active,
                    "is_running": any(c.account.token == acc.token and c.is_running for c in self.clients),
                    "reply_count": acc.reply_count,
                    "cooldown_until": acc.cooldown_until,
                    "cooldown_remaining_seconds": max(0, int((acc.cooldown_until or 0) - current_time)),
                }
                for acc in self.accounts
            ],
            "rules_count": len(self.rules),
            "active_rules": len([r for r in self.rules if r.is_active]),
            "recent_replies": list(reversed(self.recent_replies)),
        }
