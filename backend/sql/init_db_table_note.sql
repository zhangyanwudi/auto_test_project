-- 数据库表备注（db_table_note）建表 SQL
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

-- ----------------------------
-- Table: z_db_table_note（表备注 + 相关执行 SQL）
-- 关联维度：connection_id（连接配置）+ table_name（目标表）
-- 同一连接下同一表仅一条备注记录，执行 SQL 存在 sql_records 字段内（多条以行分隔）。
-- ----------------------------
CREATE TABLE IF NOT EXISTS `z_db_table_note` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '自增主键',
    `connection_id` VARCHAR(64)     NOT NULL                            COMMENT '连接配置标识（对应 db_table_note_config.json 中连接 id）',
    `table_name`    VARCHAR(192)    NOT NULL                            COMMENT '表名',
    `note`          TEXT            NULL                                COMMENT '表备注说明',
    `sql_records`   MEDIUMTEXT      NULL                                COMMENT '相关执行 SQL（多条用换行分隔）',
    `field_notes`   TEXT            NULL                                COMMENT '字段手动备注（JSON：{字段名:备注}）',
    `create_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_conn_table` (`connection_id`, `table_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='数据库表备注与相关执行SQL';
