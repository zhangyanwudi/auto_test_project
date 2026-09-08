-- 用例管理（case_govern）增量升级：创建人支持配置多个（英文逗号分隔，均有编辑/删除权限）
-- 适用：已按 init_case_govern.sql 建过表的环境
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

ALTER TABLE `z_case_govern_case`
    MODIFY COLUMN `creator` VARCHAR(256) NOT NULL DEFAULT '' COMMENT '创建人（多个用英文逗号分隔，均有编辑/删除权限）';
