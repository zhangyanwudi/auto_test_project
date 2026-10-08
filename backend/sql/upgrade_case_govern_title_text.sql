-- 用例管理（case_govern）增量升级：节点文本 title 由 VARCHAR(512) 扩展为 TEXT
-- 适用：已按 init_case_govern.sql 建过表的环境
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

ALTER TABLE `z_case_govern_case_node`
    MODIFY COLUMN `title` TEXT NOT NULL COMMENT '节点文本';
