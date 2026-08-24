-- 用例管理（case_govern）增量升级：给思维导图节点表增加「冒烟测试」标记列
-- 适用：已按 init_case_govern.sql 建过表的环境
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

ALTER TABLE `z_case_govern_case_node`
    ADD COLUMN `is_smoke` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '冒烟测试：1-冒烟用例，优先执行' AFTER `node_type`;
