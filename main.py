"""
主启动类
类似 Spring Boot 的启动方式，统一管理所有功能的启动和停止
"""
import asyncio
import logging
import sys
import os
from pathlib import Path
from utils.telegram_listener import TelegramListener
from utils.multi_account_signin import MultiAccountSigninManager
from config.config import SIGNIN_ENABLED

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.absolute()
LOG_DIR = PROJECT_ROOT / 'log'
LOG_DIR.mkdir(exist_ok=True, mode=0o755)

# 配置日志 - 使用绝对路径
LOG_FILE = LOG_DIR / 'telegram_bot.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TelegramBotApplication:
    """Telegram 机器人应用主类"""
    
    def __init__(self, session_name=None):
        """
        初始化应用
        
        Args:
            session_name: Session 名称，如果为 None 则会在启动时让用户选择或输入
        """
        self.session_name = session_name
        self.listener = None
        self.signin_manager = None
    
    async def start(self):
        """启动应用"""
        try:
            logger.info("=" * 60)
            logger.info("🚀 Telegram 机器人应用启动中...")
            logger.info("=" * 60)
            
            # 初始化监听器
            self.listener = TelegramListener(session_name=self.session_name)
            
            # 启动监听器（这会连接 Telegram 并启动消息监听）
            await self.listener.start()
            
            # 启动多账号签到任务（如果启用）
            if SIGNIN_ENABLED:
                # 为监听器使用的账号也启动签到任务（使用监听器已有的客户端，避免数据库锁定）
                from utils.signin_scheduler import SigninScheduler
                from config.config import MONITOR_GROUPS
                
                if MONITOR_GROUPS:
                    self.listener.signin_scheduler = SigninScheduler(self.listener.client, MONITOR_GROUPS)
                    await self.listener.signin_scheduler.start()
                    logger.info(f"✅ 监听器账号 '{self.listener.session_name}' 的签到任务已启动")
                
                # 为其他账号启动签到任务（排除监听器使用的 session，避免数据库锁定）
                self.signin_manager = MultiAccountSigninManager()
                await self.signin_manager.start(exclude_session=self.listener.session_name)
                account_count = self.signin_manager.get_account_count()
                if account_count > 0:
                    logger.info(f"✅ 已为 {account_count} 个其他账号启动定时签到任务")
                
                # 统计总账号数
                total_count = (1 if self.listener.signin_scheduler else 0) + account_count
                if total_count > 0:
                    logger.info(f"✅ 总计已为 {total_count} 个账号启动定时签到任务")
                else:
                    logger.info("ℹ️  未找到已登录的账号，跳过签到任务")
            else:
                logger.info("ℹ️  定时签到功能未启用")
            
            logger.info("=" * 60)
            logger.info("✅ 所有功能已启动完成")
            logger.info("=" * 60)
            logger.info("📱 消息监听: 运行中")
            from config.config import LLM_ENABLED
            if LLM_ENABLED:
                logger.info("🤖 LLM 自动回复: 运行中")
            else:
                logger.info("🤖 LLM 自动回复: 已禁用")
            if SIGNIN_ENABLED:
                account_list = []
                if self.listener.signin_scheduler:
                    account_list.append(self.listener.session_name)
                if self.signin_manager:
                    account_list.extend(self.signin_manager.get_account_list())
                if account_list:
                    total_count = len(account_list)
                    logger.info(f"⏰ 定时签到: 运行中 ({total_count} 个账号)")
                    logger.info(f"   账号列表: {', '.join(account_list)}")
            logger.info("=" * 60)
            logger.info("按 Ctrl+C 停止应用")
            logger.info("=" * 60)
            
            # 保持运行直到断开连接
            await self.listener.client.run_until_disconnected()
            
        except KeyboardInterrupt:
            logger.info("\n收到中断信号，正在关闭应用...")
        except Exception as e:
            logger.error(f"应用启动失败: {e}", exc_info=True)
            raise
    
    async def stop(self):
        """停止应用"""
        try:
            logger.info("正在关闭应用...")
            
            # 停止监听器的签到任务
            if self.listener and self.listener.signin_scheduler:
                await self.listener.signin_scheduler.stop()
            
            # 停止多账号签到管理器
            if self.signin_manager:
                await self.signin_manager.stop()
            
            # 断开 Telegram 连接
            if self.listener and self.listener.client and self.listener.client.is_connected():
                await self.listener.client.disconnect()
                logger.info("✅ Telegram 连接已断开")
            
            logger.info("✅ 应用已完全关闭")
            
        except Exception as e:
            logger.error(f"关闭应用时出错: {e}", exc_info=True)


async def main():
    """主函数"""
    # 可以通过命令行参数指定 session 名称
    session_name = sys.argv[1] if len(sys.argv) > 1 else None
    
    app = TelegramBotApplication(session_name=session_name)
    
    try:
        await app.start()
    except Exception as e:
        logger.error(f"应用异常退出: {e}")
    finally:
        await app.stop()


if __name__ == '__main__':
    # 切换到项目根目录（确保相对路径正确）
    os.chdir(PROJECT_ROOT)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("应用已停止")
    except Exception as e:
        logger.error(f"应用启动失败: {e}", exc_info=True)
        sys.exit(1)

