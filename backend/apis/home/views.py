"""
首页 / 仪表盘 API：当日配置比对统计数据查询。
"""
import logging
from urllib.parse import parse_qs

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.operate_tool.models import ZConfigCompareStat
from apps.users.decorators import require_valid_token

logger = logging.getLogger(__name__)


def _ok(data=None, msg='成功'):
    payload = {'code': 0, 'success': True, 'message': msg, 'msg': msg, 'data': data or {}}
    return JsonResponse(payload)


def _fail(msg, code=400, status=400):
    return JsonResponse(
        {'code': code, 'success': False, 'message': msg, 'msg': msg, 'data': None},
        status=status,
    )


def _extract_scheme_name(adwaynum_value):
    """从 'project\x1fschemeName' 格式中提取方案名称"""
    if not adwaynum_value:
        return ''
    sep = '\x1f'
    parts = adwaynum_value.split(sep)
    return parts[-1] if len(parts) > 1 else adwaynum_value


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def get_daily_statistic(request):
    """查询当日配置比对统计数据"""
    try:
        now = timezone.now()
        # 用本地时区（Asia/Shanghai）的「今天」0 点作为今日边界，
        # 否则按 UTC 0 点切分会让北京时间 0:00–8:00 的记录被归到「昨天」
        today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)

        today_records = ZConfigCompareStat.objects.filter(create_time__gte=today_start)

        total_count = today_records.count()
        single_count = today_records.filter(compare_type='single').count()
        batch_count = today_records.filter(compare_type='batch').count()

        unique_users = today_records.values('user_name').distinct().count()

        project_count_map = {}
        for record in today_records.values_list('project_names', flat=True):
            if record:
                for p in record.split(','):
                    p = p.strip()
                    if p:
                        project_count_map[p] = project_count_map.get(p, 0) + 1
        unique_projects = len(project_count_map)
        project_stats = sorted(
            [{'name': k, 'count': v} for k, v in project_count_map.items()],
            key=lambda x: -x['count']
        )[:10]

        hourly_map = {}
        for r in today_records.values_list('create_time', flat=True):
            if r:
                hour_key = timezone.localtime(r).strftime('%H:00')
                hourly_map[hour_key] = hourly_map.get(hour_key, 0) + 1
        hourly_stats = [{'hour': h, 'count': c} for h, c in sorted(hourly_map.items())]

        recent_qs = today_records.order_by('-create_time')[:10]
        recent_list = []
        for r in recent_qs:
            recent_list.append({
                'id': r.id,
                'project_names': r.project_names,
                'user_name': r.user_name,
                'compare_type': r.compare_type,
                'left_Adwaynum': _extract_scheme_name(r.left_Adwaynum),
                'right_Adwaynum': _extract_scheme_name(r.right_Adwaynum),
                'left_region': r.left_region,
                'right_region': r.right_region,
                'create_time': timezone.localtime(r.create_time).strftime('%Y-%m-%d %H:%M:%S') if r.create_time else '',
            })

        data = {
            'total_count': total_count,
            'single_count': single_count,
            'batch_count': batch_count,
            'unique_users': unique_users,
            'unique_projects': unique_projects,
            'project_stats': project_stats,
            'hourly_stats': hourly_stats,
            'recent_list': recent_list,
        }
        return _ok(data, '获取成功')
    except Exception as e:
        logger.exception('get_daily_statistic')
        return _fail(str(e), 500, 500)
