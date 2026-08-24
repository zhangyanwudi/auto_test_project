-- AI助手 模块建表 SQL
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

-- ----------------------------
-- Table: ai_conversation（对话会话）
-- ----------------------------
CREATE TABLE IF NOT EXISTS `ai_conversation` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT          COMMENT '自增主键',
    `conversation_code` VARCHAR(64) NOT NULL                        COMMENT '对外暴露的唯一对话编码（UUID hex）',
    `user_id`       BIGINT          NOT NULL                        COMMENT '所属用户ID，关联 z_user.id',
    `title`         VARCHAR(128)    NOT NULL DEFAULT ''             COMMENT '对话标题',
    `is_deleted`    TINYINT(1)      NOT NULL DEFAULT 0              COMMENT '软删除标记：0-正常 1-已删除',
    `create_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_conversation_code` (`conversation_code`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_user_deleted_time` (`user_id`, `is_deleted`, `update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='AI对话会话';

-- ----------------------------
-- Table: ai_message（对话消息）
-- ----------------------------
CREATE TABLE IF NOT EXISTS `ai_message` (
    `id`              BIGINT        NOT NULL AUTO_INCREMENT          COMMENT '自增主键',
    `conversation_id` BIGINT        NOT NULL                        COMMENT '所属对话ID，关联 ai_conversation.id',
    `role`            VARCHAR(16)   NOT NULL                        COMMENT '消息角色：user-用户 assistant-助手',
    `content`         LONGTEXT      NOT NULL                        COMMENT '消息内容',
    `create_time`     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_conversation_id` (`conversation_id`),
    KEY `idx_conversation_role_time` (`conversation_id`, `role`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='AI对话消息';
