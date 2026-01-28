"""
列出 Telegram 账号的所有聊天（群组、频道、私聊）
适配当前项目的配置和 session 管理系统
"""
import asyncio
import sys
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径（支持从任何目录运行）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from config.config import (
    API_ID, API_HASH, PHONE_NUMBER,
    get_session_file, list_available_sessions, validate_config
)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def select_session():
    """选择要使用的 session"""
    available_sessions = list_available_sessions()
    
    if not available_sessions:
        print("❌ 未找到任何 session 文件，请先运行 telegram_listener.py 登录")
        return None
    
    print("\n📋 可用的 Session 列表:")
    for idx, session in enumerate(available_sessions, 1):
        print(f"  {idx}. {session}")
    
    # 支持命令行参数指定 session
    if len(sys.argv) > 1:
        session_name = sys.argv[1]
        if session_name in available_sessions:
            return session_name
        else:
            print(f"⚠️  警告: Session '{session_name}' 不存在，将使用交互式选择")
    
    # 交互式选择
    while True:
        try:
            choice = input(f"\n请选择 Session (1-{len(available_sessions)}): ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(available_sessions):
                    return available_sessions[idx]
            print("❌ 无效选择，请重新输入")
        except (ValueError, KeyboardInterrupt):
            print("\n👋 已取消")
            return None


async def main():
    """主函数"""
    try:
        # 验证配置（list_user.py 不需要 MONITOR_GROUPS）
        validate_config(require_monitor_groups=False)
        
        # 选择 session
        session_name = select_session()
        if not session_name:
            return
        
        session_file = get_session_file(session_name)
        logger.info(f"使用 Session: {session_name}")
        logger.info(f"Session 文件: {session_file}")
        
        # 创建客户端并连接（API_ID 需要转换为整数）
        client = TelegramClient(session_file, int(API_ID), API_HASH)
        await client.connect()
        
        # 检查是否已授权
        if not await client.is_user_authorized():
            logger.error("❌ Session 未授权，请先运行 telegram_listener.py 登录")
            await client.disconnect()
            return
        
        logger.info("✅ 连接成功，正在获取聊天列表...")

        # 获取所有对话
        dialogs = await client.get_dialogs()
        
        # 获取当前用户信息
        me = await client.get_me()
        print(f"\n👤 当前账号: {me.first_name} (@{me.username})")
        print(f"📱 账号 ID: {me.id}")
        print(f"📞 手机号: {PHONE_NUMBER}")
        
        print("\n📋 你加入的聊天列表（群组 / 频道 / 私聊）:")
        print("=" * 100)
        print(f"{'类型':<8} | {'名称':<40} | {'ID':<20} | {'用户名':<30}")
        print("-" * 100)
        
        # 统计信息
        group_count = 0
        channel_count = 0
        private_count = 0
        
        for dialog in dialogs:
            entity = dialog.entity
            name = dialog.name or "未知名称"
            username = getattr(entity, "username", None)
            entity_id = entity.id
            
            # 判断类型
            if getattr(entity, "megagroup", False):
                chat_type = "👥 群组"
                group_count += 1
            elif getattr(entity, "broadcast", False):
                chat_type = "📢 频道"
                channel_count += 1
            else:
                chat_type = "💬 私聊"
                private_count += 1
            
            # 格式化输出
            name_display = name[:38] + ".." if len(name) > 40 else name
            username_display = f"@{username}" if username else "-"
            
            print(f"{chat_type:<8} | {name_display:<40} | {entity_id:<20} | {username_display:<30}")
        
        print("=" * 100)
        print(f"\n📊 统计:")
        print(f"  👥 群组: {group_count} 个")
        print(f"  📢 频道: {channel_count} 个")
        print(f"  💬 私聊: {private_count} 个")
        print(f"  📝 总计: {len(dialogs)} 个")
        print("\n✅ 已列出所有聊天。")
        
        await client.disconnect()
        logger.info("已断开连接")
        
    except SessionPasswordNeededError:
        logger.error("❌ 需要两步验证密码，请先运行 telegram_listener.py 完成登录")
    except Exception as e:
        logger.exception(f"❌ 程序异常: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 手动停止")
    except Exception as e:
        logger.exception(f"💥 程序异常退出: {e}")