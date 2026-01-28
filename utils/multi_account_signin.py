"""
多账号签到管理器
负责管理所有已登录账号的定时签到任务
"""
import asyncio
import logging
from telethon import TelegramClient
from config.config import (
    API_ID, API_HASH, SIGNIN_ENABLED, SIGNIN_TIME, SIGNIN_MESSAGE,
    list_available_sessions, get_session_file
)
from utils.signin_scheduler import SigninScheduler

logger = logging.getLogger(__name__)


class MultiAccountSigninManager:
    """多账号签到管理器"""
    
    def __init__(self):
        """初始化多账号签到管理器"""
        self.clients = {}  # {session_name: TelegramClient}
        self.schedulers = {}  # {session_name: SigninScheduler}
        self.is_running = False
    
    async def start(self):
        """启动所有账号的签到任务"""
        if not SIGNIN_ENABLED:
            logger.info("定时签到功能未启用")
            return
        
        # 获取所有可用的 session
        sessions = list_available_sessions()
        if not sessions:
            logger.warning("未找到任何 session 文件，无法启动签到任务")
            return
        
        logger.info(f"📋 找到 {len(sessions)} 个 session，准备启动签到任务...")
        
        self.is_running = True
        success_count = 0
        fail_count = 0
        
        for session_name in sessions:
            try:
                await self._start_account_signin(session_name)
                success_count += 1
            except Exception as e:
                logger.error(f"启动账号 '{session_name}' 的签到任务失败: {e}")
                fail_count += 1
        
        logger.info(f"✅ 签到任务启动完成: 成功 {success_count} 个，失败 {fail_count} 个")
        
        if success_count > 0:
            logger.info(f"⏰ 所有账号将在每天 {SIGNIN_TIME} 自动签到")
    
    async def _start_account_signin(self, session_name):
        """
        为单个账号启动签到任务
        
        Args:
            session_name: Session 名称
        """
        try:
            # 创建 Telegram 客户端
            session_file = get_session_file(session_name)
            client = TelegramClient(session_file, int(API_ID), API_HASH)
            
            # 连接客户端
            await client.connect()
            
            # 检查是否已授权
            if not await client.is_user_authorized():
                logger.warning(f"账号 '{session_name}' 未授权，跳过签到任务")
                await client.disconnect()
                return
            
            # 获取账号信息
            me = await client.get_me()
            account_name = f"{me.first_name} (@{me.username})" if me.username else me.first_name
            
            # 获取该账号的监控群组（这里使用配置的群组，也可以为每个账号单独配置）
            from config.config import MONITOR_GROUPS
            
            # 创建签到调度器
            scheduler = SigninScheduler(client, MONITOR_GROUPS)
            await scheduler.start()
            
            # 保存客户端和调度器
            self.clients[session_name] = client
            self.schedulers[session_name] = scheduler
            
            logger.info(f"✅ 账号 '{account_name}' ({session_name}) 的签到任务已启动")
            
        except Exception as e:
            logger.error(f"为账号 '{session_name}' 启动签到任务失败: {e}", exc_info=True)
            # 如果连接失败，尝试断开
            try:
                if 'client' in locals() and client.is_connected():
                    await client.disconnect()
            except:
                pass
            raise
    
    async def stop(self):
        """停止所有账号的签到任务"""
        logger.info("正在停止所有账号的签到任务...")
        
        # 停止所有调度器
        for session_name, scheduler in self.schedulers.items():
            try:
                await scheduler.stop()
                logger.info(f"✅ 账号 '{session_name}' 的签到任务已停止")
            except Exception as e:
                logger.error(f"停止账号 '{session_name}' 的签到任务失败: {e}")
        
        # 断开所有客户端连接
        for session_name, client in self.clients.items():
            try:
                if client.is_connected():
                    await client.disconnect()
                    logger.info(f"✅ 账号 '{session_name}' 的连接已断开")
            except Exception as e:
                logger.error(f"断开账号 '{session_name}' 的连接失败: {e}")
        
        self.clients.clear()
        self.schedulers.clear()
        self.is_running = False
        
        logger.info("✅ 所有账号的签到任务已停止")
    
    async def send_now_all(self):
        """立即为所有账号执行一次签到（用于测试）"""
        logger.info("手动触发所有账号的签到任务")
        for session_name, scheduler in self.schedulers.items():
            try:
                await scheduler.send_now()
            except Exception as e:
                logger.error(f"账号 '{session_name}' 签到失败: {e}")
    
    def get_account_count(self):
        """获取已启动的账号数量"""
        return len(self.schedulers)
    
    def get_account_list(self):
        """获取已启动的账号列表"""
        return list(self.schedulers.keys())

