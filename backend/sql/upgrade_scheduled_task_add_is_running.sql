-- 定时任务（scheduled_task）增量升级：给任务表增加「运行中」标记列
-- 适用：已建 z_scheduled_task 表的环境
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

ALTER TABLE `z_scheduled_task`
    ADD COLUMN `is_running` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否运行中：1-运行中 0-空闲' AFTER `status`;
