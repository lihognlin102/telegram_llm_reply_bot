"""
账号池管理器
用于管理多个 Telegram 账号，实现轮询回复功能
"""
import logging
from telethon import TelegramClient
from config.config import (
    API_ID, API_HASH, list_available_sessions, get_session_file
)
from utils.reply_counter import ReplyCounter
from utils.signin_scheduler import SigninScheduler

logger = logging.getLogger(__name__)


class AccountPool:
    """账号池管理器"""
    
    def __init__(self):
        """初始化账号池"""
        self.accounts = []  # [(session_name, client, reply_counter), ...]
        self.current_index = 0  # 当前使用的账号索引
        self.clients = {}  # {session_name: TelegramClient} 用于快速查找
        self.signin_schedulers = {}  # {session_name: SigninScheduler} 用于管理签到任务
        self.account_ids = set()  # {account_id, ...} 用于快速检查是否是自己的账号
    
    async def initialize(self, exclude_session=None):
        """
        初始化账号池（包含所有可用账号）
        
        Args:
            exclude_session: 已废弃，不再使用（保留参数以兼容旧代码）
        
        Returns:
            int: 成功初始化的账号数量
        """
        # 获取所有可用的 session
        sessions = list_available_sessions()
        if not sessions:
            logger.warning("未找到任何 session 文件")
            return 0
        
        initialized_count = 0
        
        for session_name in sessions:
            try:
                # 创建客户端
                session_file = get_session_file(session_name)
                client = TelegramClient(session_file, int(API_ID), API_HASH)
                
                # 连接客户端
                await client.connect()
                
                # 检查是否已授权
                if not await client.is_user_authorized():
                    logger.warning(f"账号 '{session_name}' 未授权，跳过")
                    await client.disconnect()
                    continue
                
                # 获取账号信息
                me = await client.get_me()
                logger.info(f"✅ 账号池添加账号: {me.first_name} (@{me.username}) - {session_name}")
                
                # 记录账号 ID（用于过滤自己发送的消息）
                self.account_ids.add(me.id)
                
                # 初始化回复计数器
                try:
                    reply_counter = ReplyCounter(session_name)
                    current_count, max_count = reply_counter.get_count()
                    logger.info(f"   📊 回复计数: {current_count}/{max_count}")
                except Exception as e:
                    logger.warning(f"账号 '{session_name}' 初始化回复计数器失败: {e}")
                    reply_counter = None
                
                # 添加到账号池
                self.accounts.append((session_name, client, reply_counter))
                self.clients[session_name] = client
                initialized_count += 1
                
            except Exception as e:
                logger.error(f"初始化账号 '{session_name}' 失败: {e}", exc_info=True)
                try:
                    if 'client' in locals():
                        await client.disconnect()
                except:
                    pass
        
        logger.info(f"📋 账号池初始化完成: 共 {initialized_count} 个可用账号")
        return initialized_count
    
    def get_account_by_session(self, session_name):
        """
        根据 session_name 获取账号
        
        Args:
            session_name: Session 名称
        
        Returns:
            tuple: (session_name, client, reply_counter) 或 None（如果不存在）
        """
        for acc in self.accounts:
            if acc[0] == session_name:
                return acc
        return None
    
    def get_next_account(self):
        """
        获取下一个可用的账号（轮询方式，从第一个开始）
        
        Returns:
            tuple: (session_name, client, reply_counter) 或 None（如果没有可用账号）
        """
        if not self.accounts:
            return None
        
        # 尝试从当前索引开始查找可用账号
        start_index = self.current_index
        attempts = 0
        
        while attempts < len(self.accounts):
            session_name, client, reply_counter = self.accounts[self.current_index]
            
            # 检查账号是否可用（未达到限制）
            if reply_counter:
                can_reply, current_count, max_count = reply_counter.can_reply()
                if can_reply:
                    # 找到可用账号，更新索引为下一个
                    self.current_index = (self.current_index + 1) % len(self.accounts)
                    return session_name, client, reply_counter
                else:
                    logger.debug(f"账号 '{session_name}' 已达到回复上限 ({current_count}/{max_count})，跳过")
            else:
                # 没有回复计数器，认为可用
                self.current_index = (self.current_index + 1) % len(self.accounts)
                return session_name, client, reply_counter
            
            # 移动到下一个账号
            self.current_index = (self.current_index + 1) % len(self.accounts)
            attempts += 1
        
        # 所有账号都不可用
        logger.warning("⚠️  所有账号都已达到回复上限，无法回复")
        return None
    
    def get_account_info(self):
        """
        获取所有账号的状态信息
        
        Returns:
            list: [(session_name, current_count, max_count, can_reply), ...]
        """
        info = []
        for session_name, client, reply_counter in self.accounts:
            if reply_counter:
                can_reply, current_count, max_count = reply_counter.can_reply()
                info.append((session_name, current_count, max_count, can_reply))
            else:
                info.append((session_name, 0, 0, True))
        return info
    
    async def start_signin_for_all(self, monitor_groups):
        """
        为账号池中的所有账号启动签到任务
        
        Args:
            monitor_groups: 监控的群组列表
        """
        if not monitor_groups:
            logger.warning("未配置监控群组，无法启动签到任务")
            return
        
        started_count = 0
        for session_name, client, reply_counter in self.accounts:
            try:
                scheduler = SigninScheduler(client, monitor_groups)
                await scheduler.start()
                self.signin_schedulers[session_name] = scheduler
                logger.info(f"✅ 账号池账号 '{session_name}' 的签到任务已启动")
                started_count += 1
            except Exception as e:
                logger.error(f"为账号池账号 '{session_name}' 启动签到任务失败: {e}")
        
        if started_count > 0:
            logger.info(f"✅ 账号池中共 {started_count} 个账号的签到任务已启动")
    
    async def stop_signin_for_all(self):
        """停止账号池中所有账号的签到任务"""
        for session_name, scheduler in self.signin_schedulers.items():
            try:
                await scheduler.stop()
                logger.info(f"已停止账号池账号 '{session_name}' 的签到任务")
            except Exception as e:
                logger.error(f"停止账号池账号 '{session_name}' 签到任务失败: {e}")
        
        self.signin_schedulers.clear()
    
    async def disconnect_all(self):
        """断开所有账号的连接"""
        # 先停止所有签到任务
        await self.stop_signin_for_all()
        
        for session_name, client, reply_counter in self.accounts:
            try:
                if client and client.is_connected():
                    await client.disconnect()
                    logger.info(f"已断开账号 '{session_name}' 的连接")
            except Exception as e:
                logger.error(f"断开账号 '{session_name}' 连接失败: {e}")
        
        self.accounts.clear()
        self.clients.clear()
        self.account_ids.clear()
        self.current_index = 0

