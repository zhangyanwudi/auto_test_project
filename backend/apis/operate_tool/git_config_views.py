"""
配置比对 API：与 read_git_config.ReadGitConfig 对接，响应格式与前端 gitConfigDiff.js 一致。
"""
import json
import logging
from urllib.parse import parse_qs

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.operate_tool.models import ZConfigCompareStat
from apps.users.decorators import require_valid_token
from base_utils.path_base import exists
from .read_git_config import (
    ReadGitConfig,
    sync_rebuild_adwaynum_file_cache,
    _invalidate_adwaynum_slot_cache,
)

logger = logging.getLogger(__name__)


def _ok(data=None, msg='成功'):
    payload = {'code': 0, 'success': True, 'message': msg, 'msg': msg, 'data': data or {}}
    return JsonResponse(payload)


def _fail(msg, code=400, status=400):
    return JsonResponse(
        {'code': code, 'success': False, 'message': msg, 'msg': msg, 'data': None},
        status=status,
    )


def _parse_time_slot_slot(timeslot: str) -> int:
    """left_time_slot_1 / right_time_slot_2 -> 数字槽位 0-3"""
    if not timeslot:
        return 0
    parts = str(timeslot).split('_')
    if len(parts) >= 4:
        try:
            return int(parts[3])
        except ValueError:
            return 0
    return 0


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def get_git_info(request):
    """获取期数等业务信息：?select_project=xxx"""
    project_name = (request.GET.get('select_project') or request.GET.get('project_name') or '').strip()
    if not project_name:
        return _fail('缺少项目名称 select_project', 400)
    try:
        reader = ReadGitConfig(project_name)
        business_v = reader.get_business_v()
        data = {'business_v': business_v, 'left_region': {}, 'right_region': {}}
        return _ok(data, '获取成功')
    except Exception as e:
        logger.exception('get_git_info')
        return _fail(str(e), 500, 500)


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def get_adwaynum_file(request):
    """获取方案文件列表"""
    project_name = (request.GET.get('project_name') or '').strip()
    business_v = request.GET.get('business_v') or ''
    timeslot = request.GET.get('timeslot') or ''
    if not project_name:
        return _fail('缺少 project_name', 400)
    slot = _parse_time_slot_slot(timeslot)
    try:
        reader = ReadGitConfig(project_name)
        if project_name.startswith('ios_'):
            files = reader.get_ios_adwaynum_file_v2(time_slot=slot, business_v=business_v or None)
        else:
            files = reader.get_gp_adwaynum_file(time_slot=slot, business_v=business_v or None)
        if isinstance(files, dict) and files.get('error'):
            return _fail(files['error'], 400)
        if not isinstance(files, list):
            files = []
        raw_meta = getattr(reader, '_last_adwaynum_cache_meta', None) or {}
        from_official = raw_meta.get('from_official_file')
        if business_v:
            from_official = None
        adwaynum_cache = {'from_official_file': from_official}
        return _ok({'adwaynum_files': files, 'adwaynum_cache': adwaynum_cache}, '获取成功')
    except Exception as e:
        logger.exception('get_adwaynum_file')
        return _fail(str(e), 500, 500)


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def get_adwaynum_json_2(request):
    """获取方案 JSON（按区域组织）"""
    project_name = (request.GET.get('project_name') or '').strip()
    business_v = request.GET.get('business_v') or ''
    adwaynum_name = (request.GET.get('adwaynum') or '').strip()
    timeslot = request.GET.get('timeslot') or ''
    if not project_name or not adwaynum_name:
        return _fail('缺少 project_name 或 adwaynum', 400)
    slot = _parse_time_slot_slot(timeslot)
    try:
        reader = ReadGitConfig(project_name)
        if not exists(reader.project_dir):
            return _fail(f'项目目录不存在: {reader.project_dir}', 400)
        if project_name.startswith('ios_'):
            adwaynum_json = reader.get_ios_adwaynum_json_v2(business_v, adwaynum_name)
        else:
            adwaynum_json = reader.get_gp_adwaynum_json_v4(business_v, adwaynum_name, slot)
        if isinstance(adwaynum_json, dict) and adwaynum_json.get('error'):
            return _fail(adwaynum_json['error'], 400)
        return _ok({'adwaynum_json': adwaynum_json}, '获取成功')
    except Exception as e:
        logger.exception('get_adwaynum_json_2')
        return _fail(str(e), 500, 500)


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def rebuild_adwaynum_cache(request):
    """手动触发方案列表磁盘缓存重建（同步阻塞，完成后返回）"""
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        body = {}

    project_name = (body.get('project_name') or request.GET.get('project_name') or '').strip()
    raw_names = body.get('project_names')
    if isinstance(raw_names, list):
        names = [str(p).strip() for p in raw_names if str(p).strip()]
    elif project_name:
        names = [project_name]
    else:
        return _fail('缺少 project_name 或 project_names', 400)

    errors = []
    for name in names:
        _invalidate_adwaynum_slot_cache(name)
        try:
            sync_rebuild_adwaynum_file_cache(name)
        except Exception as e:
            logger.exception('rebuild_adwaynum_cache %s', name)
            errors.append(f'{name}: {e}')

    if errors:
        return _fail('; '.join(errors), 500, 500)

    msg = f'已完成 {len(names)} 个项目的方案缓存同步'
    return _ok({'project_names': names}, msg)


def _parse_stat_body(raw_body):
    """
    解析上报的统计文本（格式为 key=value 对，用 & 或换行分隔）。
    返回 dict，常见字段：
      project_name, user_name, left_Adwaynum, right_Adwaynum,
      leftTimeslot, rightTimeslot, left_region, right_region,
      batch_compare, left_count, right_count, pair_count
    """
    if not raw_body:
        return {}
    text = raw_body.decode('utf-8', errors='replace') if isinstance(raw_body, bytes) else str(raw_body)
    # 将 & 和换行统一替换为 &
    normalized = text.replace('\n', '&').replace('\r', '')
    parsed = parse_qs(normalized, keep_blank_values=True)
    # parse_qs 返回 {key: [value, ...]}，取每个 key 的第一个值
    result = {}
    for k, v in parsed.items():
        val = v[0] if v else ''
        result[k] = val
    return result


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def report_statistic_info(request):
    """统计上报：解析并存入数据库"""
    raw = (request.body or b'').decode('utf-8', errors='replace')
    logger.info('config_compare_stat: %s', raw[:2000])

    try:
        data = _parse_stat_body(request.body or b'')
        user_name = data.get('user_name', '') or getattr(request, 'z_user', None)
        if hasattr(user_name, 'user_name'):
            user_name = user_name.user_cn_name or user_name.user_name

        is_batch = data.get('batch_compare') == '1'

        ZConfigCompareStat.objects.create(
            project_names=data.get('project_name', ''),
            user_name=str(user_name) if user_name else '',
            compare_type='batch' if is_batch else 'single',
            left_Adwaynum=data.get('left_Adwaynum', ''),
            right_Adwaynum=data.get('right_Adwaynum', ''),
            leftTimeslot=data.get('leftTimeslot', ''),
            rightTimeslot=data.get('rightTimeslot', ''),
            left_region=data.get('left_region', ''),
            right_region=data.get('right_region', ''),
            batch_left_count=int(data.get('left_count', 0)),
            batch_right_count=int(data.get('right_count', 0)),
            batch_pair_count=int(data.get('pair_count', 0)),
            raw_data=raw[:2000],
        )
    except Exception as e:
        logger.exception('report_statistic_info save error: %s', e)
        # 存库失败不应影响前端体验，仍返回成功

    return _ok({}, '已记录')


# 兼容旧 FastAPI 路径别名（可选）
get_git_config_info_v2 = get_git_info


