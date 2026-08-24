"""
AI助手后端业务逻辑：对话管理、消息上下文构建、文件上传处理。
"""
import json
import logging
import os
import re
import uuid
from datetime import date, datetime

from django.conf import settings

from .models import AiConversation, AiMessage
from .gateway import load_config
from base_utils.path_base import check_dirs, exists, joint_path

logger = logging.getLogger(__name__)

# 上传文件存储的根目录（相对于 BASE_DIR）
UPLOAD_ROOT_DIR_NAME = 'data/ai_helper_uploads'

_cached_token = None  # 模块级 token 缓存，避免「全部」模式重复登录
# 允许的上传文件扩展名
ALLOWED_EXTENSIONS = {'.json', '.xlsx', '.xls', '.png', '.jpg', '.jpeg', '.gif', '.webp'}
# 上传文件最大大小（字节）
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB


def generate_conversation_code():
    """生成唯一的对话编码（UUID4 去除横线，32位）。"""
    return uuid.uuid4().hex


def get_or_create_conversation(user, conversation_code=None):
    """
    获取或新建对话会话。

    参数:
        user — ZUser 实例
        conversation_code — 对话编码，为空则新建

    返回:
        AiConversation 实例
    """
    if conversation_code:
        try:
            conv = AiConversation.objects.get(
                conversation_code=conversation_code,
                user=user,
                is_deleted=False,
            )
            return conv
        except AiConversation.DoesNotExist:
            # 对话不存在，使用传入的 conversation_code 创建新对话
            # （而不是生成新的 code，确保前端持有的 code 与数据库一致）
            return AiConversation.objects.create(
                conversation_code=conversation_code,
                user=user,
                title='',
            )
    # 没有传入 conversation_code，检查是否有可复用的空对话（无消息记录）
    empty_conv = AiConversation.objects.filter(
        user=user,
        is_deleted=False,
        messages__isnull=True,
    ).order_by('-update_time').first()
    if empty_conv:
        return empty_conv
    return AiConversation.objects.create(
        conversation_code=generate_conversation_code(),
        user=user,
        title='',
    )


def get_user_conversations(user):
    """获取用户未删除的对话列表，按更新时间倒序。"""
    return AiConversation.objects.filter(
        user=user,
        is_deleted=False,
    ).order_by('-update_time')


def soft_delete_conversation(conversation_code, user):
    """软删除对话（仅标记 is_deleted=True）。返回删除的对话或 None。"""
    try:
        conv = AiConversation.objects.get(
            conversation_code=conversation_code,
            user=user,
            is_deleted=False,
        )
        conv.is_deleted = True
        conv.save()
        return conv
    except AiConversation.DoesNotExist:
        return None


def clear_conversation_messages(conversation_code, user):
    """
    清空指定对话下的所有消息记录，对话本身保留。

    参数:
        conversation_code — 对话编码
        user — ZUser 实例

    返回:
        int — 删除的消息数量，若对话不存在或不属于该用户则返回 0
    """
    try:
        conv = AiConversation.objects.get(
            conversation_code=conversation_code,
            user=user,
            is_deleted=False,
        )
    except AiConversation.DoesNotExist:
        return 0

    count, _ = AiMessage.objects.filter(conversation=conv).delete()
    # 更新对话的 update_time（delete() 不会触发 FK 的 save）
    conv.save(update_fields=['update_time'])
    return count


def soft_delete_all_conversations(user):
    """
    软删除用户的所有对话。

    参数:
        user — ZUser 实例

    返回:
        int — 被软删除的对话数量
    """
    return AiConversation.objects.filter(
        user=user,
        is_deleted=False,
    ).update(is_deleted=True)


def build_context_messages(conversation, system_prompt=None):
    """
    从数据库历史消息构建上下文消息列表（用于发送给智能体网关）。

    参数:
        conversation — AiConversation 实例
        system_prompt — 可选，系统提示词

    返回:
        list[dict] — [{"role": "system"|"user"|"assistant", "content": "..."}, ...]
    """
    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    history = AiMessage.objects.filter(
        conversation=conversation
    ).order_by('id')
    for msg in history:
        messages.append({
            'role': msg.role,
            'content': msg.content,
        })
    return messages


def save_user_message(conversation, content):
    """保存用户消息到数据库。"""
    return AiMessage.objects.create(
        conversation=conversation,
        role='user',
        content=content,
    )


def save_assistant_message(conversation, content):
    """保存助手回复到数据库。"""
    return AiMessage.objects.create(
        conversation=conversation,
        role='assistant',
        content=content,
    )


def create_conversation_title(first_message):
    """从首条用户消息生成对话标题（截取前30字）。"""
    cleaned = first_message.strip().replace('\n', ' ')
    return cleaned[:30] + ('...' if len(cleaned) > 30 else '')


def serialize_conversation(conv):
    """序列化对话对象为字典。"""
    return {
        'conversation_code': conv.conversation_code,
        'title': conv.title or '新对话',
        'create_time': conv.create_time.isoformat() if conv.create_time else None,
        'update_time': conv.update_time.isoformat() if conv.update_time else None,
    }


def serialize_message(msg):
    """序列化消息对象为字典。"""
    return {
        'id': msg.id,
        'role': msg.role,
        'content': msg.content,
        'create_time': msg.create_time.isoformat() if msg.create_time else None,
    }


def _get_upload_root_dir():
    """获取上传文件存储的根目录绝对路径。"""
    return joint_path(str(settings.BASE_DIR), UPLOAD_ROOT_DIR_NAME)


def find_upload_file_path(file_id):
    """
    在上传目录下递归查找 file_id 对应的文件。

    参数:
        file_id — 上传时返回的唯一文件标识

    返回:
        str | None — 文件完整路径，找不到则返回 None
    """
    root = _get_upload_root_dir()
    if not exists(root):
        return None
    target_filename = f'{file_id}.json'
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if fname == target_filename:
                return joint_path(dirpath, fname)
    return None


def get_upload_file_content(file_id):
    """
    根据 file_id 读取上传文件的内容。

    参数:
        file_id — 上传时返回的唯一文件标识

    返回:
        tuple[str, str, str|None, str|None] — (文件内容字符串, 原始文件名, 文件类型, 上传时间ISO格式)

    异常:
        FileNotFoundError — 文件不存在
        ValueError — 文件内容非合法 JSON
    """
    file_path = find_upload_file_path(file_id)
    if file_path is None:
        raise FileNotFoundError(f'未找到上传文件: {file_id}')
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    # 从文件路径推断原始文件名（存储在父目录下，原始文件名记录在同目录的 meta 中）
    meta_path = file_path + '.meta'
    original_filename = f'{file_id}.json'
    file_type = None
    upload_time = None
    if exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as mf:
                meta = json.load(mf)
                original_filename = meta.get('original_filename', original_filename)
                file_type = meta.get('file_type')
                upload_time = meta.get('upload_time')
        except (json.JSONDecodeError, IOError):
            pass
    return content, original_filename, file_type, upload_time


def save_uploaded_file(file_id, original_filename, content, file_type=None, raw_bytes=None):
    """
    保存上传的文件到磁盘。

    参数:
        file_id — 唯一文件标识
        original_filename — 原始文件名
        content — 文件内容（字符串）
        file_type — 可选，文件类型标识（如 'Image', 'Excel', 'JSON'）
        raw_bytes — 可选，文件的原始二进制数据（用于 Excel 等需要原始文件的场景）

    返回:
        str — 保存后的文件完整路径
    """
    root = _get_upload_root_dir()
    today = date.today().strftime('%Y%m%d')
    upload_dir = joint_path(root, today)
    check_dirs(upload_dir)

    file_path = joint_path(upload_dir, f'{file_id}.json')
    meta_path = file_path + '.meta'

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    meta = {
        'original_filename': original_filename,
        'upload_time': datetime.now().isoformat(),
    }
    if file_type:
        meta['file_type'] = file_type

    # 对于 Excel 文件，额外保存原始二进制文件
    if raw_bytes and file_type == 'Excel':
        ext = os.path.splitext(original_filename)[1].lower()
        if ext not in ('.xlsx', '.xls'):
            ext = '.xlsx'
        excel_path = joint_path(upload_dir, f'{file_id}{ext}')
        with open(excel_path, 'wb') as bf:
            bf.write(raw_bytes)
        meta['excel_path'] = excel_path

    with open(meta_path, 'w', encoding='utf-8') as mf:
        json.dump(meta, mf, ensure_ascii=False)

    return file_path


def perform_file_compare(file_id_1, file_id_2):
    """
    比对两个上传的 JSON 配置文件。

    参数:
        file_id_1 — 第一个文件的 file_id
        file_id_2 — 第二个文件的 file_id

    返回:
        dict — 包含比对结果的字典
    """
    from base_utils.json_utils import compare_json_keys

    content1, filename1, file_type1, _ = get_upload_file_content(file_id_1)
    content2, filename2, file_type2, _ = get_upload_file_content(file_id_2)

    # 图片 OCR 内容不支持 JSON 结构比对
    if file_type1 == 'Image' or file_type2 == 'Image':
        image_file = filename1 if file_type1 == 'Image' else filename2
        raise ValueError(
            f'图片文件（{image_file}）为 OCR 识别内容，不支持 JSON 结构比对。'
            f'请上传 JSON 格式的配置文件进行比对。'
        )

    try:
        json1 = json.loads(content1)
    except json.JSONDecodeError as e:
        raise ValueError(f'文件 {filename1} 不是合法的 JSON: {e}')

    try:
        json2 = json.loads(content2)
    except json.JSONDecodeError as e:
        raise ValueError(f'文件 {filename2} 不是合法的 JSON: {e}')

    # 使用已有的 key 结构比对
    key_diff = compare_json_keys(json1, json2)

    # 递归比较共同 key 的 value 差异
    value_diffs = _compare_json_values(json1, json2)

    return {
        'filename_1': filename1,
        'filename_2': filename2,
        'key_diff': key_diff,
        'value_diffs': value_diffs,
        'is_identical': key_diff['is_identical'] and len(value_diffs) == 0,
    }


def _compare_json_values(obj1, obj2, path=''):
    """
    递归比较两个 JSON 对象的 value 差异。

    返回:
        list[dict] — [{"path": "root.xxx", "value_1": ..., "value_2": ...}, ...]
    """
    diffs = []

    if isinstance(obj1, dict) and isinstance(obj2, dict):
        all_keys = set(obj1.keys()) | set(obj2.keys())
        for key in sorted(all_keys):
            current_path = f'{path}.{key}' if path else key
            if key not in obj1:
                diffs.append({
                    'path': current_path,
                    'type': 'only_in_second',
                    'value_1': None,
                    'value_2': obj2[key],
                })
            elif key not in obj2:
                diffs.append({
                    'path': current_path,
                    'type': 'only_in_first',
                    'value_1': obj1[key],
                    'value_2': None,
                })
            else:
                v1, v2 = obj1[key], obj2[key]
                if isinstance(v1, (dict, list)) and isinstance(v2, (dict, list)):
                    diffs.extend(_compare_json_values(v1, v2, current_path))
                elif v1 != v2:
                    diffs.append({
                        'path': current_path,
                        'type': 'value_changed',
                        'value_1': v1,
                        'value_2': v2,
                    })
    elif isinstance(obj1, list) and isinstance(obj2, list):
        max_len = max(len(obj1), len(obj2))
        for i in range(max_len):
            current_path = f'{path}[{i}]'
            if i >= len(obj1):
                diffs.append({
                    'path': current_path,
                    'type': 'only_in_second',
                    'value_1': None,
                    'value_2': obj2[i],
                })
            elif i >= len(obj2):
                diffs.append({
                    'path': current_path,
                    'type': 'only_in_first',
                    'value_1': obj1[i],
                    'value_2': None,
                })
            else:
                v1, v2 = obj1[i], obj2[i]
                if isinstance(v1, (dict, list)) and isinstance(v2, (dict, list)):
                    diffs.extend(_compare_json_values(v1, v2, current_path))
                elif v1 != v2:
                    diffs.append({
                        'path': current_path,
                        'type': 'value_changed',
                        'value_1': v1,
                        'value_2': v2,
                    })
    else:
        if obj1 != obj2:
            diffs.append({
                'path': path,
                'type': 'value_changed',
                'value_1': obj1,
                'value_2': obj2,
            })

    return diffs


def format_comparison_result(comparison):
    """
    将比对结果格式化为可读文本，用于发送给 AI。

    参数:
        comparison — perform_file_compare 返回的 dict

    返回:
        str — 人类可读的比对结果文本
    """
    filename_1 = comparison.get('filename_1', '文件1')
    filename_2 = comparison.get('filename_2', '文件2')
    key_diff = comparison.get('key_diff', {})
    value_diffs = comparison.get('value_diffs', [])

    lines = [
        f'## 文件比对结果',
        f'',
        f'**{filename_1}** vs **{filename_2}**',
        f'',
        f'### Key 结构比对',
        f'- 是否一致: {"是" if key_diff.get("is_identical") else "否"}',
        f'- 文件1 total keys: {key_diff.get("total_keys_first", 0)}',
        f'- 文件2 total keys: {key_diff.get("total_keys_second", 0)}',
    ]

    only_in_first = key_diff.get('only_in_first', [])
    only_in_second = key_diff.get('only_in_second', [])

    if only_in_first:
        lines.append(f'- 仅在 {filename_1} 中存在的 key ({len(only_in_first)} 个):')
        for k in only_in_first[:30]:
            lines.append(f'  - {k}')
    if only_in_second:
        lines.append(f'- 仅在 {filename_2} 中存在的 key ({len(only_in_second)} 个):')
        for k in only_in_second[:30]:
            lines.append(f'  - {k}')

    if value_diffs:
        lines.append(f'')
        lines.append(f'### Value 差异 ({len(value_diffs)} 处)')
        # 限制输出前50条，避免上下文过长
        for diff in value_diffs[:50]:
            path = diff['path']
            dtype = diff['type']
            if dtype == 'only_in_first':
                lines.append(f'- [{path}] 仅在 {filename_1} 中存在: `{_truncate_value(diff["value_1"])}`')
            elif dtype == 'only_in_second':
                lines.append(f'- [{path}] 仅在 {filename_2} 中存在: `{_truncate_value(diff["value_2"])}`')
            elif dtype == 'value_changed':
                lines.append(
                    f'- [{path}] 值变更: '
                    f'`{_truncate_value(diff["value_1"])}` → `{_truncate_value(diff["value_2"])}`'
                )
        if len(value_diffs) > 50:
            lines.append(f'... 还有 {len(value_diffs) - 50} 处差异未列出')
    else:
        lines.append(f'')
        lines.append(f'### Value 差异: 无')

    lines.append(f'')
    lines.append(f'**总结**: {"两个文件完全一致" if comparison.get("is_identical") else "两个文件存在差异"}')

    return '\n'.join(lines)


def _truncate_value(value, max_len=80):
    """截断过长的值用于显示。"""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len] + '...'
    return s


def perform_hot_update_test(file_id, project, row_number=4):
    """
    执行热更测试：解析 AB 实验 Excel 文档，提取方案号，
    通过浏览器自动化在配置比对页面获取两个方案的 JSON 配置并对比。

    参数:
        file_id — 上传的 Excel 文件 ID
        project — 项目内部标识（如 ios_blcokblast_ab3.5_orth）
        row_number — 要解析的数据行号（默认第 4 行）

    返回:
        str — 格式化后的测试报告文本

    异常:
        FileNotFoundError — 文件不存在
        ValueError — 解析失败或方案不存在
        RuntimeError — 其他执行错误
    """
    import json as _json
    import os as _os
    import re as _re
    import openpyxl as _openpyxl

    # ======== 步骤1：查找并解析上传的 Excel 文件 ========
    # 注意：这些函数在同一模块中定义，直接调用

    file_path = find_upload_file_path(file_id)
    if file_path is None:
        raise FileNotFoundError(f'未找到上传文件: {file_id}')

    content, original_filename, file_type, _ = get_upload_file_content(file_id)
    if file_type and file_type.lower() == 'image':
        raise ValueError(f'图片文件不支持热更测试，请上传 Excel 格式的 AB 实验需求文档')

    # 尝试解析 Excel（file_path 是存储的 json 文件，需要读取原始文件名后再读取 Excel）
    excel_path = _find_original_excel(file_id)
    if excel_path is None:
        # 兜底：尝试从 content 中解析（如果 Excel 内容已存为文本）
        raise ValueError(
            f'无法解析 AB 实验文档。请确认上传的是 .xlsx 格式的 AB 实验需求 Excel 文件。'
            f'当前文件: {original_filename}'
        )

    # ======== 步骤2：从 Excel 中提取方案号 ========
    try:
        parsed = _parse_ab_excel(excel_path, row_number=row_number)
    except Exception as e:
        raise ValueError(f'解析 AB 实验文档失败: {e}')

    left_scheme = parsed.get('left_scheme', '')
    right_scheme = parsed.get('right_scheme', '')
    overview_text = parsed.get('overview_text', '')
    detail_text = parsed.get('detail_text', '')

    if not left_scheme:
        raise ValueError(
            f'未能从文档第 {row_number} 行的方案概述中提取到底板方案号（rv/fs 开头），'
            f'且已向上追溯到第4行仍未找到。'
            f'请确认该行或前面行的 C 列包含「【底板】rvxxx」格式的底板方案号。'
        )
    if not right_scheme:
        raise ValueError(
            f'未能从文档第 {row_number} 行的 A 列提取到原始方案编号，'
            f'且已向上追溯到第4行仍未找到。'
            f'请确认该行或前面行的 A 列包含原始方案编号。'
        )

    logger.info('热更测试解析结果: project=%s, left=%s, right=%s, row=%s',
                project, left_scheme, right_scheme, row_number)

    # ======== 步骤3：通过 API 方式获取两个方案的 JSON ========
    # 1) Playwright 无痕登录 → 获取 token
    # 2) 调用方案列表 API → 匹配左右方案号 → 找到方案路径
    # 3) 调用方案 JSON API → 获取两个方案的 JSON 配置
    import asyncio as _asyncio

    try:
        left_json, right_json = _asyncio.run(
            _fetch_json_via_api(project, left_scheme, right_scheme)
        )
    except Exception as e:
        raise RuntimeError(f'API 方式获取方案 JSON 失败: {e}')

    # ======== 步骤4：对比两个 JSON ========
    from base_utils.json_utils import compare_json_keys

    key_diff = compare_json_keys(left_json, right_json)
    raw_value_diffs = _compare_json_values(left_json, right_json)

    # ======== 步骤4.5：过滤 adwaynum 差异（仅方案号变了，不视为功能差异） ========
    # 分离 adwaynum 差异和功能性差异
    adwaynum_diffs = []
    functional_diffs = []
    for d in raw_value_diffs:
        path = d.get('path', '')
        if 'adwaynum' in path.lower():
            # 检查值是否匹配 left_scheme → right_scheme 的过渡
            v1 = str(d.get('value_1', ''))
            v2 = str(d.get('value_2', ''))
            if left_scheme in v1 and right_scheme in v2:
                adwaynum_diffs.append(d)
            else:
                # adwaynum 但值不匹配预期的方案号过渡，仍保留为功能差异
                functional_diffs.append(d)
        else:
            functional_diffs.append(d)

    value_diffs = functional_diffs  # 后续报告只显示功能性差异

    # ======== 步骤4.6：合并连续数组索引差异 + 过滤 unit_id 交换 ========
    value_diffs = _consolidate_array_diffs(value_diffs)
    value_diffs = _filter_unit_id_swaps(value_diffs)

    is_identical = key_diff.get('is_identical', False) and len(value_diffs) == 0

    # ======== 步骤5：生成结构化 JSON 数据（供 AI 网关逐条验证后输出报告） ========
    key_is_same = key_diff.get("is_identical", False)
    _is_pure_baseplate = _is_pure_baseplate_scheme(overview_text)
    fill_info = parsed.get('fill_info', '')

    # 构建结构化 JSON（供 AI 网关逐条验证后输出报告）
    report_data = {
        'project': project,
        'left_scheme': left_scheme,
        'right_scheme': right_scheme,
        'row_number': row_number,
        'fill_info': fill_info,
        'is_pure_baseplate': _is_pure_baseplate,
        'key_same': key_is_same,
        'key_count': f"{key_diff.get('total_keys_first', 0)} / {key_diff.get('total_keys_second', 0)}",
        'diff_count': len(value_diffs),
        'adwaynum_ignored': len(adwaynum_diffs),
        'diffs': [
            {
                'path': d['path'],
                'type': d['type'],
                'old': str(d.get('value_1', ''))[:300],
                'new': str(d.get('value_2', ''))[:300],
            }
            for d in value_diffs
        ],
        'overview_text': (overview_text or '')[:3000],
        'detail_text': (detail_text or '')[:3000],
    }
    return json.dumps(report_data, ensure_ascii=False, indent=2)


# ============================================================
# 热更测试报告增强：辅助函数
# ============================================================


def _auto_verify_diffs(overview_text, value_diffs, left_scheme, right_scheme):
    """
    自动分析方案概述，提取改动点并与差异列表比对，生成逐条验证结果。
    """
    if not overview_text or not value_diffs:
        return []

    import re as _re

    all_diff_text = ''
    for d in value_diffs:
        all_diff_text += f'{d.get("path", "")} {d.get("value_1", "")} {d.get("value_2", "")} '

    results = []

    # 规则1：搜索概述中的 case/配置名（gp_ecpm_xxx, al_1034, fs_xxx 等）
    case_patterns = [
        (r'gp_ecpm_\S+', 'case名'),
        (r'fs\d+', '方案号'),
        (r'al_\d+', '算法ID'),
        (r'service_version[：:]\s*(\S+)', 'service_version'),
    ]
    found_cases = set()
    for pattern, label in case_patterns:
        for m in _re.finditer(pattern, overview_text):
            case_name = m.group(1) if m.lastindex else m.group(0)
            if case_name in found_cases:
                continue
            found_cases.add(case_name)
            in_diff = case_name in all_diff_text
            results.append({
                'description': f'{label}: {case_name}',
                'passed': in_diff,
                'detail': '在新方案JSON中找到' if in_diff else f'在新方案JSON中未找到 {case_name}',
            })

    # 规则2：adunit/ID 相关改动
    adunit_patterns = [
        (r'(?:ID|adunit|ad_unit)[_]?(\d+)[：:\s]*禁用', 'autoretry禁用'),
        (r'(?:ID|adunit|ad_unit)[_]?(\d+)\*(\d+\.?\d*)', '底价乘数'),
        (r'(?:ID|adunit|ad_unit)[_]?(\d+)[：:].*?底价.*?\*(\d+\.?\d*)', '底价设置'),
        (r'(?:ID|adunit|ad_unit)[_]?(\d+)[：:\s]*(\d+)\s*s', '重试间隔'),
        (r'(?:ID|adunit|ad_unit)[_]?(\d+).*?\*\((\d+\.?\d*)\s*[,，]\s*(\d+\.?\d*)\)', '底价区间'),
        (r'(?:ID|adunit|ad_unit)[_]?(\d+)[：:].*?有展示前\*(\d+\.?\d*).*?有展示后\*(\d+\.?\d*)', '底价展示前后'),
    ]
    for pattern, label in adunit_patterns:
        for m in _re.finditer(pattern, overview_text, _re.IGNORECASE):
            ad_id = m.group(1)
            desc = m.group(0)[:80]
            search_terms = [f'ad_unit_{ad_id}', f'adunit{ad_id}']
            matched = any(
                any(t in str(d.get('path', '')).lower() for t in search_terms)
                for d in value_diffs
            )
            results.append({
                'description': f'ID{ad_id} {label}: {desc[:60]}',
                'passed': matched,
                'detail': f'ad_unit_{ad_id} 下{"找到" if matched else "未找到"}相关差异',
            })

    # 规则3：全局功能改动
    global_patterns = [
        (r'预估.*?ecpm|ecpm.*?预估', 'ecpm预估'),
        (r'corridor.*?地板|地板.*?corridor', 'corridor地板价'),
        (r'接口.*?超时|超时.*?接口|异常.*?底板|走底板', '超时/异常回退底板'),
    ]
    for pattern, label in global_patterns:
        if _re.search(pattern, overview_text, _re.IGNORECASE):
            related = any(
                'algorithm' in str(d.get('path', '')).lower()
                or 'al_' in str(d.get('value_2', ''))
                for d in value_diffs
            )
            results.append({
                'description': f'全局改动: {label}',
                'passed': related,
                'detail': '差异中存在相关变更' if related else '未找到相关差异',
            })

    # 去重
    seen = set()
    unique = []
    for r in results:
        key = r['description']
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _consolidate_array_diffs(diffs):
    """
    合并连续的数组索引差异。

    将 fail_retry_interval_time_list[0], [1], [2]... 合并为
    fail_retry_interval_time_list: [1,10,2,...] → [3,3,3,...]

    合并条件：同一 base_path 下 >= 3 个连续索引的同类变更。
    """
    import re as _re

    # 按 base_path 分组
    groups = {}  # base_path → [(index, diff), ...]
    standalone = []  # 非数组索引的 diff

    for d in diffs:
        path = d.get('path', '')
        # 匹配路径末尾的数组索引: xxx[N]
        m = _re.match(r'^(.+)\[(\d+)\]$', path)
        if m:
            base_path = m.group(1)
            idx = int(m.group(2))
            groups.setdefault(base_path, []).append((idx, d))
        else:
            standalone.append(d)

    if not groups:
        return diffs

    result = list(standalone)

    for base_path, indexed_diffs in groups.items():
        # 太少不值得合并
        if len(indexed_diffs) < 3:
            for _, d in indexed_diffs:
                result.append(d)
            continue

        indexed_diffs.sort(key=lambda x: x[0])
        indices = [x[0] for x in indexed_diffs]

        # 检查是否连续且类型一致
        types = set(d['type'] for _, d in indexed_diffs)

        if len(types) == 1 and len(indexed_diffs) >= 3:
            dtype = list(types)[0]

            if dtype == 'value_changed':
                # 检查是否所有值都变成同一个
                new_values = set(str(d['value_2']) for _, d in indexed_diffs)
                old_values = [str(d['value_1']) for _, d in indexed_diffs]

                if len(new_values) == 1:
                    # 所有索引变为同一值 → 简洁摘要
                    new_val = list(new_values)[0]
                    old_summary = f'[{",".join(old_values[:5])}{"..." if len(old_values) > 5 else ""}]'
                    result.append({
                        'path': f'{base_path}[{indices[0]}..{indices[-1]}]',
                        'type': 'value_changed',
                        'value_1': f'各索引原值不同: {old_summary}',
                        'value_2': f'统一改为: {new_val}',
                    })
                else:
                    # 各索引值不同 → 保留前几个作为示例
                    for _, d in indexed_diffs[:5]:
                        result.append(d)
                    if len(indexed_diffs) > 5:
                        result.append({
                            'path': f'{base_path}[...]',
                            'type': 'value_changed',
                            'value_1': f'共 {len(indexed_diffs)} 个索引值变更',
                            'value_2': '(详见上方明细)',
                        })
            elif dtype == 'only_in_first':
                # 数组在底板中更长
                removed_vals = [str(d['value_1']) for _, d in indexed_diffs]
                result.append({
                    'path': base_path,
                    'type': 'array_length_changed',
                    'value_1': f'底板 {indices[-1] + 1} 项 → 新方案 {indices[0]} 项（删除索引 [{indices[0]}..{indices[-1]}]，值: [{",".join(removed_vals[:5])}{"..." if len(removed_vals) > 5 else ""}]）',
                    'value_2': None,
                })
            elif dtype == 'only_in_second':
                # 数组在新方案中更长
                added_vals = [str(d['value_2']) for _, d in indexed_diffs]
                result.append({
                    'path': base_path,
                    'type': 'array_length_changed',
                    'value_1': None,
                    'value_2': f'底板 {indices[0]} 项 → 新方案 {indices[-1] + 1} 项（新增索引 [{indices[0]}..{indices[-1]}]，值: [{",".join(added_vals[:5])}{"..." if len(added_vals) > 5 else ""}]）',
                })
            else:
                for _, d in indexed_diffs:
                    result.append(d)
        else:
            # 类型不一致，保持原样
            for _, d in indexed_diffs:
                result.append(d)

    return result


def _filter_unit_id_swaps(diffs):
    """
    过滤 ad_unit_infos 之间的 unit_id 交换（A↔B 互换），不是真正的配置变更。

    检测模式：
      ad_unit_infos[X].unit_id: A → B
      ad_unit_infos[Y].unit_id: B → A
    这种成对的交换不视为功能差异，过滤掉。
    """
    import re as _re

    # 收集所有 unit_id 变更
    unit_id_changes = {}  # (old_id, new_id) → [path, ...]
    for d in diffs:
        path = d.get('path', '')
        if d['type'] == 'value_changed' and path.endswith('.unit_id'):
            key = (str(d['value_1']), str(d['value_2']))
            unit_id_changes.setdefault(key, []).append(path)

    if not unit_id_changes:
        return diffs

    # 检测交换对
    swap_paths = set()
    for (old_a, new_a), paths_a in unit_id_changes.items():
        # 查找反向：old_b==new_a 且 new_b==old_a
        reverse_key = (new_a, old_a)
        if reverse_key in unit_id_changes:
            # 确认是成对交换：两边数量相等
            if len(paths_a) == len(unit_id_changes[reverse_key]):
                swap_paths.update(paths_a)
                swap_paths.update(unit_id_changes[reverse_key])

    if not swap_paths:
        return diffs

    return [d for d in diffs if d.get('path', '') not in swap_paths]

# 纯底板方案检测：功能改动关键词列表
_PURE_BASEPLATE_FEATURE_KEYWORDS = [
    '重试', '底价', 'corridor', '地板价', '缓存', 'cache',
    'load', 'reload', '频次', 'frequency', 'bidding', 'b2b',
    '补位', '直连', '上报', '超时', 'timeout', '禁用', '启用',
    '新增', '增加', '删除', '移除', '修改', '调整', '变更',
    'segment', 'auto retry', 'retry',
]


def _is_pure_baseplate_scheme(overview_text):
    """
    判断方案概述是否描述了一个「纯底板方案」。

    纯底板方案：概述中仅有底板方案号引用，没有任何功能性改动描述。
    例如：「【底板】rv176685」或「基于rv159610」后面没有其它改动说明。

    返回:
        bool — True 表示纯底板方案（仅方案号不同，配置应一致）
    """
    if not overview_text:
        return True  # 空概述默认为纯底板

    text = overview_text

    # Step 1: 移除底板声明行（仅移除纯底板声明，保留后面的功能改动内容）
    import re as _re
    # 去掉【底板】xxx 行（独立行）
    text = _re.sub(r'【底板】[^\n]*', '', text)
    text = _re.sub(r'[（(]?底板[）)]?[^\n]*', '', text)
    # 去掉"基于rv/fxxxxx"底板引用（仅匹配方案号部分，不吞掉后面的+功能描述）
    # "基于rv159610" → 移除, "基于rv159610+重试逻辑" → 移除"基于rv159610"但保留"+重试逻辑"
    text = _re.sub(r'基于\s*[rf][sv]\d+', '', text)
    # 去掉其他方案号引用
    text = _re.sub(r'[rf][sv]\d+', '', text)
    # 去掉空白、特殊标点（但保留中文关键字）
    text = _re.sub(r'[\s\n\r]+', '', text)
    # 去掉开头的 + 、等连接符
    text = _re.sub(r'^[+＋、，,。.；;：:\s]+', '', text)
    text = text.strip()

    # Step 2: 检查剩余内容中是否包含功能改动关键词
    text_lower = text.lower()
    for keyword in _PURE_BASEPLATE_FEATURE_KEYWORDS:
        if keyword.lower() in text_lower:
            return False  # 发现了功能改动关键词 → 非纯底板方案

    return True  # 没有功能改动关键词 → 纯底板方案


def _diff_feature_label(path):
    """
    根据 diff path 生成人类可读的功能标签。

    例如：
      ad_unit_2.reload.reload_logic.retry_intervals → adunit2 → 重试间隔
      ad_unit_1.reload.reload_logic.rp_reload_value → adunit1 → 底价设置
      install_day_1.ad_unit_3.reload.reload_count → adunit3 → 重试次数

    返回:
        str — 可读标签，如 "adunit2 → 重试间隔"
    """
    path_lower = path.lower()

    # 识别 ad_unit
    ad_unit = None
    ad_match = re.search(r'ad_unit[_]?(\d+)', path_lower)
    if ad_match:
        ad_unit = f'adunit{ad_match.group(1)}'
    elif 'adunit' in path_lower:
        ad_match2 = _re_import.search(r'adunit(\d+)', path_lower)
        if ad_match2:
            ad_unit = f'adunit{ad_match2.group(1)}'

    # 识别功能分类
    feature = None
    if 'retry_interval' in path_lower:
        feature = '重试间隔'
    elif 'retry_count' in path_lower or ('retry' in path_lower and 'count' in path_lower):
        feature = '重试次数'
    elif 'auto_retry' in path_lower:
        feature = '自动重试开关'
    elif 'retry' in path_lower:
        feature = '重试逻辑'
    elif 'rp_reload' in path_lower or 'corridor' in path_lower or 'floor' in path_lower or 'base_price' in path_lower:
        feature = '底价/corridor'
    elif 'reload_count' in path_lower:
        feature = '重试次数'
    elif 'reload_time' in path_lower:
        feature = 'reload时间'
    elif 'reload_action' in path_lower:
        feature = 'reload动作'
    elif 'reload_type' in path_lower:
        feature = 'reload类型'
    elif 'cache' in path_lower:
        feature = '缓存设置'
    elif 'bidding' in path_lower or 'b2b' in path_lower:
        feature = 'bidding设置'
    elif 'frequency' in path_lower:
        feature = '频次控制'
    elif 'timeout' in path_lower:
        feature = '超时设置'
    elif 'load' in path_lower:
        feature = 'load逻辑'
    elif 'segment' in path_lower:
        feature = 'segment设置'

    if ad_unit and feature:
        return f'{ad_unit} → {feature}'
    elif ad_unit:
        return ad_unit
    elif feature:
        return feature
    return ''


def _diff_adunit_group(path):
    """
    根据 diff path 确定所属 ad_unit 分组。

    返回:
        str — 分组名，如 "ad_unit_2", "ad_unit_1", "其他"
    """
    path_lower = path.lower()
    ad_match = re.search(r'ad_unit[_]?(\d+)', path_lower)
    if ad_match:
        return f'ad_unit_{ad_match.group(1)}'
    if 'adunit' in path_lower:
        ad_match2 = re.search(r'adunit(\d+)', path_lower)
        if ad_match2:
            return f'ad_unit_{ad_match2.group(1)}'
    if 'install_day' in path_lower:
        return 'install_day 相关'
    return '其他'


def _label_value_diffs(value_diffs):
    """
    为每条 value diff 添加可读标签。

    返回:
        list[dict] — 每条 diff 增加 'label' 和 'adunit_group' 字段
    """
    labeled = []
    for d in value_diffs:
        path = d.get('path', '')
        labeled.append({
            **d,
            'label': _diff_feature_label(path),
            'adunit_group': _diff_adunit_group(path),
        })
    return labeled


def _group_diffs_by_adunit(labeled_diffs):
    """
    按 ad_unit 分组差异，并按 ad_unit 编号排序。

    返回:
        dict — {group_name: [diff_list], ...}
    """
    from collections import OrderedDict

    grouped = OrderedDict()
    # 按 ad_unit 编号排序
    def _sort_key(name):
        m = re.search(r'ad_unit_(\d+)', name)
        return int(m.group(1)) if m else 999

    for d in labeled_diffs:
        group = d.get('adunit_group', '其他')
        if group not in grouped:
            grouped[group] = []
        grouped[group].append(d)

    # 排序分组
    sorted_groups = OrderedDict()
    for name in sorted(grouped.keys(), key=_sort_key):
        sorted_groups[name] = grouped[name]

    # 每组内按 path 排序
    for name in sorted_groups:
        sorted_groups[name].sort(key=lambda x: x.get('path', ''))

    return sorted_groups


def _extract_modification_keywords(overview_text):
    """
    从方案概述文本中提取可验证的改动关键词列表。

    识别模式：
    - 「ID2：2s间隔重试」→ adunit2 重试间隔 2s
    - 「ID2：corridor地板价格=上次展示ecpm*0.8」→ adunit2 底价 corridor *0.8
    - 「adunit2禁用」→ adunit2 禁用
    - 「新增上报点位」→ 新增 上报

    返回:
        list[str] — 改动关键词描述列表
    """
    if not overview_text:
        return []

    keywords = []
    seen = set()

    # 规则1：匹配 "ID数字：描述内容" 模式
    id_pattern = re.findall(
        r'(?:ID|adunit|ad_unit)[_]?(\d+)[：:]\s*([^\n；;。]+)',
        overview_text, re.IGNORECASE
    )
    for ad_id, desc in id_pattern:
        desc_clean = desc.strip()[:80]
        key = f'adunit{ad_id}: {desc_clean}'
        if key not in seen:
            seen.add(key)
            keywords.append(key)

    # 规则2：匹配 "【xxx】描述" 模式
    bracket_pattern = re.findall(
        r'【([^】]+)】[^\n]{0,100}',
        overview_text
    )
    for tag in bracket_pattern:
        tag_clean = tag.strip()[:60]
        if tag_clean not in seen and not tag_clean.startswith('底板'):
            seen.add(tag_clean)
            keywords.append(f'【{tag_clean}】相关改动')

    # 规则3：匹配特定数值模式
    # "Ns间隔重试" → N秒重试
    interval_pattern = re.findall(
        r'(\d+)\s*s\s*(?:间隔)?\s*重试',
        overview_text
    )
    if interval_pattern:
        key = f'重试间隔: {", ".join(interval_pattern[:5])}s'
        if key not in seen:
            seen.add(key)
            keywords.append(key)

    # "*数字" 乘数模式（底价相关）
    multiplier_pattern = re.findall(
        r'\*(\d+\.?\d*)',
        overview_text
    )
    if multiplier_pattern:
        key = f'底价乘数: {", ".join(multiplier_pattern[:5])}'
        if key not in seen:
            seen.add(key)
            keywords.append(key)

    # 规则4：匹配功能关键词
    feature_map = {
        '缓存': '缓存逻辑',
        'cache': '缓存逻辑',
        '禁用': '禁用/关闭',
        'bidding': 'bidding设置',
        'b2b': 'b2b设置',
        '补位': '补位逻辑',
        '直连': '直连设置',
        '上报': '上报点位',
        'segment': 'segment设置',
        '频次': '频次控制',
        'load': 'load逻辑',
        'auto retry': 'auto retry设置',
    }
    for keyword, label in feature_map.items():
        if keyword.lower() in overview_text.lower():
            if label not in seen:
                seen.add(label)
                keywords.append(f'功能变更: {label}')

    return keywords


def _build_match_hints(mod_keywords, labeled_diffs):
    """
    为改动关键词与差异路径建立匹配提示。

    匹配逻辑：
    - 「adunit2」→ 匹配 adunit_group == 'ad_unit_2' 的 diff
    - 「重试间隔」→ 匹配 label 含「重试间隔」的 diff
    - 「底价」→ 匹配 label 含「底价」的 diff

    返回:
        list[dict] — [{"keyword": "adunit2: 2s间隔重试", "matched_path": "ad_unit_2...retry_intervals"}, ...]
    """
    if not mod_keywords or not labeled_diffs:
        return []

    hints = []
    for kw in mod_keywords:
        kw_lower = kw.lower()
        matched = []

        # adunit 匹配
        ad_match = re.search(r'adunit(\d+)', kw_lower)
        target_adunit = f'ad_unit_{ad_match.group(1)}' if ad_match else None

        for d in labeled_diffs:
            path = d.get('path', '')
            label = d.get('label', '')
            group = d.get('adunit_group', '')

            # 同 adunit + 同功能类型
            if target_adunit and group == target_adunit:
                # 进一步用功能关键词匹配
                if 'retry' in kw_lower or '重试' in kw:
                    if 'retry' in path.lower():
                        matched.append(path)
                elif '底价' in kw or 'corridor' in kw_lower or 'floor' in kw_lower:
                    if any(t in path.lower() for t in ['corridor', 'floor', 'base_price', 'rp_reload']):
                        matched.append(path)
                elif 'cache' in kw_lower or '缓存' in kw:
                    if 'cache' in path.lower():
                        matched.append(path)
                elif 'load' in kw_lower:
                    if 'load' in path.lower() or 'reload' in path.lower():
                        matched.append(path)
                elif 'bidding' in kw_lower or 'b2b' in kw_lower:
                    if 'bidding' in path.lower() or 'b2b' in path.lower():
                        matched.append(path)
                elif '禁用' in kw:
                    if 'auto_retry' in path.lower() or 'enable' in path.lower():
                        matched.append(path)
                else:
                    # 同 adunit 的 diff 都可能是相关改动
                    matched.append(path)
            elif not target_adunit:
                # 无特定 adunit，用标签匹配
                if label and any(t in label for t in ['重试', '底价', '缓存', 'load', 'bidding', '频次']):
                    if any(t in kw for t in ['重试', '底价', '缓存', 'load', 'bidding', '频次']):
                        matched.append(path)

        for mp in matched[:3]:  # 每个关键词最多3条匹配
            hints.append({'keyword': kw[:60], 'matched_path': mp})

    # 去重
    seen = set()
    unique_hints = []
    for h in hints:
        key = (h['keyword'], h['matched_path'])
        if key not in seen:
            seen.add(key)
            unique_hints.append(h)

    return unique_hints


def _find_original_excel(file_id):
    """
    找到上传的原始 Excel 文件路径。
    优先使用 meta 中记录的 excel_path（原始二进制），
    兜底使用 json_path（文本格式）。
    """
    json_path = find_upload_file_path(file_id)
    if json_path is None:
        return None

    # 检查 meta 文件是否记录了 excel_path
    import os as _os
    meta_path = json_path + '.meta'
    if _os.path.exists(meta_path):
        import json as _json
        try:
            with open(meta_path, 'r', encoding='utf-8') as mf:
                meta = _json.load(mf)
            excel_path = meta.get('excel_path', '')
            if excel_path and _os.path.exists(excel_path):
                return excel_path
        except Exception:
            pass

    return None


def _safe_str(v):
    """安全转换为字符串（去除首尾空白），用于 Excel 单元格值读取。"""
    return str(v).strip() if v is not None else ''


def _build_column_map(headers):
    """
    根据表头行构建列名→列索引的映射。

    表头可能包含这些列名：原始方案编号, 广告类型, 方案概述,
    abtest, 技术, 方案细节, 状态, 发起人, 备注, 上线地区, 数据依据
    """
    col_map = {}
    for i, h in enumerate(headers):
        h_clean = str(h).strip().replace('\n', '').replace(' ', '') if h is not None else ''
        if not h_clean:
            continue
        if '原始方案编号' in h_clean:
            col_map['原始方案编号'] = i
        elif '广告类型' in h_clean:
            col_map['广告类型'] = i
        elif '方案概述' in h_clean:
            col_map['方案概述'] = i
        elif 'abtest' in h_clean.lower():
            col_map['abtest'] = i
        elif '技术' in h_clean:
            col_map['技术'] = i
        elif '方案细节' in h_clean:
            col_map['方案细节'] = i
        elif '状态' in h_clean:
            col_map['状态'] = i
        elif '发起人' in h_clean:
            col_map['发起人'] = i
        elif '备注' in h_clean:
            col_map['备注'] = i
    return col_map


def _parse_ab_excel(file_path, row_number=4, sheet_name='All'):
    """
    解析 AB 实验 Excel 文档，提取方案号。支持前向填充：
    - 如果当前行 A 列为空（无新方案号），向上查找前一行
    - 如果当前行 C 列提取不到底板方案号，向上查找前一行
    - 如果当前行概述仅含「底板」无效内容，沿用前一行的概述

    内部函数，与 scripts/parse_hot_update_file.py 逻辑一致。
    支持通过表头检测自动映射列位置，降级到硬编码位置（A=0, C=2, F=5）。
    """
    import openpyxl as _openpyxl
    import re as _re

    wb = _openpyxl.load_workbook(file_path, data_only=True)

    if sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    row_idx = row_number - 1
    if row_idx < 0 or row_idx >= len(rows):
        raise ValueError(f'行号 {row_number} 超出范围（1-{len(rows)}）')

    # 检测表头行（第 3 行，0-based index 2）并构建列映射
    header_row_idx = 2  # 0-based，对应第 3 行
    headers = list(rows[header_row_idx]) if header_row_idx < len(rows) else []
    col_map = _build_column_map(headers)

    # 方案号正则
    scheme_pattern = _re.compile(r'(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])')
    base_rules = [
        _re.compile(r'【底板】[^\n]*?(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])'),
        _re.compile(r'[（(]?底板[）)]?[^\n]*?(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])'),
        _re.compile(r'基于[^\n]*?(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])'),
    ]

    def _extract_left_scheme(text):
        """从文本中提取底板方案号。"""
        if not text:
            return ''
        for rule in base_rules:
            match = rule.search(text)
            if match:
                return match.group(1)
        all_s = scheme_pattern.findall(text)
        return all_s[0] if all_s else ''

    def _extract_all_schemes(text):
        """从文本中提取所有方案号。"""
        result = []
        if text:
            for m in scheme_pattern.finditer(text):
                s = m.group(0)
                if s not in result:
                    result.append(s)
        return result

    def _is_overview_empty(text):
        """判断概述文本是否仅为底板声明（无实际改动内容）。"""
        if not text or not text.strip():
            return True
        cleaned = _re.sub(r'【底板】[^\n]*', '', text)
        cleaned = _re.sub(r'[（(]?底板[）)]?[^\n]*', '', cleaned)
        cleaned = cleaned.strip()
        return not cleaned

    def _read_row_cells(r_idx):
        """读取指定行索引的单元格值。"""
        r = rows[r_idx]
        rs = _safe_str(r[col_map.get('原始方案编号', 0)]) if len(r) > col_map.get('原始方案编号', 0) else ''
        ot = _safe_str(r[col_map.get('方案概述', 2)]) if len(r) > col_map.get('方案概述', 2) else ''
        dt = _safe_str(r[col_map.get('方案细节', 5)]) if len(r) > col_map.get('方案细节', 5) else ''
        return rs, ot, dt

    # 读取当前行
    right_scheme, overview_text, detail_text = _read_row_cells(row_idx)
    left_scheme = _extract_left_scheme(overview_text)

    # ======== 前向填充 ========
    # 规则：从当前行向上查找，直到找到有效值为止（数据行从第4行开始，即 row_idx >= 3）
    searched_rows = [row_idx]
    search_idx = row_idx - 1
    data_start_idx = 3  # 第4行（0-based index 3）

    # 如果当前行概述为空/仅底板 → 需要从前面行寻找实际概述和底板方案号
    if _is_overview_empty(overview_text):
        while search_idx >= data_start_idx:
            searched_rows.append(search_idx)
            _, prev_overview, _ = _read_row_cells(search_idx)
            prev_left = _extract_left_scheme(prev_overview)
            if not _is_overview_empty(prev_overview):
                # 找到有内容的概述
                overview_text = prev_overview
                if not left_scheme:
                    left_scheme = prev_left
                break
            search_idx -= 1

    # 如果底板方案号仍为空 → 继续向上找
    if not left_scheme:
        search_idx = row_idx - 1
        while search_idx >= data_start_idx:
            _, prev_overview, _ = _read_row_cells(search_idx)
            prev_left = _extract_left_scheme(prev_overview)
            if prev_left:
                left_scheme = prev_left
                searched_rows.append(search_idx)
                break
            search_idx -= 1

    # 如果新方案号为空 → 向上找前一行
    if not right_scheme:
        search_idx = row_idx - 1
        while search_idx >= data_start_idx:
            prev_rs, _, _ = _read_row_cells(search_idx)
            if prev_rs:
                right_scheme = prev_rs
                searched_rows.append(search_idx)
                break
            search_idx -= 1

    # 记录��向填充信息（用于报告）
    fill_info = ''
    if len(searched_rows) > 1:
        fill_info = f'（前向填充：第{row_number}行 → 追溯到第{searched_rows[-1] + 1}行）'

    all_schemes_in_overview = _extract_all_schemes(overview_text)

    return {
        'right_scheme': right_scheme,
        'left_scheme': left_scheme,
        'all_schemes_in_overview': all_schemes_in_overview,
        'overview_text': overview_text,
        'detail_text': detail_text,
        'fill_info': fill_info,
    }


async def _login_and_get_token():
    """
    Playwright 无痕登录，获取 token。使用模块级缓存，多次调用只登录一次。

    返回:
        str — admin_token
    """
    global _cached_token
    if _cached_token:
        logger.info('API方式: 使用缓存的 token（%d 字符），跳过登录', len(_cached_token))
        return _cached_token

    from playwright.async_api import async_playwright
    from urllib.parse import urlparse as _urlparse

    cfg = load_config()
    frontend_url = cfg.get('config_compare_page_url', 'http://localhost:5173')
    parsed = _urlparse(frontend_url)

    token = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        page = await context.new_page()
        page.set_default_timeout(15000)

        try:
            login_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 5173}/"
            logger.info('API方式: 打开登录页 %s', login_url)
            await page.goto(login_url, wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(2000)

            # 自动登录
            login_input = page.locator('input[placeholder*="用户名"]')
            if await login_input.is_visible(timeout=3000):
                logger.info('API方式: 检测到登录页，自动登录...')
                await login_input.click()
                await login_input.fill('auto_user')
                pwd_input = page.locator('input[placeholder*="密码"]').first
                await pwd_input.click()
                await pwd_input.fill('auto_user')
                login_btn = page.locator('button:has-text("登"), button:has-text("登录")').first
                await login_btn.click()
                await page.wait_for_timeout(3000)

            # 从 localStorage 提取 token
            token = await page.evaluate('() => localStorage.getItem("admin_token")')
            if not token:
                await page.wait_for_timeout(3000)
                token = await page.evaluate('() => localStorage.getItem("admin_token")')
            if not token:
                raise RuntimeError(
                    '登录后未获取到 token，请检查自动登录是否成功（用户名/密码是否正确）'
                )
            logger.info('API方式: 登录成功，token 已获取 (%d 字符)', len(token))
        finally:
            await context.close()
            await browser.close()

    _cached_token = token
    return token


def clear_cached_token():
    """清除缓存的登录 token。"""
    global _cached_token
    _cached_token = None
    logger.info('API方式: 已清除缓存的 token')


async def _fetch_json_via_api(project, left_scheme, right_scheme, token=None):
    """
    通过 API 方式获取两个方案的 JSON 配置：
    1. 使用传入的 token（或调用 _login_and_get_token 登录获取）
    2. 调用方案列表 API → 匹配左右方案号 → 找到完整方案路径
    3. 调用方案 JSON API → 获取两个方案的 JSON 配置
    """
    import requests as _requests
    from urllib.parse import urlparse as _urlparse

    if token is None:
        token = await _login_and_get_token()

    cfg = load_config()
    frontend_url = cfg.get('config_compare_page_url', 'http://localhost:5173')
    parsed = _urlparse(frontend_url)
    api_base = f"{parsed.scheme}://{parsed.hostname}:8000"
    logger.info('API方式: api_base=%s, project=%s, left=%s, right=%s',
                api_base, project, left_scheme, right_scheme)

    # ======== Step 2: 调用方案列表 API ========
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    list_url = f"{api_base}/api/operate_tool/git_config_diff/get_adwaynum_file/"
    logger.info('API方式: 调用方案列表 API: %s?project_name=%s', list_url, project)
    resp = _requests.get(list_url, params={
        'project_name': project,
        'business_v': '',
        'timeslot': 'left_time_slot_0',
    }, headers=headers, timeout=60)
    resp.raise_for_status()
    list_data = resp.json()
    if list_data.get('code') != 0:
        raise RuntimeError(f'方案列表 API 返回错误 (code={list_data.get("code")}): {list_data.get("message")}')
    files = list_data['data'].get('adwaynum_files', [])
    logger.info('API方式: 方案列表共 %d 条', len(files))

    # ======== Step 3: 在方案列表中匹配左右方案号 ========
    left_matched = None
    right_matched = None
    for f in files:
        name = f if isinstance(f, str) else str(f)
        if not left_matched and left_scheme.lower() in name.lower():
            left_matched = name
            logger.info('API方式: 左侧底板方案匹配成功: %s', name)
        if not right_matched and right_scheme.lower() in name.lower():
            right_matched = name
            logger.info('API方式: 右侧新方案匹配成功: %s', name)
        if left_matched and right_matched:
            break

    if not left_matched:
        raise RuntimeError(
            f'在方案列表中未找到底板方案「{left_scheme}」（列表共 {len(files)} 个方案），请确认方案号正确'
        )
    if not right_matched:
        raise RuntimeError(
            f'在方案列表中未找到新方案「{right_scheme}」（列表共 {len(files)} 个方案），请确认方案号正确'
        )

    # ======== Step 4: 调用方案 JSON API 获取左右两侧 JSON ========
    def _get_scheme_json(adwaynum, label):
        url = f"{api_base}/api/operate_tool/git_config_diff/get_adwaynum_json_2/"
        logger.info('API方式: 获取%s JSON: %s?adwaynum=%s', label, url, adwaynum)
        resp = _requests.get(url, params={
            'project_name': project,
            'business_v': '',
            'adwaynum': adwaynum,
            'timeslot': 'left_time_slot_0',
        }, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') != 0:
            raise RuntimeError(f'{label}方案 JSON API 返回错误 (code={data.get("code")}): {data.get("message")}')
        result = data['data'].get('adwaynum_json', {})
        logger.info('API方式: %s JSON 获取完成, keys=%d', label,
                     len(result) if isinstance(result, dict) else 0)
        return result

    left_json = _get_scheme_json(left_matched, '左侧')
    right_json = _get_scheme_json(right_matched, '右侧')

    return left_json, right_json


def parse_tool_call(reply_text):
    """
    从 AI 回复文本中解析第一条工具调用指令。

    参数:
        reply_text — AI 回复的完整文本

    返回:
        tuple[str | None, dict | None] — (工具名称, 参数字典)
        如果没有找到工具调用则返回 (None, None)
    """
    pattern = r'\[TOOL_CALL:(\w+)\]\s*(\{[^}]*\})\s*\[/TOOL_CALL\]'
    match = re.search(pattern, reply_text, re.DOTALL)
    if not match:
        return None, None
    tool_name = match.group(1)
    try:
        params = json.loads(match.group(2))
    except json.JSONDecodeError:
        logger.warning('TOOL_CALL JSON 解析失败: %s', match.group(2))
        return None, None
    return tool_name, params


def parse_all_tool_calls(reply_text):
    """
    从 AI 回复文本中解析所有工具调用指令（支持一条消息中的多个 TOOL_CALL）。

    参数:
        reply_text — AI 回复的完整文本

    返回:
        list[tuple[str, dict]] — [(工具名称, 参数字典), ...]
        如果没有找到任何工具调用则返回空列表 []
    """
    pattern = r'\[TOOL_CALL:(\w+)\]\s*(\{[^}]*\})\s*\[/TOOL_CALL\]'
    results = []
    for match in re.finditer(pattern, reply_text, re.DOTALL):
        tool_name = match.group(1)
        try:
            params = json.loads(match.group(2))
            results.append((tool_name, params))
        except json.JSONDecodeError:
            logger.warning('TOOL_CALL JSON 解析失败: %s', match.group(2))
    return results


def remove_tool_call_from_reply(reply_text):
    """
    从 AI 回复中移除 TOOL_CALL 块，返回干净的文本。

    参数:
        reply_text — 含 TOOL_CALL 的完整回复

    返回:
        str — 移除 TOOL_CALL 后的文本
    """
    pattern = r'\n?\[TOOL_CALL:\w+\]\s*\{[^}]*\}\s*\[/TOOL_CALL\]'
    return re.sub(pattern, '', reply_text).strip()
