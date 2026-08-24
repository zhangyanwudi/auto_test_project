-- 配置比对使用统计表
CREATE TABLE IF NOT EXISTS `z_config_compare_stat` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  `project_names` VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '项目名称（逗号分隔）',
  `user_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '操作人',
  `compare_type` VARCHAR(32) NOT NULL DEFAULT 'single' COMMENT '比对类型：single-单次对比 batch-批量比对',
  `left_Adwaynum` VARCHAR(512) NOT NULL DEFAULT '' COMMENT '左侧方案',
  `right_Adwaynum` VARCHAR(512) NOT NULL DEFAULT '' COMMENT '右侧方案',
  `leftTimeslot` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '左侧时间段',
  `rightTimeslot` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '右侧时间段',
  `left_region` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '左侧区域',
  `right_region` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '右侧区域',
  `batch_left_count` INT NOT NULL DEFAULT 0 COMMENT '批量-左侧方案数',
  `batch_right_count` INT NOT NULL DEFAULT 0 COMMENT '批量-右侧方案数',
  `batch_pair_count` INT NOT NULL DEFAULT 0 COMMENT '批量-配对数',
  `raw_data` TEXT COMMENT '原始上报数据',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  INDEX `idx_create_date` (`create_time`),
  INDEX `idx_user_name` (`user_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='配置比对使用统计';
