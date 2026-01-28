"""
主启动类
类似 Spring Boot 的启动方式，统一管理所有功能的启动和停止
"""
import asyncio
import logging
import sys
from utils.telegram_listener import TelegramListener
from utils.multi_account_signin import MultiAccountSigninManager
from config.config import SIGNIN_ENABLED

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('log/telegram_bot.log', encoding='utf-8'),
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
                self.signin_manager = MultiAccountSigninManager()
                await self.signin_manager.start()
                account_count = self.signin_manager.get_account_count()
                if account_count > 0:
                    logger.info(f"✅ 已为 {account_count} 个账号启动定时签到任务")
                else:
                    logger.info("ℹ️  未找到已登录的账号，跳过签到任务")
            else:
                logger.info("ℹ️  定时签到功能未启用")
            
            logger.info("=" * 60)
            logger.info("✅ 所有功能已启动完成")
            logger.info("=" * 60)
            logger.info("📱 消息监听: 运行中")
            logger.info("🤖 LLM 自动回复: 运行中")
            if SIGNIN_ENABLED and self.signin_manager:
                account_count = self.signin_manager.get_account_count()
                if account_count > 0:
                    logger.info(f"⏰ 定时签到: 运行中 ({account_count} 个账号)")
                    logger.info(f"   账号列表: {', '.join(self.signin_manager.get_account_list())}")
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
    # 确保日志目录存在
    import os
    os.makedirs('log', exist_ok=True)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("应用已停止")
    except Exception as e:
        logger.error(f"应用启动失败: {e}", exc_info=True)
        sys.exit(1)

