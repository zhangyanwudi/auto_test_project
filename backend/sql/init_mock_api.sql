-- Mock API 模块建表 SQL
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

-- ----------------------------
-- Table: z_mock_api_rule（Mock 规则配置）
-- ----------------------------
CREATE TABLE IF NOT EXISTS `z_mock_api_rule` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '自增主键',
    `rule_name`     VARCHAR(128)    NOT NULL                            COMMENT '规则名称',
    `url_pattern`   VARCHAR(512)    NOT NULL                            COMMENT 'URL 匹配模式（关键字或正则表达式）',
    `match_type`    VARCHAR(32)     NOT NULL DEFAULT 'contains'         COMMENT '匹配方式: contains-包含 regex-正则 exact-精确',
    `response_file` VARCHAR(512)    NOT NULL DEFAULT ''                 COMMENT 'JSON 响应数据文件路径（最高优先级）',
    `response_data` LONGTEXT        NOT NULL                            COMMENT '内联响应数据（JSON 字符串，可作为数据库查询降级 fallback）',
    `response_sql`  LONGTEXT        NOT NULL                            COMMENT 'SQL 查询语句（命中规则时实时执行）',
    `response_db`   LONGTEXT        NOT NULL                            COMMENT '数据库连接配置（JSON 格式: {host, port, username, password, database, db_type}）',
    `status_code`   INT UNSIGNED    NOT NULL DEFAULT 200                COMMENT '响应 HTTP 状态码',
    `status`        SMALLINT        NOT NULL DEFAULT 1                  COMMENT '状态：1-启用 0-停用',
    `sort_order`    INT UNSIGNED    NOT NULL DEFAULT 0                  COMMENT '排序序号（越小越靠前）',
    `remark`        VARCHAR(512)    NOT NULL DEFAULT ''                 COMMENT '备注',
    `create_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间',
    PRIMARY KEY (`id`),
    KEY `idx_status` (`status`),
    KEY `idx_sort` (`sort_order`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Mock API 规则配置';

-- ----------------------------
-- Table: z_mock_api_db_config（Mock API 数据库连接配置，可复用）
-- ----------------------------
CREATE TABLE IF NOT EXISTS `z_mock_api_db_config` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '自增主键',
    `config_key`    VARCHAR(64)     NOT NULL                            COMMENT '连接标识（唯一）',
    `db_type`       VARCHAR(32)     NOT NULL DEFAULT 'mysql'            COMMENT '数据库类型',
    `host`          VARCHAR(128)    NOT NULL                            COMMENT '主机地址',
    `port`          INT UNSIGNED    NOT NULL DEFAULT 3306               COMMENT '端口',
    `username`      VARCHAR(64)     NOT NULL                            COMMENT '用户名',
    `password`      VARCHAR(256)    NOT NULL                            COMMENT '密码',
    `database`      VARCHAR(128)    NOT NULL                            COMMENT '数据库名',
    `status`        SMALLINT        NOT NULL DEFAULT 1                  COMMENT '状态：1-启用 0-停用',
    `remark`        VARCHAR(512)    NOT NULL DEFAULT ''                 COMMENT '备注',
    `create_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_config_key` (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Mock API 数据库连接配置';
