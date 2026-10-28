-- 定时任务执行日志表（scheduled_task 增量新增）
-- 每次任务执行（立即运行 / Cron 调度）都会写入一条记录，用于页面展示执行历史与详情。
-- 数据库: auto_test_db
-- 执行前请确认已选择正确的数据库: USE auto_test_db;

CREATE TABLE IF NOT EXISTS `z_scheduled_task_run_log` (
    `id`            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    `task_id`       BIGINT       NOT NULL COMMENT '关联定时任务 z_scheduled_task.id',
    `trigger_type`  VARCHAR(16)  NOT NULL DEFAULT 'manual' COMMENT '触发方式：manual-立即运行 cron-定时调度',
    `start_time`    DATETIME(6)  NOT NULL COMMENT '开始执行时间',
    `end_time`      DATETIME(6)  NULL COMMENT '结束执行时间',
    `duration_ms`   INT          NOT NULL DEFAULT 0 COMMENT '执行时长（毫秒）',
    `success`       TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否成功：1-成功 0-失败',
    `message`       VARCHAR(512) NOT NULL DEFAULT '' COMMENT '执行说明',
    `detail_json`   LONGTEXT     NULL COMMENT '执行详情JSON（命令/退出码/成功失败消息/stdout等）',
    `create_time`   DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_run_log_task_time` (`task_id`, `start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务执行日志';
