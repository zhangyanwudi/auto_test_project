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


# 参与首页「按菜单功能统计」的功能编码（新增功能时在此扩展）
FEATURE_MENUS = [
    ('case_govern', '用例管理'),
    ('ai_helper', 'AI助手'),
    ('mock_api', 'Mock接口'),
    ('scheduled_task', '定时任务'),
    ('db_table_note', '数据库备注'),
    ('config_compare', '配置比对'),
]


def _parse_time_range(request):
    """解析查询参数 start / end（YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS），返回 (start_dt, end_dt, err)。

    未传表示全量；时区按本地（Asia/Shanghai）。错误格式返回 err 文案。
    """
    from django.utils.dateparse import parse_datetime
    import datetime as _dt

    start_raw = (request.GET.get('start') or '').strip()
    end_raw = (request.GET.get('end') or '').strip()

    def _to_dt(raw):
        if not raw:
            return None
        # 仅日期则补 00:00:00
        if len(raw) == 10:
            raw = raw + ' 00:00:00'
        return parse_datetime(raw)

    start_dt = _to_dt(start_raw)
    end_dt = _to_dt(end_raw)
    if start_raw and start_dt is None:
        return None, None, 'start 时间格式错误'
    if end_raw and end_dt is None:
        return None, None, 'end 时间格式错误'

    # naive 视为本地时区，转为 UTC 以与 USE_TZ=True 存储一致
    if start_dt and start_dt.tzinfo is None:
        start_dt = timezone.make_aware(start_dt)
    if end_dt and end_dt.tzinfo is None:
        end_dt = timezone.make_aware(end_dt)

    # end 为「当天」时按当天 23:59:59 结束，更符合直觉
    if end_dt and len(end_raw) == 10:
        end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    return start_dt, end_dt, None


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def feature_usage_report(request):
    """功能使用上报：进入某功能页停留满 1 分钟，前端调用本接口记一次使用。

    body: { menu_code, menu_name }
    """
    import json as _json
    try:
        body = _json.loads(request.body or '{}')
    except _json.JSONDecodeError:
        return _fail('请求体格式错误', 400, 400)
    menu_code = (body.get('menu_code') or '').strip()
    menu_name = (body.get('menu_name') or '').strip()
    if not menu_code or not menu_name:
        return _fail('缺少 menu_code 或 menu_name', 400, 400)

    # 仅记录已纳入统计的功能编码，避免脏数据
    allowed = {code for code, _ in FEATURE_MENUS}
    if menu_code not in allowed:
        return _fail('未纳入统计的功能编码', 400, 400)

    user = getattr(request, 'z_user', None)
    user_name = ''
    if user:
        user_name = (getattr(user, 'user_cn_name', '') or getattr(user, 'user_name', '') or '').strip()

    from apps.operate_tool.models import ZFeatureUsage
    ZFeatureUsage.objects.create(
        menu_code=menu_code,
        menu_name=menu_name,
        user_name=user_name,
    )
    return _ok({'recorded': True}, '上报成功')


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def feature_usage_statistic(request):
    """按菜单功能统计使用次数（全量；支持 start/end 时间过滤，未传为全量）。"""
    from apps.operate_tool.models import ZFeatureUsage
    from django.db.models import Count

    start_dt, end_dt, err = _parse_time_range(request)
    if err:
        return _fail(err, 400, 400)

    qs = ZFeatureUsage.objects.all()
    if start_dt:
        qs = qs.filter(create_time__gte=start_dt)
    if end_dt:
        qs = qs.filter(create_time__lte=end_dt)

    # KPI：按功能统计次数（每次进入都算，不去重）
    count_map = dict(
        qs.values_list('menu_code').annotate(cnt=Count('id')).values_list('menu_code', 'cnt')
    )
    kpi = [
        {'menu_code': code, 'menu_name': name, 'usage_count': count_map.get(code, 0)}
        for code, name in FEATURE_MENUS
    ]
    total_usage = sum(c['usage_count'] for c in kpi)

    # 饼图：各功能使用占比（只保留有使用的）
    distribution = [
        {'name': name, 'value': count_map.get(code, 0)}
        for code, name in FEATURE_MENUS
        if count_map.get(code, 0) > 0
    ]

    # 折线图：近 1 天按小时趋势（每功能一列）
    now = timezone.now()
    day_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    today_qs = ZFeatureUsage.objects.filter(create_time__gte=day_start)
    hour_map = {}  # hour_key -> {menu_code: count}
    for menu_code, hour in today_qs.values_list('menu_code', 'create_time'):
        hk = timezone.localtime(hour).strftime('%H:00')
        bucket = hour_map.setdefault(hk, {})
        bucket[menu_code] = bucket.get(menu_code, 0) + 1
    trend = []
    for hk in sorted(hour_map.keys()):
        row = {'hour': hk}
        for code, _name in FEATURE_MENUS:
            row[code] = hour_map[hk].get(code, 0)
        trend.append(row)

    # 最近使用流水
    recent_qs = qs.order_by('-create_time')[:20]
    recent_list = [
        {
            'menu_code': r.menu_code,
            'menu_name': r.menu_name,
            'user_name': r.user_name,
            'use_time': timezone.localtime(r.create_time).strftime('%Y-%m-%d %H:%M:%S') if r.create_time else '',
        }
        for r in recent_qs
    ]

    data = {
        'kpi': kpi,
        'total_usage': total_usage,
        'distribution': distribution,
        'trend': trend,
        'recent_list': recent_list,
    }
    return _ok(data, '获取成功')
