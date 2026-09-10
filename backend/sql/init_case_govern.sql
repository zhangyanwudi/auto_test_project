-- 用例管理（case_govern）建表 SQL
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;
-- 菜单（menu_code=case_govern）已在页面「菜单管理」中创建，本脚本只负责建表。

-- ----------------------------
-- Table: z_case_govern_module（用例模块，可配置，供下拉选择）
-- ----------------------------
CREATE TABLE IF NOT EXISTS `z_case_govern_module` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '自增主键',
    `module_name`   VARCHAR(128)    NOT NULL                            COMMENT '模块名称（唯一）',
    `status`        SMALLINT        NOT NULL DEFAULT 1                  COMMENT '状态：1-启用 0-停用',
    `sort_order`    INT UNSIGNED    NOT NULL DEFAULT 0                  COMMENT '排序序号（越小越靠前）',
    `create_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_module_name` (`module_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用例管理-模块配置';

-- ----------------------------
-- Table: z_case_govern_case（用例主表）
-- ----------------------------
CREATE TABLE IF NOT EXISTS `z_case_govern_case` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '自增主键',
    `case_name`     VARCHAR(128)    NOT NULL                            COMMENT '用例名称',
    `module`        VARCHAR(128)    NOT NULL DEFAULT ''                 COMMENT '所属模块',
    `priority`      SMALLINT        NOT NULL DEFAULT 2                  COMMENT '优先级：1-高 2-中 3-低',
    `status`        SMALLINT        NOT NULL DEFAULT 1                  COMMENT '状态：1-启用 0-停用',
    `creator`       VARCHAR(256)    NOT NULL DEFAULT ''                 COMMENT '创建人（多个用英文逗号分隔，均有编辑/删除权限）',
    `description`   VARCHAR(512)    NOT NULL DEFAULT ''                 COMMENT '说明',
    `image`         LONGTEXT        NULL                                COMMENT '图片（base64 data URL，粘贴）',
    `create_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_case_module` (`case_name`, `module`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用例管理-用例主表';

-- ----------------------------
-- Table: z_case_govern_case_node（思维导图节点表，parent_id 树形关联）
-- ----------------------------
CREATE TABLE IF NOT EXISTS `z_case_govern_case_node` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT              COMMENT '自增主键',
    `case_id`       BIGINT          NOT NULL                            COMMENT '关联用例主表 id',
    `parent_id`     BIGINT          NULL                                COMMENT '父节点 id（NULL=根节点）',
    `node_type`     VARCHAR(32)     NOT NULL DEFAULT 'case'             COMMENT '节点类型：module-模块 case-用例 step-步骤 expect-预期 precondition-前置条件 result-结果',
    `is_smoke`      TINYINT(1)      NOT NULL DEFAULT 0                  COMMENT '冒烟测试：1-冒烟用例，优先执行',
    `exec_result`   VARCHAR(16)     NOT NULL DEFAULT ''                 COMMENT '执行结果：pass-通过 fail-不通过 空-未执行',
    `collapsed`     TINYINT(1)      NOT NULL DEFAULT 0                  COMMENT '收起子节点：1-收起 0-展开',
    `title`         VARCHAR(512)    NOT NULL                            COMMENT '节点文本',
    `image`         LONGTEXT        NULL                                COMMENT '图片（base64 data URL，粘贴）',
    `sort_order`    INT UNSIGNED    NOT NULL DEFAULT 0                  COMMENT '同级排序（越小越靠前）',
    `create_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    `update_time`   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间',
    PRIMARY KEY (`id`),
    KEY `idx_case` (`case_id`),
    KEY `idx_parent` (`parent_id`),
    CONSTRAINT `fk_case_govern_node_case` FOREIGN KEY (`case_id`) REFERENCES `z_case_govern_case` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_case_govern_node_parent` FOREIGN KEY (`parent_id`) REFERENCES `z_case_govern_case_node` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用例管理-思维导图节点';
