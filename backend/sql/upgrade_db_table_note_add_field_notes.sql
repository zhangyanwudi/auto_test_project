-- 数据库表备注（db_table_note）增量升级：新增「字段手动备注」列
-- 适用：已按 init_db_table_note.sql 建过表的环境
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

ALTER TABLE `z_db_table_note`
    ADD COLUMN `field_notes` TEXT NULL COMMENT '字段手动备注（JSON：{字段名:备注}）' AFTER `sql_records`;
