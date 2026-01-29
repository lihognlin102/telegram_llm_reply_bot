-- 账号回复计数表
-- 用于跟踪每个 Telegram 账号的 LLM 回复数量

CREATE TABLE IF NOT EXISTS `account_reply_count` (
  `session_name` VARCHAR(255) NOT NULL COMMENT '账号标识（Session 名称）',
  `reply_count` INT NOT NULL DEFAULT 0 COMMENT '当前回复计数',
  `max_replies` INT NOT NULL DEFAULT 120 COMMENT '最大回复数限制',
  `last_reset_date` DATE NULL COMMENT '上次重置日期（用于每日重置功能）',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`session_name`),
  INDEX `idx_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账号回复计数表';

