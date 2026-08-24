-- 用例管理（case_govern）增量升级：给思维导图节点表增加「执行结果」标记列
-- 适用：已按 init_case_govern.sql 建过表的环境
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

ALTER TABLE `z_case_govern_case_node`
    ADD COLUMN `exec_result` VARCHAR(16) NOT NULL DEFAULT '' COMMENT '执行结果：pass-通过 fail-不通过 空-未执行' AFTER `is_smoke`;
