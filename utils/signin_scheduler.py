"""
定时签到调度器模块
负责每天定时向监控的群组发送签到消息
"""
import asyncio
import logging
from datetime import datetime, time, timedelta
from telethon import TelegramClient
from config.config import SIGNIN_ENABLED, SIGNIN_TIME, SIGNIN_MESSAGE, MONITOR_GROUPS

logger = logging.getLogger(__name__)


class SigninScheduler:
    """定时签到调度器"""
    
    def __init__(self, client: TelegramClient, monitor_groups=None):
        """
        初始化签到调度器
        
        Args:
            client: Telegram 客户端实例
            monitor_groups: 监控的群组列表，如果为 None 则使用配置中的 MONITOR_GROUPS
        """
        self.client = client
        self.monitor_groups = monitor_groups or MONITOR_GROUPS
        self.task = None
        self.is_running = False
        self.start_time = None  # 记录启动时间
        self.first_signin_done = False  # 标记是否已完成第一次签到
        self.daily_signin_time = None  # 记录每天签到的时间
    
    async def start(self):
        """启动签到调度器"""
        if not SIGNIN_ENABLED:
            logger.info("定时签到功能未启用")
            return
        
        if not self.monitor_groups:
            logger.warning("未配置监控群组，无法启动签到任务")
            return
        
        if self.is_running:
            logger.warning("签到调度器已在运行")
            return
        
        self.is_running = True
        self.start_time = datetime.now()  # 记录启动时间
        self.first_signin_done = False
        self.daily_signin_time = None
        self.task = asyncio.create_task(self._scheduler_loop())
        # 计算第一次签到时间（启动时间 + 60秒）
        first_signin_time = self.start_time + timedelta(seconds=60)
        logger.info(f"定时签到任务已启动，首次签到时间: {first_signin_time.strftime('%Y-%m-%d %H:%M:%S')}，之后每天此时执行")
    
    async def stop(self):
        """停止签到调度器"""
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            logger.info("定时签到任务已停止")
        self.is_running = False
    
    async def _scheduler_loop(self):
        """调度器主循环"""
        try:
            while self.is_running:
                now = datetime.now()
                
                if not self.first_signin_done:
                    # 第一次签到：启动后60秒
                    target_time = self.start_time + timedelta(seconds=60)
                    wait_seconds = (target_time - now).total_seconds()
                    
                    if wait_seconds > 0:
                        logger.info(f"⏰ 首次签到时间: {target_time.strftime('%Y-%m-%d %H:%M:%S')}，等待 {wait_seconds:.1f} 秒")
                        await asyncio.sleep(wait_seconds)
                    else:
                        # 如果已经过了60秒，立即执行
                        logger.info("⏰ 启动已超过60秒，立即执行首次签到")
                    
                    # 执行第一次签到
                    await self._send_signin_messages()
                    self.first_signin_done = True
                    
                    # 记录第一次签到的时间（用于后续每天执行）
                    self.daily_signin_time = target_time.time()
                    logger.info(f"✅ 首次签到完成，之后每天 {self.daily_signin_time.strftime('%H:%M:%S')} 执行签到")
                else:
                    # 后续签到：每天按照第一次签到的时间执行
                    signin_time_obj = self.daily_signin_time
                    target_time = datetime.combine(now.date(), signin_time_obj)
                    
                    # 如果今天的时间已过，设置为明天
                    if target_time <= now:
                        target_time += timedelta(days=1)
                    
                    # 计算等待时间（秒）
                    wait_seconds = (target_time - now).total_seconds()
                    
                    logger.info(f"⏰ 下次签到时间: {target_time.strftime('%Y-%m-%d %H:%M:%S')}，等待 {wait_seconds/3600:.1f} 小时")
                    
                    # 等待到签到时间
                    await asyncio.sleep(wait_seconds)
                    
                    # 执行签到
                    await self._send_signin_messages()
                
        except asyncio.CancelledError:
            logger.info("定时签到任务已取消")
        except Exception as e:
            logger.error(f"定时签到任务出错: {e}", exc_info=True)
            self.is_running = False
    
    async def _send_signin_messages(self):
        """向所有监控的群组发送签到消息"""
        if not self.monitor_groups:
            logger.warning("未配置监控群组，跳过签到")
            return
        
        logger.info(f"📝 开始执行签到任务，共 {len(self.monitor_groups)} 个群组")
        
        success_count = 0
        fail_count = 0
        
        for group_identifier in self.monitor_groups:
            try:
                # 获取群组实体
                entity = await self._get_group_entity(group_identifier)
                
                if not entity:
                    logger.warning(f"无法找到群组 '{group_identifier}'，跳过签到")
                    fail_count += 1
                    continue
                
                # 发送签到消息
                await self.client.send_message(entity, SIGNIN_MESSAGE)
                
                title = getattr(entity, 'title', None) or getattr(entity, 'username', None) or str(entity.id)
                logger.info(f"✅ 已向 '{title}' 发送签到消息")
                success_count += 1
                
                # 避免发送过快，添加小延迟
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"向 '{group_identifier}' 发送签到消息失败: {e}")
                fail_count += 1
        
        logger.info(f"📊 签到完成: 成功 {success_count} 个，失败 {fail_count} 个")
    
    async def _get_group_entity(self, group_identifier):
        """
        获取群组实体
        
        Args:
            group_identifier: 群组标识符（ID、用户名等）
        
        Returns:
            群组实体对象，如果找不到返回 None
        """
        try:
            # 尝试直接获取
            return await self.client.get_entity(group_identifier)
        except ValueError:
            # 如果直接获取失败，尝试通过对话框列表查找
            try:
                dialogs = await self.client.get_dialogs()
                identifier_str = str(group_identifier).strip()
                
                if identifier_str.lstrip('-').isdigit():
                    test_id = int(identifier_str)
                    for dialog in dialogs:
                        if abs(dialog.entity.id) == abs(test_id):
                            return dialog.entity
            except Exception as e:
                logger.debug(f"通过对话框列表查找失败: {e}")
        
        return None
    
    async def send_now(self):
        """立即执行一次签到（用于测试）"""
        logger.info("手动触发签到任务")
        await self._send_signin_messages()

