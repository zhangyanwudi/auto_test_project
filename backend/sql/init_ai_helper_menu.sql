-- AI助手 菜单注册
-- 1. 在 z_menu 表中插入 AI助手 菜单项
--    menu_code 必须与 Home.vue 中 viewMap 的 key 一致：ai_helper
INSERT INTO `z_menu` (`menu_name`, `menu_code`, `path`, `parent_id`, `icon`, `sort_order`, `status`, `create_time`, `update_time`)
VALUES ('AI助手', 'ai_helper', '@/views/ai_helper/AiHelperPage.vue', NULL, 'ChatDotRound', 18, 1, NOW(), NOW())
ON DUPLICATE KEY UPDATE `menu_name` = 'AI助手', `status` = 1;

-- 2. 将 AI助手 菜单关联到超级管理员角色（确保角色能看到此菜单）
INSERT INTO `z_role_menu` (`role_id`, `menu_id`)
SELECT r.id, m.id
FROM `z_role` r
CROSS JOIN `z_menu` m
WHERE r.role_code = 'super_admin'
  AND m.menu_code = 'ai_helper'
  AND NOT EXISTS (
    SELECT 1 FROM `z_role_menu` rm
    WHERE rm.role_id = r.id AND rm.menu_id = m.id
  );
