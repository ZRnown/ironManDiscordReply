import asyncio
import discord
import re
import random
import time
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# discord.py-self 不需要Intents


class MatchType(Enum):
    PARTIAL = "partial"
    EXACT = "exact"
    REGEX = "regex"


@dataclass
class Account:
    token: str
    is_active: bool = True
    is_valid: bool = False  # Token验证状态
    last_verified: Optional[float] = None  # 最后验证时间
    user_info: Optional[Dict] = None  # 用户信息
    rule_ids: List[str] = None  # 关联的规则ID列表
    last_sent_time: Optional[float] = None  # 最后发送消息时间
    rate_limit_until: Optional[float] = None  # 频率限制到期时间

    def __post_init__(self):
        if self.rule_ids is None:
            self.rule_ids = []

    @property
    def alias(self) -> str:
        """获取账号别名（使用用户名）"""
        if self.user_info and isinstance(self.user_info, dict):
            return f"{self.user_info.get('name', 'Unknown')}#{self.user_info.get('discriminator', '0000')}"
        return f"Token-{self.token[:8]}..."


@dataclass
class Rule:
    id: str  # 规则唯一标识
    keywords: List[str]
    reply: str
    match_type: MatchType
    target_channels: List[int]
    delay_min: float = 0.1
    delay_max: float = 1.0
    is_active: bool = True
    ignore_replies: bool = True  # 是否忽略回复他人的消息
    ignore_mentions: bool = True  # 是否忽略包含@他人的消息
    case_sensitive: bool = False  # 是否区分大小写，False表示不区分大小写


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

        except Exception as e:
            error_msg = f"[{self.account.alias}] on_ready事件错误: {e}"
            print(error_msg)
            if self.log_callback:
                self.log_callback(error_msg)
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

        for rule in self.rules:
            if not rule.is_active:
                continue

            if rule.target_channels and message.channel.id not in rule.target_channels:
                continue

            if rule.ignore_replies and message.reference is not None:
                continue

            if rule.ignore_mentions and message.mentions:
                continue

            if self._check_match(message.content, rule):
                match_msg = f"[{self.account.alias}] 🎯 匹配到关键词 | 消息: '{message.content}' | 来自: {message.author.name} | 频道: #{message.channel.name}"
                reply_msg = f"[{self.account.alias}] 🤖 准备回复: '{rule.reply}'"

                print(match_msg)
                print(reply_msg)
                if self.log_callback:
                    self.log_callback(match_msg)
                    self.log_callback(reply_msg)

                try:
                    delay = random.uniform(rule.delay_min, rule.delay_max)
                    delay_msg = f"[{self.account.alias}] ⏱️  等待 {delay:.1f} 秒..."
                    print(delay_msg)
                    if self.log_callback:
                        self.log_callback(delay_msg)

                    try:
                        async with message.channel.typing():
                            await asyncio.sleep(delay)
                    except Exception:
                        await asyncio.sleep(delay)

                    # 检查是否启用轮换模式
                    if (self.discord_manager and
                        self.discord_manager.rotation_enabled and
                        rule.target_channels and
                        message.channel.id in rule.target_channels):
                        # 使用轮换模式
                        success = await self.discord_manager.send_rotated_reply(
                            message, rule.reply, rule.keywords[0] if rule.keywords else ""
                        )
                        if success:
                            success_msg = f"[{self.account.alias}] ✅ 轮换回复成功"
                            print(success_msg)
                            if self.log_callback:
                                self.log_callback(success_msg)
                        else:
                            error_msg = f"[{self.account.alias}] ❌ 轮换回复失败"
                            print(error_msg)
                            if self.log_callback:
                                self.log_callback(error_msg)
                    else:
                        # 使用普通回复
                        await message.reply(rule.reply)
                        success_msg = f"[{self.account.alias}] ✅ 回复成功"
                        print(success_msg)
                        if self.log_callback:
                            self.log_callback(success_msg)

                    break # 只处理第一个匹配规则

                except Exception as e:
                    error_msg = f"[{self.account.alias}] ❌ 回复失败: {e}"
                    print(error_msg)
                    if self.log_callback:
                        self.log_callback(error_msg)

                break

    def _check_match(self, content: str, rule: Rule) -> bool:
        """检查消息内容是否匹配规则"""
        if not content:
            return False

        if rule.match_type == MatchType.PARTIAL:
            if rule.case_sensitive:
                # 区分大小写
                return any(keyword in content for keyword in rule.keywords)
            else:
                # 不区分大小写
                content_lower = content.lower()
                return any(keyword.lower() in content_lower for keyword in rule.keywords)
        elif rule.match_type == MatchType.EXACT:
            if rule.case_sensitive:
                # 区分大小写
                return content in rule.keywords
            else:
                # 不区分大小写
                content_lower = content.lower()
                return content_lower in [k.lower() for k in rule.keywords]
        elif rule.match_type == MatchType.REGEX:
            flags = 0 if rule.case_sensitive else re.IGNORECASE
            return any(re.search(keyword, content, flags) for keyword in rule.keywords)

        return False

    async def start_client(self):
        try:
            self.is_running = False

            # 启动客户端
            await self.start(self.account.token)

            # 等待on_ready事件，最多等待10秒
            try:
                await asyncio.wait_for(self.wait_for('ready', timeout=10.0), timeout=10.0)
                # 如果能到达这里，说明on_ready已经成功执行，is_running已经被设置为True
            except asyncio.TimeoutError:
                error_msg = f"[{self.account.alias}] 连接超时：等待ready事件超时"
                print(error_msg)
                if self.log_callback:
                    self.log_callback(error_msg)
                self.is_running = False
                await self.close()

        except discord.LoginFailure as e:
            error_msg = f"[{self.account.alias}] 登录失败: Token无效 - {e}"
            print(error_msg)
            if self.log_callback:
                self.log_callback(error_msg)
            self.is_running = False

        except Exception as e:
            error_msg = f"[{self.account.alias}] 启动失败: {e}"
            print(error_msg)
            if self.log_callback:
                self.log_callback(error_msg)
            self.is_running = False

    async def stop_client(self):
        """停止客户端"""
        self.is_running = False
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
        self.accounts: List[Account] = []
        self.rules: List[Rule] = []
        self.is_running = False
        self.validator = TokenValidator()
        self.log_callback = log_callback

        # 轮换设置
        self.rotation_enabled: bool = False  # 是否启用账号轮换
        self.rotation_interval: int = 10  # 轮换间隔（秒），默认10秒
        self.current_rotation_index: int = 0  # 当前使用的账号索引

        # 消息去重跟踪 - 存储已回复的消息ID，避免重复回复
        self.replied_messages: Set[int] = set()
        self.max_replied_messages: int = 1000  # 最多跟踪1000条消息

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
            user_info=user_info
        )

        self.accounts.append(account)

        return True, "账号添加成功" + (f" ({user_info.get('name', 'Unknown')})" if user_info and isinstance(user_info, dict) else "")


    def remove_account(self, token: str):
        """移除账号"""
        self.accounts = [acc for acc in self.accounts if acc.token != token]

    def add_rule(self, keywords: List[str], reply: str, match_type: MatchType,
                 target_channels: List[int], delay_min: float = 0.1, delay_max: float = 1.0,
                 ignore_replies: bool = True, ignore_mentions: bool = True,
                 case_sensitive: bool = False):
        """添加规则"""
        # 生成唯一的规则ID
        import time
        rule_id = f"rule_{int(time.time() * 1000)}_{len(self.rules)}"

        rule = Rule(
            id=rule_id,
            keywords=keywords,
            reply=reply,
            match_type=match_type,
            target_channels=target_channels,
            delay_min=delay_min,
            delay_max=delay_max,
            ignore_replies=ignore_replies,
            ignore_mentions=ignore_mentions,
            case_sensitive=case_sensitive
        )
        self.rules.append(rule)

    def remove_rule(self, index: int):
        """移除规则"""
        if 0 <= index < len(self.rules):
            self.rules.pop(index)

    def update_rule(self, index: int, **kwargs):
        """更新规则"""
        if 0 <= index < len(self.rules):
            rule = self.rules[index]
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)

    async def start_all_clients(self):
        if self.is_running: return

        self.is_running = True

        await self.stop_all_clients()
        self.clients.clear()

        for acc in self.accounts:
            if acc.is_active and acc.is_valid:
                rules = [r for r in self.rules if r.id in acc.rule_ids]
                client = AutoReplyClient(acc, rules, self.log_callback, self)
                self.clients.append(client)
                # 创建启动任务，让它们在后台运行
                asyncio.create_task(client.start_client())

        # 不在这里检查状态，让调用者负责等待和状态检查

    async def stop_all_clients(self):
        self.is_running = False

        for c in self.clients:
            await c.stop_client()

        self.clients.clear()

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

    def get_next_available_account(self) -> Optional[Account]:
        """获取下一个可用的账号（用于轮换）"""
        if not self.rotation_enabled or not self.accounts:
            return None

        # 查找所有有效的活跃账号
        available_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]

        if not available_accounts:
            return None

        # 检查当前账号是否可以发送
        current_time = time.time()
        current_account = available_accounts[self.current_rotation_index % len(available_accounts)]

        # 如果当前账号没有频率限制或限制已过期，可以使用
        if (current_account.rate_limit_until is None or
            current_time >= current_account.rate_limit_until):
            return current_account

        # 否则，寻找下一个可用的账号
        for i in range(1, len(available_accounts)):
            next_index = (self.current_rotation_index + i) % len(available_accounts)
            account = available_accounts[next_index]
            if (account.rate_limit_until is None or
                current_time >= account.rate_limit_until):
                self.current_rotation_index = next_index
                return account

        # 如果所有账号都被限制，返回None
        return None

    async def send_rotated_reply(self, message, reply_text: str, rule_name: str = "") -> bool:
        """使用轮换账号发送回复"""
        if not self.rotation_enabled:
            return False

        # 检查这条消息是否已经被回复过
        if message.id in self.replied_messages:
            if self.log_callback:
                self.log_callback(f"⚠️ 消息 {message.id} 已被回复，跳过轮换回复")
            return False

        account = self.get_next_available_account()
        if not account:
            if self.log_callback:
                self.log_callback(f"❌ 所有账号都被频率限制，无法发送回复")
            return False

        # 查找对应的客户端
        client = next((c for c in self.clients if c.account.token == account.token), None)
        if not client:
            if self.log_callback:
                self.log_callback(f"❌ 找不到账号 {account.alias} 的客户端")
            return False

        try:
            # 标记这条消息已被回复
            self.replied_messages.add(message.id)

            # 清理过期的消息ID（保持内存使用合理）
            if len(self.replied_messages) > self.max_replied_messages:
                # 移除最旧的一半消息
                sorted_messages = sorted(self.replied_messages)
                remove_count = len(sorted_messages) // 2
                for msg_id in sorted_messages[:remove_count]:
                    self.replied_messages.remove(msg_id)

            # 更新账号的最后发送时间
            current_time = time.time()
            account.last_sent_time = current_time

            # 发送消息
            await message.reply(reply_text)

            # 移动到下一个账号
            available_accounts = [acc for acc in self.accounts if acc.is_active and acc.is_valid]
            if available_accounts:
                self.current_rotation_index = (self.current_rotation_index + 1) % len(available_accounts)

            if self.log_callback:
                self.log_callback(f"✅ [{account.alias}] 轮换回复成功: '{reply_text[:50]}...'")

            return True

        except discord.HTTPException as e:
            # 检查是否是频率限制错误
            if e.code == 20016:  # 慢速模式
                account.rate_limit_until = current_time + 600  # 10分钟限制
                if self.log_callback:
                    self.log_callback(f"⚠️ [{account.alias}] 触发慢速模式，10分钟内无法发送")
            elif e.code == 50035:  # 无效表单内容
                if self.log_callback:
                    self.log_callback(f"❌ [{account.alias}] 发送失败: 无效内容")
            else:
                if self.log_callback:
                    self.log_callback(f"❌ [{account.alias}] 发送失败: HTTP {e.code}")

            # 尝试下一个账号
            return await self.send_rotated_reply(message, reply_text, rule_name)

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ [{account.alias}] 发送异常: {str(e)}")
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
        return {
            "is_running": self.is_running,
            "accounts": [
                {
                    "token": acc.token,
                    "alias": acc.alias,  # 现在是只读属性
                    "is_active": acc.is_active,
                    "is_running": any(c.account.token == acc.token and c.is_running for c in self.clients)
                }
                for acc in self.accounts
            ],
            "rules_count": len(self.rules),
            "active_rules": len([r for r in self.rules if r.is_active])
        }
