"""
Telegram 消息监听模块
实现基本的消息监听和日志记录功能
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneNumberInvalidError,
    FloodWaitError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError
)
from config.config import (
    API_ID, API_HASH, PHONE_NUMBER, MONITOR_GROUPS, LLM_ENABLED,
    get_session_file, list_available_sessions, validate_config
)
from utils.llm_util import get_llm_instance
from utils.signin_scheduler import SigninScheduler
from utils.reply_counter import ReplyCounter

logger = logging.getLogger(__name__)

class TelegramListener:
    """Telegram 消息监听器"""
    
    def __init__(self, session_name=None, account_pool=None):
        """
        初始化监听器
        +447464736880
        Args:
            session_name: Session 名称，如果为 None 则会在启动时让用户选择或输入
            account_pool: 账号池管理器（用于轮询回复）
        """
        validate_config()
        self.session_name = session_name
        self.session_file = get_session_file(session_name) if session_name else None
        self.client = None  # 稍后初始化
        self.monitor_groups = MONITOR_GROUPS
        self.llm = None  # LLM 实例，延迟初始化
        self.signin_scheduler = None  # 签到调度器
        self.reply_counter = None  # 回复计数器，延迟初始化（仅用于监听器账号）
        self.account_pool = account_pool  # 账号池（用于轮询回复）
        
    def _select_or_create_session(self):
        """选择或创建 session"""
        available_sessions = list_available_sessions()
        is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else True
        
        if available_sessions:
            if is_interactive:
                print("\n可用的 Session 列表:")
                for idx, session in enumerate(available_sessions, 1):
                    print(f"  {idx}. {session}")
                print(f"  {len(available_sessions) + 1}. 创建新的 Session")
                
                choice = input(f"\n请选择 (1-{len(available_sessions) + 1})，或直接输入新的 Session 名称: ").strip()
                
                # 检查是否是数字选择
                if choice.isdigit():
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(available_sessions):
                        self.session_name = available_sessions[choice_num - 1]
                        logger.info(f"选择使用已有 Session: {self.session_name}")
                    elif choice_num == len(available_sessions) + 1:
                        # 创建新的
                        self.session_name = input("请输入新 Session 的名称: ").strip() or 'telegram_session'
                        logger.info(f"创建新 Session: {self.session_name}")
                    else:
                        logger.warning("无效选择，使用默认 Session 名称")
                        self.session_name = 'telegram_session'
                else:
                    # 直接输入名称
                    self.session_name = choice or 'telegram_session'
                    logger.info(f"使用 Session 名称: {self.session_name}")
            else:
                # 非交互式环境（如 systemd 服务），使用第一个 session
                logger.info("非交互式环境，自动使用第一个 session")
                self.session_name = available_sessions[0]
                logger.info(f"选择使用已有 Session: {self.session_name}")
        else:
            # 没有已有 session
            if is_interactive:
                print("\n未找到已有 Session，需要创建新的。")
                self.session_name = input("请输入 Session 名称（直接回车使用默认名称 'telegram_session'）: ").strip() or 'telegram_session'
            else:
                # 非交互式环境，使用默认名称
                self.session_name = 'telegram_session'
                logger.info("非交互式环境，使用默认 Session 名称")
            logger.info(f"创建新 Session: {self.session_name}")
        
        # 设置 session 文件路径
        self.session_file = get_session_file(self.session_name)
        logger.info(f"Session 文件路径: {self.session_file}")
        
        # 初始化客户端（API_ID 需要转换为整数）
        self.client = TelegramClient(self.session_file, int(API_ID), API_HASH)
        
    async def start(self):
        """启动客户端并连接"""
        try:
            # 如果还没有选择 session，先选择或创建
            if self.client is None:
                self._select_or_create_session()
            
            # 检查是否已有 session 文件
            session_path = Path(self.session_file)
            session_exists = session_path.exists() or session_path.with_suffix('.session').exists()
            if session_exists:
                logger.info(f"发现已存在的 session 文件: {self.session_file}")
            
            # 确定要使用的手机号（如果 session 名称是手机号，优先使用）
            phone_to_use = PHONE_NUMBER
            is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else True
            if self.session_name and (self.session_name.startswith('+') or self.session_name.replace(' ', '').isdigit()):
                # Session 名称看起来像手机号
                if is_interactive:
                    # 交互式环境，询问是否使用
                    use_session_as_phone = input(f"检测到 Session 名称 '{self.session_name}' 可能是手机号，是否使用它登录？(Y/n): ").strip().lower()
                    if use_session_as_phone != 'n':
                        phone_to_use = self.session_name
                        logger.info(f"使用 Session 名称作为手机号: {phone_to_use}")
                else:
                    # 非交互式环境，自动使用 session 名称作为手机号
                    phone_to_use = self.session_name
                    logger.info(f"非交互式环境，自动使用 Session 名称作为手机号: {phone_to_use}")
            
            # 先连接客户端（必须在使用前连接）
            logger.info("正在连接 Telegram...")
            await self.client.connect()
            
            # 检查是否已授权（必须在连接后检查）
            if not await self.client.is_user_authorized():
                logger.info("未授权，开始登录流程...")
                logger.info(f"正在向 {phone_to_use} 发送验证码...")
                
                try:
                    # 发送验证码请求
                    sent_code = await self.client.send_code_request(phone_to_use)
                    logger.info("✅ 验证码请求已发送")
                    logger.info(f"📱 验证码将通过 {sent_code.type} 发送")
                    
                    # 显示提示信息
                    print("\n" + "="*60)
                    print("📱 验证码发送提示:")
                    print(f"   手机号: {phone_to_use}")
                    if hasattr(sent_code, 'phone_code_hash'):
                        print(f"   验证码哈希: {sent_code.phone_code_hash[:10]}...")
                    if hasattr(sent_code, 'type'):
                        code_type = str(sent_code.type).split('.')[-1] if sent_code.type else "未知"
                        print(f"   发送方式: {code_type}")
                    print("   请检查你的 Telegram 应用或短信")
                    print("   如果长时间未收到，请检查:")
                    print("   1. 手机号是否正确")
                    print("   2. 网络连接是否正常")
                    print("   3. Telegram 应用是否正常运行")
                    print("="*60 + "\n")
                    
                    # 请求输入验证码（支持重试）
                    max_retries = 3
                    is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else True
                    if not is_interactive:
                        logger.error("非交互式环境无法输入验证码，请先使用交互式方式登录")
                        raise ValueError("非交互式环境需要已登录的 session")
                    
                    for attempt in range(max_retries):
                        try:
                            code = input(f'请输入 Telegram 发送的验证码 (尝试 {attempt + 1}/{max_retries}): ').strip()
                            
                            if not code:
                                logger.warning("验证码不能为空")
                                continue
                            
                            logger.info(f"正在验证代码: {code[:2]}****")
                            try:
                                await self.client.sign_in(phone_to_use, code)
                                logger.info("✅ 验证码验证成功")
                                break
                            except SessionPasswordNeededError:
                                # 需要两步验证密码
                                logger.info("需要两步验证密码")
                                password = input('请输入两步验证密码: ')
                                await self.client.sign_in(password=password)
                                logger.info("✅ 两步验证成功")
                                break
                            
                        except PhoneCodeInvalidError:
                            logger.error(f"❌ 验证码错误 (尝试 {attempt + 1}/{max_retries})")
                            if attempt < max_retries - 1:
                                retry = input("是否重新发送验证码？(y/N): ").strip().lower()
                                if retry == 'y':
                                    sent_code = await self.client.send_code_request(phone_to_use)
                                    logger.info("✅ 已重新发送验证码")
                                else:
                                    logger.info("继续使用当前验证码...")
                            else:
                                raise Exception("验证码错误次数过多，请重新运行程序")
                                
                        except PhoneCodeExpiredError:
                            logger.error("❌ 验证码已过期")
                            retry = input("是否重新发送验证码？(y/N): ").strip().lower()
                            if retry == 'y':
                                sent_code = await self.client.send_code_request(phone_to_use)
                                logger.info("✅ 已重新发送验证码")
                                attempt = -1  # 重置计数器
                            else:
                                raise Exception("验证码已过期，请重新运行程序")
                                
                        except FloodWaitError as e:
                            wait_time = e.seconds
                            logger.error(f"❌ 请求过于频繁，请等待 {wait_time} 秒后重试")
                            raise Exception(f"请求过于频繁，请等待 {wait_time} 秒后重试")
                    
                    # 登录成功后，telethon 会自动保存 session
                    logger.info(f"✅ 登录成功，Session 已自动保存到: {self.session_file}")
                    
                except PhoneNumberInvalidError:
                    logger.error(f"❌ 手机号格式错误: {phone_to_use}")
                    logger.error("   请确保手机号格式正确，例如: +8613800138000")
                    logger.error("   注意: 手机号必须包含国家代码（如 +86 表示中国）")
                    raise
                except Exception as e:
                    logger.error(f"❌ 发送验证码失败: {e}")
                    logger.error("   可能的原因:")
                    logger.error("   1. 手机号格式错误")
                    logger.error("   2. 网络连接问题")
                    logger.error("   3. API_ID 或 API_HASH 配置错误")
                    logger.error("   4. Telegram 服务暂时不可用")
                    raise
            else:
                logger.info("使用已保存的 session，无需重新登录")
            
            # 获取当前用户信息
            me = await self.client.get_me()
            logger.info(f"已登录账号: {me.first_name} (@{me.username})")
            logger.info(f"账号 ID: {me.id}")
            
            # 初始化回复计数器（需要 session_name）
            if self.session_name:
                try:
                    self.reply_counter = ReplyCounter(self.session_name)
                    current_count, max_count = self.reply_counter.get_count()
                    logger.info(f"📊 回复计数: {current_count}/{max_count}")
                except Exception as e:
                    logger.warning(f"初始化回复计数器失败，将不限制回复数量: {e}")
                    self.reply_counter = None
            else:
                logger.warning("Session 名称为空，无法初始化回复计数器")
            
            # 注册消息处理器
            self._register_handlers()
            
            # 显示监听的群组
            await self._list_monitor_groups()
            
            logger.info("开始监听消息...")
            # 注意：不在这里启动签到任务，由主启动类统一管理
            # 也不在这里调用 run_until_disconnected，由主启动类控制
            
        except SessionPasswordNeededError:
            logger.error("需要两步验证密码，但密码输入失败")
            raise
        except Exception as e:
            logger.error(f"启动失败: {e}", exc_info=True)
            raise
    
    async def start_with_existing_client(self):
        """
        使用已有的客户端启动监听器（从账号池中复用客户端）
        注意：客户端必须已经连接
        """
        try:
            if self.client is None:
                raise ValueError("客户端未设置，无法启动监听器")
            
            # 检查客户端是否已连接
            if not self.client.is_connected():
                logger.warning("客户端未连接，尝试连接...")
                await self.client.connect()
            
            # 检查是否已授权
            if not await self.client.is_user_authorized():
                raise ValueError("客户端未授权，无法启动监听器")
            
            # 获取当前用户信息
            me = await self.client.get_me()
            logger.info(f"已登录账号: {me.first_name} (@{me.username})")
            logger.info(f"账号 ID: {me.id}")
            
            # 注册消息处理器
            self._register_handlers()
            
            # 显示监听的群组
            await self._list_monitor_groups()
            
            logger.info("开始监听消息...")
            
        except Exception as e:
            logger.error(f"启动失败: {e}", exc_info=True)
            raise
    
    def _register_handlers(self):
        """注册消息事件处理器"""
        
        @self.client.on(events.NewMessage)
        async def message_handler(event):
            """处理新消息事件"""
            try:
                # 获取消息信息
                chat = await event.get_chat()
                sender = await event.get_sender()
                message = event.message
                
                # 检查是否在监听的群组中
                chat_title = getattr(chat, 'title', None) or getattr(chat, 'username', None) or '未知'
                chat_id = chat.id
                
                # 判断是否应该监听此聊天（群组/频道/私聊）
                should_monitor = False
                if self.monitor_groups:
                    # 如果配置了监听列表，检查是否匹配
                    for group_identifier in self.monitor_groups:
                        # 支持多种匹配方式：
                        # 1. 直接匹配 ID（支持正数和负数格式）
                        # 2. 匹配标题
                        # 3. 匹配用户名
                        identifier_str = str(group_identifier).strip()
                        chat_id_str = str(chat_id)
                        
                        # 处理 ID 格式差异（正数/负数）
                        if identifier_str.lstrip('-').isdigit():
                            identifier_id = int(identifier_str)
                            chat_id_int = int(chat_id_str)
                            # 匹配 ID（考虑正负数格式）
                            if abs(identifier_id) == abs(chat_id_int):
                                should_monitor = True
                                break
                        
                        # 匹配标题或用户名
                        if (chat_title == identifier_str or 
                            getattr(chat, 'username', '') == identifier_str or
                            identifier_str in chat_title):
                            should_monitor = True
                            break
                else:
                    # 如果没有配置，监听所有聊天（群组/频道/私聊）
                    should_monitor = True
                
                if should_monitor:
                    # 记录消息信息
                    sender_name = getattr(sender, 'first_name', '') or getattr(sender, 'username', '') or '未知'
                    message_text = message.message or '[媒体/贴纸/其他]'
                    
                    # 判断聊天类型
                    if getattr(chat, 'megagroup', False):
                        chat_type = "👥 群组"
                    elif getattr(chat, 'broadcast', False):
                        chat_type = "📢 频道"
                    else:
                        chat_type = "💬 私聊"
                    
                    logger.info(f"📨 收到消息 [{chat_type}]")
                    logger.info(f"   聊天: {chat_title} (ID: {chat_id})")
                    logger.info(f"   发送者: {sender_name}")
                    logger.info(f"   内容: {message_text[:100]}")  # 只显示前100个字符
                    
                    # 这里后续可以添加消息处理逻辑
                    await self._handle_message(event, chat, sender, message)
                
            except Exception as e:
                logger.error(f"处理消息时出错: {e}", exc_info=True)
    
    async def _handle_message(self, event, chat, sender, message):
        """
        处理消息的核心逻辑
        包括消息过滤、LLM 调用和自动回复
        """
        try:
            # 如果 LLM 功能已禁用，直接返回
            if not LLM_ENABLED:
                return
            
            # 获取消息文本
            message_text = message.message
            if not message_text:
                # 忽略非文本消息（图片、视频等）
                return
            
            # 获取当前用户信息（用于判断是否是自己发送的消息）
            me = await self.client.get_me()
            sender_id = getattr(sender, 'id', None)
            sender_name = getattr(sender, 'first_name', '') or getattr(sender, 'username', '') or '未知'
            
            # 过滤条件1: 忽略自己发送的消息（包括监听器账号和账号池中的所有账号）
            if sender_id == me.id:
                logger.info(f"⏭️  忽略监听器账号自己发送的消息 (发送者: {sender_name}, ID: {sender_id})")
                return
            
            # 检查是否是账号池中的账号发送的消息
            if self.account_pool and sender_id in self.account_pool.account_ids:
                logger.info(f"⏭️  忽略账号池中账号发送的消息 (发送者: {sender_name}, ID: {sender_id}, 账号池IDs: {self.account_pool.account_ids})")
                return
            
            # 过滤条件2: 只处理长度小于15个字的消息
            message_length = len(message_text.strip())
            if message_length >= 15:
                logger.info(f"⏭️  消息长度 {message_length} >= 15，忽略处理")
                return
            
            # 过滤条件3: 忽略包含"签到"关键词的消息
            if "签到" in message_text:
                logger.info(f"⏭️  消息包含'签到'关键词，忽略处理")
                return
            
            # 过滤条件4: 忽略空消息
            if message_length == 0:
                logger.info(f"⏭️  消息为空，忽略处理")
                return
            
            logger.info(f"📝 准备生成回复，消息: '{message_text[:50]}', 长度: {message_length}, 发送者: {sender_name} (ID: {sender_id})")
            
            # 选择用于回复的账号（从账号池中轮询选择）
            reply_account = None
            if self.account_pool and len(self.account_pool.accounts) > 0:
                # 使用账号池轮询选择账号
                account_result = self.account_pool.get_next_account()
                if account_result:
                    reply_session_name, reply_client, reply_counter = account_result
                    reply_account = {
                        'session_name': reply_session_name,
                        'client': reply_client,
                        'reply_counter': reply_counter
                    }
                    logger.info(f"🔄 选择账号 '{reply_session_name}' 进行回复")
                else:
                    # 账号池中所有账号都达到上限，尝试使用监听器账号回复
                    logger.warning("⚠️  账号池中所有账号都已达到回复上限，尝试使用监听器账号回复")
                    if self.reply_counter:
                        can_reply, current_count, max_count = self.reply_counter.can_reply()
                        if can_reply:
                            reply_account = {
                                'session_name': self.session_name,
                                'client': self.client,
                                'reply_counter': self.reply_counter
                            }
                            logger.info(f"🔄 切换到监听器账号 '{self.session_name}' 进行回复 ({current_count}/{max_count})")
                        else:
                            logger.warning(f"⛔ 监听器账号 '{self.session_name}' 也已达到回复上限 ({current_count}/{max_count})，无法回复")
                            return
                    else:
                        logger.warning("⚠️  监听器账号没有回复计数器，无法回复")
                        return
            else:
                # 没有账号池，使用监听器自己的账号回复
                if self.reply_counter:
                    can_reply, current_count, max_count = self.reply_counter.can_reply()
                    if not can_reply:
                        logger.info(f"⛔ 账号 '{self.session_name}' 已达到回复上限 ({current_count}/{max_count})，跳过回复")
                        return
                    logger.debug(f"📊 当前回复计数: {current_count}/{max_count}")
                
                reply_account = {
                    'session_name': self.session_name,
                    'client': self.client,
                    'reply_counter': self.reply_counter
                }
            
            # 在调用LLM之前，再次确认账号是否可以回复（防止竞态条件）
            if reply_account['reply_counter']:
                can_reply, current_count, max_count = reply_account['reply_counter'].can_reply()
                if not can_reply:
                    logger.info(f"⛔ 账号 '{reply_account['session_name']}' 已达到回复上限 ({current_count}/{max_count})，跳过LLM调用")
                    return
            
            # 初始化 LLM（延迟初始化）
            if self.llm is None:
                try:
                    self.llm = get_llm_instance()
                    logger.info("LLM 实例初始化成功")
                except Exception as e:
                    logger.error(f"LLM 初始化失败，将跳过回复: {e}")
                    return
            
            # 调用 LLM 生成回复
            try:
                reply_text = await self.llm.generate_reply(message_text)
                
                if reply_text:
                    # 尝试发送回复（如果账号无法访问群组，会尝试其他账号）
                    success = await self._try_send_reply(
                        reply_account, 
                        event.chat_id, 
                        reply_text
                    )
                    
                    if success:
                        # 增加回复计数
                        reply_counter = reply_account['reply_counter']
                        if reply_counter:
                            success, new_count, max_count = reply_counter.increment()
                            if success:
                                logger.info(f"📊 账号 '{reply_account['session_name']}' 回复计数已更新: {new_count}/{max_count}")
                            else:
                                logger.warning("回复计数更新失败，但消息已发送")
                else:
                    logger.warning("LLM 返回空回复，跳过发送")
                    
            except Exception as e:
                logger.error(f"生成或发送回复失败: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"处理消息时出错: {e}", exc_info=True)
    
    async def _try_send_reply(self, initial_account, chat_id, reply_text):
        """
        尝试发送回复，如果账号未加入群组，则直接跳过
        
        Args:
            initial_account: 选中的账号 {'session_name': str, 'client': TelegramClient, 'reply_counter': ReplyCounter}
            chat_id: 聊天 ID
            reply_text: 回复文本
        
        Returns:
            bool: 是否成功发送
        """
        try:
            await initial_account['client'].send_message(chat_id, reply_text)
            logger.info(f"✅ 已通过账号 '{initial_account['session_name']}' 发送回复: {reply_text[:50]}...")
            return True
        except ValueError as e:
            # 账号无法访问该群组/频道（未加入）
            error_msg = str(e)
            if "Could not find the input entity" in error_msg:
                logger.info(f"⏭️  账号 '{initial_account['session_name']}' 未加入该群组/频道，跳过回复")
                return False
            else:
                # 其他 ValueError，直接抛出
                raise
        except Exception as e:
            # 其他错误，记录并返回失败
            logger.error(f"账号 '{initial_account['session_name']}' 发送失败: {e}")
            return False
    
    async def _list_monitor_groups(self):
        """列出并验证监听的聊天（群组/频道/私聊）"""
        if not self.monitor_groups:
            logger.warning("未配置监听列表，将监听所有消息（群组/频道/私聊）")
            return
        
        logger.info("配置的监听列表:")
        for group in self.monitor_groups:
            logger.info(f"  - {group}")
        
        # 尝试获取聊天信息
        logger.info("\n正在验证聊天...")
        valid_groups = []
        for group_identifier in self.monitor_groups:
            entity = None
            try:
                # 尝试直接使用标识符
                entity = await self.client.get_entity(group_identifier)
            except ValueError:
                # 如果直接获取失败，可能是私聊，尝试通过 ID 获取
                if group_identifier.lstrip('-').isdigit():
                    try:
                        # 尝试作为用户 ID 获取
                        entity = await self.client.get_entity(int(group_identifier))
                    except:
                        # 如果还是失败，尝试负数格式
                        if not group_identifier.startswith('-'):
                            try:
                                entity = await self.client.get_entity(int(f"-{group_identifier}"))
                            except:
                                pass
                
                # 如果还是失败，尝试通过对话框列表查找
                if entity is None:
                    try:
                        if group_identifier.lstrip('-').isdigit():
                            test_id = int(group_identifier)
                            
                            # 方法1: 尝试超级群组格式（-100 + ID）
                            if test_id > 0:
                                supergroup_id = f"-100{test_id}"
                                try:
                                    entity = await self.client.get_entity(int(supergroup_id))
                                except:
                                    pass
                            
                            # 方法2: 通过对话框列表查找（适用于私聊）
                            if entity is None:
                                try:
                                    dialogs = await self.client.get_dialogs()
                                    for dialog in dialogs:
                                        if abs(dialog.entity.id) == abs(test_id):
                                            entity = dialog.entity
                                            break
                                except Exception as dialog_error:
                                    logger.debug(f"通过对话框列表查找失败: {dialog_error}")
                    except:
                        pass
            
            # 如果成功获取到实体，处理并显示信息
            if entity is not None:
                try:
                    title = getattr(entity, 'title', None) or getattr(entity, 'username', None) or getattr(entity, 'first_name', None) or str(entity.id)
                    entity_id = entity.id
                    
                    # 判断聊天类型并显示信息
                    if hasattr(entity, 'megagroup') and entity.megagroup:
                        chat_type = "👥 群组"
                        # 超级群组 ID 应该是负数格式
                        if entity_id > 0:
                            corrected_id = f"-100{entity_id}"
                            logger.info(f"  ✓ {chat_type}: {title}")
                            logger.info(f"    当前 ID: {entity_id}")
                            logger.info(f"    建议使用: {corrected_id} 或 @{getattr(entity, 'username', 'N/A')}")
                        else:
                            logger.info(f"  ✓ {chat_type}: {title} (ID: {entity_id})")
                    elif hasattr(entity, 'broadcast') and entity.broadcast:
                        chat_type = "📢 频道"
                        logger.info(f"  ✓ {chat_type}: {title} (ID: {entity_id})")
                    else:
                        chat_type = "💬 私聊"
                        logger.info(f"  ✓ {chat_type}: {title} (ID: {entity_id})")
                        logger.info(f"    提示: 私聊 ID 可以是正数或负数格式")
                    
                    valid_groups.append(group_identifier)
                except Exception as e:
                    logger.warning(f"  ⚠️  处理实体信息时出错 '{group_identifier}': {e}")
            else:
                logger.warning(f"  ⚠️  验证时无法直接访问 '{group_identifier}'")
                logger.warning(f"    提示: 这可能是私聊，验证时无法直接获取，但监听时仍会正常工作")
                logger.warning(f"    程序会继续运行，实际消息事件中包含的聊天信息可以正常匹配")
        
        if valid_groups:
            logger.info(f"\n✅ 成功验证 {len(valid_groups)}/{len(self.monitor_groups)} 个群组")
        else:
            logger.warning(f"\n⚠️  未能验证任何群组，程序仍会运行但可能无法正确过滤消息")

async def main():
    """主函数"""
    # 可以通过命令行参数指定 session 名称
    import sys
    session_name = sys.argv[1] if len(sys.argv) > 1 else None
    
    listener = TelegramListener(session_name=session_name)
    try:
        await listener.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
    finally:
        try:
            # 停止签到调度器
            if listener.signin_scheduler:
                await listener.signin_scheduler.stop()
            
            if listener.client and listener.client.is_connected():
                await listener.client.disconnect()
            logger.info("已断开连接")
        except Exception as e:
            logger.error(f"关闭连接时出错: {e}")

if __name__ == '__main__':
    asyncio.run(main())

