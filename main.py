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
from utils.account_pool import AccountPool
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
        self.account_pool = None  # 账号池（用于轮询回复）
    
    async def start(self):
        """启动应用"""
        try:
            logger.info("=" * 60)
            logger.info("🚀 Telegram 机器人应用启动中...")
            logger.info("=" * 60)
            
            # 先初始化账号池（包含所有账号）
            self.account_pool = AccountPool()
            account_count = await self.account_pool.initialize()
            
            if account_count == 0:
                logger.error("❌ 未找到任何可用账号，无法启动")
                raise ValueError("未找到任何可用账号")
            
            logger.info(f"✅ 账号池已初始化，共 {account_count} 个账号")
            # 显示账号状态
            account_info = self.account_pool.get_account_info()
            for session_name, current_count, max_count, can_reply in account_info:
                status = "✅ 可用" if can_reply else "⛔ 已满"
                logger.info(f"   {status} - {session_name}: {current_count}/{max_count}")
            
            # 初始化监听器（从账号池中选择第一个账号作为监听器）
            # 如果通过命令行参数指定了 session_name，则使用指定的；否则使用账号池中的第一个
            if self.session_name:
                # 检查指定的 session 是否在账号池中
                listener_account = self.account_pool.get_account_by_session(self.session_name)
                if not listener_account:
                    logger.warning(f"⚠️  指定的账号 '{self.session_name}' 不在账号池中，将使用账号池中的第一个账号")
                    if len(self.account_pool.accounts) > 0:
                        listener_account = self.account_pool.accounts[0]
                    else:
                        raise ValueError("账号池为空，无法启动监听器")
                else:
                    logger.info(f"✅ 使用指定的账号作为监听器: {self.session_name}")
            else:
                # 使用账号池中的第一个账号作为监听器
                if len(self.account_pool.accounts) > 0:
                    listener_account = self.account_pool.accounts[0]
                    logger.info(f"✅ 使用账号池中的第一个账号作为监听器")
                else:
                    raise ValueError("账号池为空，无法启动监听器")
            
            listener_session_name, listener_client, listener_reply_counter = listener_account
            
            # 初始化监听器（复用账号池中的客户端）
            self.listener = TelegramListener(session_name=listener_session_name, account_pool=self.account_pool)
            self.listener.client = listener_client
            self.listener.reply_counter = listener_reply_counter
            
            logger.info(f"✅ 监听器使用账号: {listener_session_name}")
            
            # 启动监听器（注册消息处理器，但不连接，因为客户端已经在账号池中连接了）
            await self.listener.start_with_existing_client()
            
            # 启动多账号签到任务（如果启用）
            if SIGNIN_ENABLED:
                from config.config import MONITOR_GROUPS
                
                if MONITOR_GROUPS:
                    # 从账号池中为所有账号启动签到任务（复用账号池中的客户端）
                    if self.account_pool and len(self.account_pool.accounts) > 0:
                        await self.account_pool.start_signin_for_all(MONITOR_GROUPS)
                        account_count = len(self.account_pool.accounts)
                        logger.info(f"✅ 已为账号池中所有 {account_count} 个账号启动定时签到任务")
                    else:
                        logger.warning("⚠️  账号池为空，无法启动签到任务")
                else:
                    logger.warning("⚠️  未配置监控群组，无法启动签到任务")
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
                if self.account_pool and len(self.account_pool.accounts) > 0:
                    account_list = [acc[0] for acc in self.account_pool.accounts]
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
            
            # 断开账号池中所有账号的连接（会自动停止签到任务）
            if self.account_pool:
                await self.account_pool.disconnect_all()
            
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
        try:
            # 停止应用（会自动断开所有连接和停止所有任务）
            await app.stop()
        except Exception as e:
            logger.error(f"关闭应用时出错: {e}", exc_info=True)


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

