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

    def __post_init__(self):
        if self.rule_ids is None:
            self.rule_ids = []

    @property
    def alias(self) -> str:
        """获取账号别名（使用用户名）"""
        if self.user_info:
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


class AutoReplyClient(discord.Client):
    def __init__(self, account: Account, rules: List[Rule], log_callback=None, *args, **kwargs):
        # 修正: discord.py-self 不需要也不支持 intents 参数
        # 直接调用父类构造函数即可
        super().__init__(*args, **kwargs)

        self.account = account
        self.rules = rules
        self.is_running = False
        self.log_callback = log_callback

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

        content_lower = content.lower()

        if rule.match_type == MatchType.PARTIAL:
            return any(keyword.lower() in content_lower for keyword in rule.keywords)
        elif rule.match_type == MatchType.EXACT:
            return content_lower in [k.lower() for k in rule.keywords]
        elif rule.match_type == MatchType.REGEX:
            return any(re.search(keyword, content, re.IGNORECASE) for keyword in rule.keywords)

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
        # 1. 先尝试 HTTP 验证 (更稳)
        http_res = await TokenValidator._validate_token_http(token)
        if http_res[0] is not None:
            return http_res

        # 2. 备选: WebSocket 验证
        return await TokenValidator._validate_token_websocket(token)

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
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://discord.com/api/v10/users/@me', headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        user_info = {
                            'id': data.get('id'),
                            'name': data.get('username'),
                            'discriminator': data.get('discriminator', '0000'),
                            'avatar_url': f"https://cdn.discordapp.com/avatars/{data['id']}/{data['avatar']}.png" if data.get('avatar') else None,
                            'bot': data.get('bot', False),
                            'token_type': 'bot' if data.get('bot') else 'user'
                        }
                        return True, user_info, None
                    elif resp.status == 401:
                        return False, None, "Token无效"
                    else:
                        return False, None, f"HTTP {resp.status}"
        except Exception as e:
            return None, None, str(e)

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

            # 启动并等待
            await client.start(token)

            if user_info:
                return True, user_info, None
            return False, None, "无法获取用户信息"

        except Exception as e:
            return False, None, str(e)
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

        return True, "账号添加成功" + (f" ({user_info['name']})" if user_info else "")

    def add_account(self, token: str, alias: str):
        """添加账号（同步版本，用于向后兼容）"""
        account = Account(token=token, alias=alias)
        self.accounts.append(account)

    def remove_account(self, token: str):
        """移除账号"""
        self.accounts = [acc for acc in self.accounts if acc.token != token]

    def add_rule(self, keywords: List[str], reply: str, match_type: MatchType,
                 target_channels: List[int], delay_min: float = 0.1, delay_max: float = 1.0,
                 ignore_replies: bool = True, ignore_mentions: bool = True):
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
            ignore_mentions=ignore_mentions
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
                client = AutoReplyClient(acc, rules, self.log_callback)
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

        if is_valid and user_info:
            username = f"{user_info['name']}#{user_info['discriminator']}"
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
