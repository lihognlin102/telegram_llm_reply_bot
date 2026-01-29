"""
回复计数器模块
用于跟踪每个 Telegram 账号的 LLM 回复数量，限制每个账号最多回复指定条数
"""
import logging
import pymysql
from datetime import datetime
from config.config import (
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_CHARSET,
    MAX_REPLIES_PER_ACCOUNT
)

logger = logging.getLogger(__name__)


class ReplyCounter:
    """回复计数器"""
    
    def __init__(self, session_name):
        """
        初始化回复计数器
        
        Args:
            session_name: Session 名称（账号标识）
        """
        self.session_name = session_name
        self.max_replies = MAX_REPLIES_PER_ACCOUNT
        self._ensure_table_exists()
        self._initialize_account()
    
    def _get_connection(self, retries=3):
        """
        获取数据库连接（带重试机制）
        
        Args:
            retries: 重试次数，默认3次
        """
        last_error = None
        for attempt in range(retries):
            try:
                return pymysql.connect(
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=DB_NAME,
                    charset=DB_CHARSET,
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False,
                    connect_timeout=10,
                    read_timeout=10,
                    write_timeout=10
                )
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    logger.warning(f"数据库连接失败（尝试 {attempt + 1}/{retries}）: {e}，1秒后重试...")
                    import time
                    time.sleep(1)
                else:
                    logger.error(f"数据库连接失败（已重试 {retries} 次）: {e}")
        raise last_error
    
    def _ensure_table_exists(self):
        """确保数据库表存在"""
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cursor:
                    # 检查表是否存在
                    cursor.execute("""
                        SELECT COUNT(*) as count 
                        FROM information_schema.tables 
                        WHERE table_schema = %s AND table_name = 'account_reply_count'
                    """, (DB_NAME,))
                    result = cursor.fetchone()
                    
                    if result['count'] == 0:
                        # 创建表
                        cursor.execute("""
                            CREATE TABLE IF NOT EXISTS `account_reply_count` (
                              `session_name` VARCHAR(255) NOT NULL COMMENT '账号标识（Session 名称）',
                              `reply_count` INT NOT NULL DEFAULT 0 COMMENT '当前回复计数',
                              `max_replies` INT NOT NULL DEFAULT %s COMMENT '最大回复数限制',
                              `last_reset_date` DATE NULL COMMENT '上次重置日期（用于每日重置功能）',
                              `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                              `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                              PRIMARY KEY (`session_name`),
                              INDEX `idx_updated_at` (`updated_at`)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账号回复计数表'
                        """, (self.max_replies,))
                        conn.commit()
                        logger.info("数据库表 account_reply_count 创建成功")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"创建数据库表失败: {e}", exc_info=True)
            raise
    
    def _initialize_account(self):
        """初始化账号记录（如果不存在）"""
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cursor:
                    # 检查账号是否存在
                    cursor.execute("""
                        SELECT reply_count, max_replies 
                        FROM account_reply_count 
                        WHERE session_name = %s
                    """, (self.session_name,))
                    result = cursor.fetchone()
                    
                    if result is None:
                        # 创建新记录
                        cursor.execute("""
                            INSERT INTO account_reply_count 
                            (session_name, reply_count, max_replies) 
                            VALUES (%s, 0, %s)
                        """, (self.session_name, self.max_replies))
                        conn.commit()
                        logger.info(f"账号 '{self.session_name}' 的回复计数记录已初始化")
                    else:
                        # 如果 max_replies 配置改变了，更新它
                        if result['max_replies'] != self.max_replies:
                            cursor.execute("""
                                UPDATE account_reply_count 
                                SET max_replies = %s 
                                WHERE session_name = %s
                            """, (self.max_replies, self.session_name))
                            conn.commit()
                            logger.info(f"账号 '{self.session_name}' 的最大回复数已更新为 {self.max_replies}")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"初始化账号记录失败: {e}", exc_info=True)
            raise
    
    def can_reply(self):
        """
        检查是否可以回复
        
        Returns:
            tuple: (是否可以回复, 当前计数, 最大计数)
        """
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT reply_count, max_replies 
                        FROM account_reply_count 
                        WHERE session_name = %s
                    """, (self.session_name,))
                    result = cursor.fetchone()
                    
                    if result is None:
                        # 如果记录不存在，初始化它
                        self._initialize_account()
                        return True, 0, self.max_replies
                    
                    current_count = result['reply_count']
                    max_replies = result['max_replies']
                    can_reply = current_count < max_replies
                    
                    return can_reply, current_count, max_replies
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"检查回复计数失败: {e}", exc_info=True)
            # 出错时允许回复，避免因数据库问题导致功能完全失效
            return True, 0, self.max_replies
    
    def increment(self):
        """
        增加回复计数
        
        Returns:
            tuple: (是否成功, 当前计数, 最大计数)
        """
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cursor:
                    # 使用原子操作增加计数
                    cursor.execute("""
                        UPDATE account_reply_count 
                        SET reply_count = reply_count + 1,
                            updated_at = NOW()
                        WHERE session_name = %s
                    """, (self.session_name,))
                    
                    if cursor.rowcount == 0:
                        # 如果记录不存在，创建它
                        self._initialize_account()
                        cursor.execute("""
                            UPDATE account_reply_count 
                            SET reply_count = reply_count + 1,
                                updated_at = NOW()
                            WHERE session_name = %s
                        """, (self.session_name,))
                    
                    # 获取更新后的计数
                    cursor.execute("""
                        SELECT reply_count, max_replies 
                        FROM account_reply_count 
                        WHERE session_name = %s
                    """, (self.session_name,))
                    result = cursor.fetchone()
                    
                    conn.commit()
                    
                    current_count = result['reply_count']
                    max_replies = result['max_replies']
                    
                    logger.info(f"账号 '{self.session_name}' 回复计数已更新: {current_count}/{max_replies}")
                    return True, current_count, max_replies
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"增加回复计数失败: {e}", exc_info=True)
            # 如果 conn 已定义，尝试回滚
            if 'conn' in locals():
                try:
                    conn.rollback()
                except:
                    pass
            return False, 0, self.max_replies
    
    def get_count(self):
        """
        获取当前回复计数
        
        Returns:
            tuple: (当前计数, 最大计数)
        """
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT reply_count, max_replies 
                        FROM account_reply_count 
                        WHERE session_name = %s
                    """, (self.session_name,))
                    result = cursor.fetchone()
                    
                    if result is None:
                        return 0, self.max_replies
                    
                    return result['reply_count'], result['max_replies']
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"获取回复计数失败: {e}", exc_info=True)
            return 0, self.max_replies
    
    def reset_count(self):
        """
        重置回复计数（用于测试或手动重置）
        
        Returns:
            bool: 是否成功
        """
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE account_reply_count 
                        SET reply_count = 0,
                            updated_at = NOW()
                        WHERE session_name = %s
                    """, (self.session_name,))
                    conn.commit()
                    logger.info(f"账号 '{self.session_name}' 的回复计数已重置")
                    return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"重置回复计数失败: {e}", exc_info=True)
            # 如果 conn 已定义，尝试回滚
            if 'conn' in locals():
                try:
                    conn.rollback()
                except:
                    pass
            return False

