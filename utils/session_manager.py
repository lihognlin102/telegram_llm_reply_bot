"""
Session 管理工具
用于列出、删除和管理 Telegram session 文件
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（支持从任何目录运行）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config.config import SESSION_DIR, list_available_sessions

def list_sessions():
    """列出所有 session 文件"""
    sessions = list_available_sessions()
    if not sessions:
        print("未找到任何 session 文件")
        return
    
    print(f"\n找到 {len(sessions)} 个 session 文件:")
    print("-" * 50)
    for idx, session in enumerate(sessions, 1):
        session_file = SESSION_DIR / f"{session}.session"
        size = session_file.stat().st_size if session_file.exists() else 0
        size_kb = size / 1024
        print(f"  {idx}. {session} ({size_kb:.2f} KB)")
    print("-" * 50)

def delete_session(session_name):
    """删除指定的 session 文件"""
    session_file = SESSION_DIR / f"{session_name}.session"
    if session_file.exists():
        session_file.unlink()
        print(f"✓ 已删除 session: {session_name}")
        return True
    else:
        print(f"✗ 未找到 session: {session_name}")
        return False

def cleanup_old_sessions():
    """清理不在 sessions 目录下的旧 session 文件"""
    project_root = SESSION_DIR.parent
    old_sessions = []
    
    # 查找项目根目录下的所有 .session 文件
    for session_file in project_root.rglob('*.session'):
        # 排除 sessions 目录下的文件
        if 'sessions' not in str(session_file):
            old_sessions.append(session_file)
    
    if old_sessions:
        print(f"\n找到 {len(old_sessions)} 个旧 session 文件（不在 sessions/ 目录下）:")
        for session_file in old_sessions:
            print(f"  - {session_file}")
        
        confirm = input("\n是否删除这些旧文件？(y/N): ").strip().lower()
        if confirm == 'y':
            for session_file in old_sessions:
                try:
                    session_file.unlink()
                    print(f"✓ 已删除: {session_file}")
                except Exception as e:
                    print(f"✗ 删除失败 {session_file}: {e}")
        else:
            print("已取消")
    else:
        print("未找到需要清理的旧 session 文件")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'list':
            list_sessions()
        elif command == 'delete' and len(sys.argv) > 2:
            delete_session(sys.argv[2])
        elif command == 'cleanup':
            cleanup_old_sessions()
        else:
            print("用法:")
            print("  python session_manager.py list          # 列出所有 session")
            print("  python session_manager.py delete <name> # 删除指定 session")
            print("  python session_manager.py cleanup       # 清理旧 session 文件")
    else:
        print("Session 管理工具")
        print("\n用法:")
        print("  python session_manager.py list          # 列出所有 session")
        print("  python session_manager.py delete <name> # 删除指定 session")
        print("  python session_manager.py cleanup       # 清理旧 session 文件")
        print("\n当前 session 列表:")
        list_sessions()



