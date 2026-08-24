from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.menu_management.models import ZMenu

# menu_code -> 与前端 Vue 页面对应的路径说明（存库，菜单管理页展示）
DEFAULT_PATHS = {
    'home': '@/views/Home.vue',
    'dashboard': '@/views/Dashboard.vue',
    'system': '',  # 仅分组，无独立页
    'users': '@/views/system/UserManagement.vue',
    'roles': '@/views/system/RoleManagement.vue',
    'menu_management': '@/views/system/MenuManagement.vue',
    'icon_management': '@/views/system/IconManagement.vue',
    'config_compare': '@/views/tools/ConfigCompare.vue',
    'convenience_tools': '',  # 便捷工具（分组）
    'settings': '@/views/system/Settings.vue',
    'scheduled_task': '@/views/task/ScheduledTaskManagement.vue',
    'page_scheduled': '',  # 「定时任务」分组父级（与系统管理平级），无独立页；子菜单亦为「定时任务」
    'gp_logcat': '@/views/gp_logcat/GpLogcat.vue',
    'mock_api': '@/views/mock_api/MockApiManagement.vue',
}


class Command(BaseCommand):
    help = '写入默认后台菜单（含系统管理、「定时任务」分组与子菜单路径）；已存在 menu_code 则跳过创建'

    def handle(self, *args, **options):
        # 1) 顶级菜单
        top = [
            ('首页', 'home', 'House', 10),
            ('数据概览', 'dashboard', 'DataAnalysis', 20),
        ]
        for name, code, icon, order in top:
            if ZMenu.objects.filter(menu_code=code).exists():
                continue
            ZMenu.objects.create(
                menu_name=name,
                menu_code=code,
                path=DEFAULT_PATHS.get(code, ''),
                icon=icon,
                sort_order=order,
                status=1,
                parent=None,
            )

        # 2) 便捷工具（父级）
        conv = ZMenu.objects.filter(menu_code='convenience_tools').first()
        if not conv:
            conv = ZMenu.objects.create(
                menu_name='便捷工具',
                menu_code='convenience_tools',
                path=DEFAULT_PATHS.get('convenience_tools', ''),
                icon='Operation',
                sort_order=22,
                status=1,
                parent=None,
            )

        # 2b) 配置比对
        if not ZMenu.objects.filter(menu_code='config_compare').exists():
            ZMenu.objects.create(
                menu_name='配置比对',
                menu_code='config_compare',
                path=DEFAULT_PATHS.get('config_compare', ''),
                icon='DocumentCopy',
                sort_order=23,
                status=1,
                parent=conv,
            )

        # 2c) GP商业化日志
        if not ZMenu.objects.filter(menu_code='gp_logcat').exists():
            ZMenu.objects.create(
                menu_name='GP商业化日志',
                menu_code='gp_logcat',
                path=DEFAULT_PATHS.get('gp_logcat', ''),
                icon='Monitor',
                sort_order=24,
                status=1,
                parent=conv,
            )

        # 2c2) Mock接口管理
        if not ZMenu.objects.filter(menu_code='mock_api').exists():
            ZMenu.objects.create(
                menu_name='Mock接口管理',
                menu_code='mock_api',
                path=DEFAULT_PATHS.get('mock_api', ''),
                icon='Connection',
                sort_order=25,
                status=1,
                parent=conv,
            )

        # 2d) 定时任务（父级分组，独立于系统管理）；侧栏路径为【定时任务】-【定时任务】
        page_scheduled = ZMenu.objects.filter(menu_code='page_scheduled').first()
        if not page_scheduled:
            page_scheduled = ZMenu.objects.create(
                menu_name='定时任务',
                menu_code='page_scheduled',
                path=DEFAULT_PATHS.get('page_scheduled', ''),
                icon='Clock',
                sort_order=24,
                status=1,
                parent=None,
            )

        # 2e) 定时任务（子菜单，cron 配置页挂载在 2d 下；与父级同名，menu_code 区分）
        if not ZMenu.objects.filter(menu_code='scheduled_task').exists():
            ZMenu.objects.create(
                menu_name='定时任务',
                menu_code='scheduled_task',
                path=DEFAULT_PATHS.get('scheduled_task', ''),
                icon='Timer',
                sort_order=10,
                status=1,
                parent=page_scheduled,
            )

        # 3) 系统管理（父级）
        system = ZMenu.objects.filter(menu_code='system').first()
        if not system:
            system = ZMenu.objects.create(
                menu_name='系统管理',
                menu_code='system',
                path=DEFAULT_PATHS.get('system', ''),
                icon='Setting',
                sort_order=25,
                status=1,
                parent=None,
            )

        # 4) 系统管理下子菜单（「定时任务」分组见 2c/2d，不归入此处）
        children = [
            ('用户管理', 'users', 'User', 30),
            ('角色管理', 'roles', 'UserFilled', 40),
            ('菜单管理', 'menu_management', 'Menu', 45),
            ('图标管理', 'icon_management', 'Grid', 50),
        ]
        for name, code, icon, order in children:
            if ZMenu.objects.filter(menu_code=code).exists():
                continue
            ZMenu.objects.create(
                menu_name=name,
                menu_code=code,
                path=DEFAULT_PATHS.get(code, ''),
                icon=icon,
                sort_order=order,
                status=1,
                parent=system,
            )

        # 5) 系统设置（顶级）
        if not ZMenu.objects.filter(menu_code='settings').exists():
            ZMenu.objects.create(
                menu_name='系统设置',
                menu_code='settings',
                path=DEFAULT_PATHS.get('settings', ''),
                icon='Tools',
                sort_order=60,
                status=1,
                parent=None,
            )

        # 6) 已存在记录：若 path 为空则补全（便于老数据升级）
        for code, p in DEFAULT_PATHS.items():
            ZMenu.objects.filter(menu_code=code, path='').update(path=p)

        # 7) 子菜单挂载：用户/角色/菜单/图标 ->「系统管理」；配置比对 ->「便捷工具」；子级「定时任务」-> 父级「定时任务」分组
        system = ZMenu.objects.filter(menu_code='system').first()
        if system:
            ZMenu.objects.filter(
                menu_code__in=['users', 'roles', 'menu_management', 'icon_management']
            ).update(parent=system)
        conv = ZMenu.objects.filter(menu_code='convenience_tools').first()
        if conv:
            ZMenu.objects.filter(menu_code='config_compare').update(parent=conv)
            ZMenu.objects.filter(menu_code='gp_logcat').update(parent=conv)
            ZMenu.objects.filter(menu_code='mock_api').update(parent=conv)
        page_scheduled = ZMenu.objects.filter(menu_code='page_scheduled').first()
        if page_scheduled:
            ZMenu.objects.filter(menu_code='page_scheduled').update(menu_name='定时任务')
            ZMenu.objects.filter(menu_code='scheduled_task').update(
                parent_id=page_scheduled.pk,
                menu_name='定时任务',
            )

        # 8) 图标管理等新菜单默认关联超级管理员角色
        from apps.role_management.models import ZRole, ZRoleMenu

        sa = ZRole.objects.filter(role_code='super_admin').first()
        if sa:
            for m in ZMenu.objects.filter(
                menu_code__in=['page_scheduled', 'icon_management', 'config_compare', 'scheduled_task', 'gp_logcat', 'mock_api']
            ):
                ZRoleMenu.objects.get_or_create(role=sa, menu=m)

        self.stdout.write(
            self.style.SUCCESS('默认菜单结构已就绪（新建、补全 path、层级挂接到 system / 便捷工具 /「定时任务」分组）')
        )
