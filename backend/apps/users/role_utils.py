"""当前用户与角色相关的工具（如是否超级管理员）。"""
from apps.role_management.models import ZRole


def _first_user_id():
    """z_user 中 id 最小的一条，与业务上「系统管理员」一致。"""
    from apps.users.models import ZUser

    return ZUser.objects.order_by('id').values_list('id', flat=True).first()


def get_user_role_flags(user):
    """
    返回 dict: role_code (str|None), is_super_admin (bool)

    is_super_admin 为 True 当且仅当：
    - 当前用户为系统管理员（id 最小），或
    - 绑定角色 role_code == 'super_admin'

    说明：部分环境未给首条用户绑定 role_id，但仍视为超级管理员（与侧栏全菜单逻辑一致）。
    """
    if not user:
        return {'role_code': None, 'is_super_admin': False}

    first_id = _first_user_id()
    if first_id is not None and user.id == first_id:
        rid = getattr(user, 'role_id', None)
        role_code = None
        if rid:
            try:
                role_code = ZRole.objects.get(pk=rid).role_code
            except ZRole.DoesNotExist:
                pass
        return {'role_code': role_code, 'is_super_admin': True}

    rid = getattr(user, 'role_id', None)
    if not rid:
        return {'role_code': None, 'is_super_admin': False}
    try:
        r = ZRole.objects.get(pk=rid)
        return {
            'role_code': r.role_code,
            'is_super_admin': r.role_code == 'super_admin',
        }
    except ZRole.DoesNotExist:
        return {'role_code': None, 'is_super_admin': False}
