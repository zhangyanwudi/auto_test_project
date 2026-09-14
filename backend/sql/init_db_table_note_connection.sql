-- 数据库连接配置（db_table_note）建表 SQL
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

CREATE TABLE IF NOT EXISTS `z_db_table_note_connection` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '自增主键',
    `connection_id` VARCHAR(64)     NOT NULL                            COMMENT '连接配置标识（唯一）',
    `name`          VARCHAR(128)    NOT NULL DEFAULT ''                 COMMENT '显示名称',
    `host`          VARCHAR(255)    NOT NULL                            COMMENT '数据库地址',
    `port`          INT             NOT NULL DEFAULT 3306               COMMENT '端口',
    `user`          VARCHAR(128)    NOT NULL                            COMMENT '用户名',
    `password`      VARCHAR(255)    NOT NULL                            COMMENT '密码',
    `database`      VARCHAR(128)    NOT NULL                            COMMENT '数据库名',
    `create_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_connection_id` (`connection_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='数据库表备注-连接配置';
