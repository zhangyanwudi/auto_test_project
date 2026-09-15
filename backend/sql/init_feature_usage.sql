-- 功能使用记录表：记录用户进入某功能页停留满 1 分钟计一次「使用」
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

CREATE TABLE IF NOT EXISTS `z_feature_usage` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '自增主键',
    `menu_code`     VARCHAR(64)     NOT NULL                            COMMENT '功能编码（case_govern/ai_helper/mock_api/scheduled_task/db_table_note/config_compare）',
    `menu_name`     VARCHAR(128)    NOT NULL                            COMMENT '功能名称',
    `user_name`     VARCHAR(255)    NOT NULL                            COMMENT '使用人',
    `create_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '上报时间（进入满1分钟的时刻）',
    PRIMARY KEY (`id`),
    KEY `idx_menu_time` (`menu_code`, `create_time`),
    KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='功能使用记录（进入页面满1分钟计一次）';
