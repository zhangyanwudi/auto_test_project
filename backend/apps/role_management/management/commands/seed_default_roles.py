from django.core.management.base import BaseCommand
from apps.role_management.models import ZRole, ZRoleMenu
from apps.menu_management.models import ZMenu


class Command(BaseCommand):
    help = '创建默认角色「超级管理员」并关联全部启用菜单，并给 z_user 第一条用户绑定该角色'

    def handle(self, *args, **options):
        r, created = ZRole.objects.get_or_create(
            role_code='super_admin',
            defaults={'role_name': '超级管理员', 'remark': '默认拥有全部菜单', 'status': 1},
        )
        if not created:
            self.stdout.write('角色 super_admin 已存在')
        else:
            self.stdout.write(self.style.SUCCESS('已创建角色：超级管理员'))

        mids = list(ZMenu.objects.filter(status=1).values_list('id', flat=True))
        ZRoleMenu.objects.filter(role=r).delete()
        for mid in mids:
            ZRoleMenu.objects.get_or_create(role=r, menu_id=mid)

        self.stdout.write(self.style.SUCCESS(f'已为 {r.role_name} 关联 {len(mids)} 个菜单'))

        # 绑定 z_user 最小 id 用户
        from apps.users.models import ZUser
        first = ZUser.objects.order_by('id').first()
        if first:
            first.role_id = r.id
            first.save(update_fields=['role_id'])
            self.stdout.write(self.style.SUCCESS(f'用户 id={first.id} 已绑定角色 {r.role_name}'))
        else:
            self.stdout.write('无用户数据，跳过绑定')
