-- 数据库表备注（db_table_note）增量升级：连接配置支持 PostgreSQL
-- 新增 db_type（mysql / postgre，默认 mysql，存量连接保持 MySQL 行为不变）
-- 新增 schema_name（仅 PostgreSQL 使用，默认 public）
-- 适用：已按 init_db_table_note_connection.sql 建过表的环境
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

ALTER TABLE `z_db_table_note_connection`
    ADD COLUMN `db_type`    VARCHAR(16)  NOT NULL DEFAULT 'mysql'  COMMENT '数据库类型（mysql / postgre）' AFTER `database`,
    ADD COLUMN `schema_name` VARCHAR(128) NOT NULL DEFAULT 'public' COMMENT 'PostgreSQL 模式名（仅 postgre 使用）' AFTER `db_type`;
