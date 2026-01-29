"""
添加新 Session 的独立脚本
用于在本地环境添加新的 Telegram 账号 session
"""
import asyncio
import sys
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.telegram_listener import TelegramListener
from config.config import validate_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def add_session():
    """添加新 session"""
    try:
        # 验证配置
        validate_config(require_monitor_groups=False)
        
        # 获取 session 名称
        if len(sys.argv) > 1:
            session_name = sys.argv[1]
        else:
            session_name = input("\n请输入新 Session 名称（建议使用手机号，如 +8612345678900）: ").strip()
            if not session_name:
                logger.error("Session 名称不能为空")
                return
        
        logger.info(f"正在创建 Session: {session_name}")
        
        # 创建监听器并启动（这会完成登录流程）
        listener = TelegramListener(session_name=session_name)
        await listener.start()
        
        # 获取账号信息
        me = await listener.client.get_me()
        logger.info(f"\n✅ Session 创建成功！")
        logger.info(f"   账号: {me.first_name} (@{me.username})")
        logger.info(f"   账号 ID: {me.id}")
        logger.info(f"   Session 文件: {listener.session_file}")
        
        # 断开连接
        await listener.client.disconnect()
        logger.info("\n✅ 已断开连接，Session 已保存")
        logger.info(f"   之后可以使用以下命令运行: python main.py {session_name}")
        
    except KeyboardInterrupt:
        logger.info("\n已取消")
    except Exception as e:
        logger.error(f"添加 Session 失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    try:
        asyncio.run(add_session())
    except KeyboardInterrupt:
        logger.info("已停止")
    except Exception as e:
        logger.error(f"程序异常: {e}", exc_info=True)
        sys.exit(1)

