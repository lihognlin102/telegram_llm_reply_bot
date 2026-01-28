"""
配置文件
用于管理 Telegram API 配置和群组设置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量+447464736880.session
load_dotenv()

# Telegram API 配置
API_ID = os.getenv('API_ID', '')
API_HASH = os.getenv('API_HASH', '')
PHONE_NUMBER = os.getenv('PHONE_NUMBER', '')

# 监听配置
MONITOR_GROUPS = os.getenv('MONITOR_GROUPS', '').split(',') if os.getenv('MONITOR_GROUPS') else []
# 过滤掉空字符串
MONITOR_GROUPS = [g.strip() for g in MONITOR_GROUPS if g.strip()]

# Session 文件路径 - 使用绝对路径，保存在项目根目录的 sessions 文件夹中
SESSION_DIR = Path(__file__).parent.parent / 'sessions'
SESSION_DIR.mkdir(exist_ok=True)  # 确保目录存在

# 默认 session 名称（如果未指定）
DEFAULT_SESSION_NAME = os.getenv('SESSION_FILE', 'telegram_session')

# LLM 配置（阿里云百炼）
LLM_API_KEY = os.getenv('LLM_API_KEY', '')
LLM_BASE_URL = os.getenv('LLM_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
LLM_MODEL = os.getenv('LLM_MODEL', 'qwen-plus')  # 默认使用 qwen-plus

# 定时签到配置
SIGNIN_ENABLED = os.getenv('SIGNIN_ENABLED', 'true').lower() in ('true', '1', 'yes')
SIGNIN_TIME = os.getenv('SIGNIN_TIME', '12:00')  # 签到时间，格式：HH:MM
SIGNIN_MESSAGE = os.getenv('SIGNIN_MESSAGE', '签到')  # 签到消息内容

def get_session_file(session_name=None):
    """获取 session 文件路径"""
    if session_name is None:
        session_name = DEFAULT_SESSION_NAME
    return str(SESSION_DIR / session_name)

def list_available_sessions():
    """列出所有可用的 session 文件"""
    sessions = []
    if SESSION_DIR.exists():
        for file in SESSION_DIR.glob('*.session'):
            sessions.append(file.stem)  # 不包含 .session 扩展名
    return sorted(sessions)

def validate_config(require_monitor_groups=True):
    """
    验证配置是否完整
    
    Args:
        require_monitor_groups: 是否要求 MONITOR_GROUPS 必须设置（默认 True）
    """
    errors = []
    if not API_ID:
        errors.append("API_ID 未设置")
    if not API_HASH:
        errors.append("API_HASH 未设置")
    if not PHONE_NUMBER:
        errors.append("PHONE_NUMBER 未设置")
    if require_monitor_groups and not MONITOR_GROUPS:
        errors.append("MONITOR_GROUPS 未设置")
    
    if errors:
        raise ValueError(f"配置错误: {', '.join(errors)}")
    
    return True

