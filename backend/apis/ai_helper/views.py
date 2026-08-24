"""
AI助手 API 接口层：对话列表、创建/删除对话、发送消息、文件上传与比对。

支持两种模型后端：
- gateway（默认）：远端智能体网关（stargate）
- local：本地 Ollama 模型
"""
import json
import logging
import os
import uuid

import openpyxl
from PIL import Image

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.ai_helper.gateway import call_agent_gateway, load_config as load_gateway_config
from apps.llm.gateway import call_ollama_chat, list_ollama_models
from apps.ai_helper.models import AiConversation, AiMessage
from apps.ai_helper.tools import build_system_prompt, PROJECT_NAME_ALIASES
from apps.ai_helper.views import (
    MAX_UPLOAD_SIZE,
    ALLOWED_EXTENSIONS,
    _find_original_excel,
    build_context_messages,
    clear_cached_token,
    clear_conversation_messages,
    create_conversation_title,
    find_upload_file_path,
    format_comparison_result,
    get_or_create_conversation,
    get_upload_file_content,
    get_user_conversations,
    parse_all_tool_calls,
    parse_tool_call,
    perform_file_compare,
    perform_hot_update_test,
    remove_tool_call_from_reply,
    save_assistant_message,
    save_uploaded_file,
    save_user_message,
    serialize_conversation,
    serialize_message,
    soft_delete_all_conversations,
    soft_delete_conversation,
)
from apps.users.decorators import require_valid_token
from base_utils.image_base import ImageBase
from base_utils.secrecy_base import base64_en
from apis.ocr.views import _extract_detected_text_from_tencent_json

logger = logging.getLogger(__name__)


def _parse_body(request):
    """解析 JSON 请求体。"""
    try:
        return json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return None


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def conversation_list(request):
    """获取当前用户的对话列表。"""
    user = request.z_user
    conversations = get_user_conversations(user)
    return JsonResponse({
        'code': 0,
        'data': [serialize_conversation(c) for c in conversations],
    })


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def conversation_create(request):
    """
    生成新的对话编码（不创建数据库记录）。

    对话记录仅在用户首次发送消息时由 chat 接口创建。
    仅点开面板不发送消息不会留下空的会话记录。
    """
    from apps.ai_helper.views import generate_conversation_code
    conv_code = generate_conversation_code()
    return JsonResponse({
        'code': 0,
        'message': '成功',
        'data': {
            'conversation_code': conv_code,
            'title': '新对话',
            'create_time': None,
            'update_time': None,
        },
    })


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def conversation_delete(request, conversation_code):
    """软删除指定对话。"""
    user = request.z_user
    conv = soft_delete_conversation(conversation_code, user)
    if conv is None:
        return JsonResponse({'code': 404, 'message': '对话不存在或已删除'}, status=404)
    return JsonResponse({'code': 0, 'message': '已删除'})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def conversation_clear_messages(request, conversation_code):
    """清空指定对话的所有消息记录。"""
    user = request.z_user
    count = clear_conversation_messages(conversation_code, user)
    if count == 0:
        conv_exists = AiConversation.objects.filter(
            conversation_code=conversation_code,
            user=user,
            is_deleted=False,
        ).exists()
        if not conv_exists:
            return JsonResponse({'code': 404, 'message': '对话不存在'}, status=404)
    return JsonResponse({
        'code': 0,
        'message': f'已清空 {count} 条消息',
        'data': {'deleted_count': count},
    })


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def conversation_clear_all(request):
    """清空当前用户的所有对话（软删除）。"""
    user = request.z_user
    count = soft_delete_all_conversations(user)
    return JsonResponse({
        'code': 0,
        'message': f'已清空 {count} 个对话',
        'data': {'deleted_count': count},
    })


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def conversation_messages(request, conversation_code):
    """获取指定对话的消息历史。"""
    user = request.z_user
    try:
        conv = AiConversation.objects.get(
            conversation_code=conversation_code,
            user=user,
            is_deleted=False,
        )
    except AiConversation.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '对话不存在'}, status=404)
    messages = build_context_messages(conv)
    return JsonResponse({'code': 0, 'data': messages})


# ── 报告生成专用 System Prompt（不含 TOOL_CALL 指令，避免 AI 误判） ──
_REPORT_SYSTEM_PROMPT = """你是一个 AB 实验配置比对分析助手。你的任务是：根据提供的热更测试数据和 AB 实验文档内容，生成一份详细的逐条验证报告。

## 报告格式

请按以下结构输出：

### 📊 基本信息
用表格展示：项目、底板方案、新方案、Key结构是否一致、差异总数

### 🔕 已忽略的 adwaynum 差异
列出数量和原因（仅方案号从底板变更为新方案，不视为功能差异）

### 🔍 逐条验证
对每条功能差异**必须**使用以下三种状态之一标记：

| 图标 | 状态 | 判断条件 |
|------|------|---------|
| ✅ AI测试通过 | 通过 | 差异内容能在「📄 文档内容」中找到对应的改动描述 |
| ⚠️ 需人工确认 | 待确认 | 无法在文档中找到对应描述，或描述模糊无法确定 |
| ❌ AI测试不通过 | 不通过 | 差异内容与文档描述矛盾，或纯底板方案出现异常差异 |

每条差异的展示格式：
```
N. `差异路径`
   > 变更: old → new（或 仅底板/新方案存在）
   > 📄 文档描述: （引用原文）
   > ✅ AI测试通过  /  ⚠️ 需人工确认  /  ❌ AI测试不通过
```

### 🎯 测试结论
- 汇总统计：✅ 通过 X 条 / ⚠️ 待确认 Y 条 / ❌ 不通过 Z 条
- 给出整体结论（通过 / 不通过 / 需人工确认）

## 重要规则
1. 直接输出报告，禁止使用任何工具调用格式（如 [TOOL_CALL:...]）
2. 不要输出原始 JSON 或 diffs 列表原文
3. 用中文回复
4. 纯底板方案（is_pure_baseplate=true）的任何差异都应标记为 ❌ AI测试不通过
5. 数组索引差异（如 fail_retry_interval_time_list[0],[1]...[9]）应合并描述，不要逐条列出
6. 每个差异必须且只能有一个状态标记（✅ ⚠️ ❌ 三者之一）
7. unit_id 交换（A↔B 互换）不视为功能差异，标记为 ✅ AI测试通过"""


def _execute_single_hot_update_test(tool_params, reply, context_messages):
    """
    执行单条热更测试并调用 AI 网关生成报告。

    使用「隔离上下文」策略：为报告生成构建独立的上下文，
    不包含主对话的 system prompt（以免 TOOL_CALL 指令干扰 AI）。

    参数:
        tool_params — dict，包含 project, file_id, row_number
        reply — AI 的原始回复文本（未使用，保留接口兼容）
        context_messages — 当前对话上下文消息列表（未使用，保留接口兼容）

    返回:
        str — 最终的 AI 报告或错误信息
    """
    import json as _json

    try:
        file_id = tool_params.get('file_id', '')
        project = tool_params.get('project', '')
        row_number = int(tool_params.get('row_number', 4))
        if not file_id or not project:
            raise ValueError('缺少 file_id 或 project 参数')

        # ── 步骤1：执行配置比对，获取结构化 JSON ──
        tool_result_text = perform_hot_update_test(file_id, project, row_number)
        logger.info('热更测试完成: project=%s, file_id=%s, row=%s',
                    project, file_id, row_number)

        # ── 步骤2：解析 JSON，提取关键字段 ──
        data = _json.loads(tool_result_text)
        left_scheme = data.get('left_scheme', '?')
        right_scheme = data.get('right_scheme', '?')
        overview_text = data.get('overview_text', '')
        detail_text = data.get('detail_text', '')
        diffs = data.get('diffs', [])
        key_same = data.get('key_same', False)
        key_count = data.get('key_count', '?/?')
        diff_count = data.get('diff_count', 0)
        adwaynum_ignored = data.get('adwaynum_ignored', 0)
        is_pure_baseplate = data.get('is_pure_baseplate', False)
        fill_info = data.get('fill_info', '')

        # ── 步骤3：将差异列表 + 文档内容组合，构建报告生成提示 ──
        diffs_text = _format_diffs_for_ai(diffs)
        doc_context = _build_doc_context(overview_text, detail_text)

        report_prompt = (
            f'## 📊 热更测试数据\n'
            f'- 项目: {project}\n'
            f'- 行号: 第 {row_number} 行\n'
            f'- 底板方案(左侧): {left_scheme}\n'
            f'- 新方案(右侧): {right_scheme}\n'
            f'- Key结构: {"✅一致" if key_same else "❌不一致"} ({key_count})\n'
            f'- 功能差异: {diff_count} 处\n'
            f'- 已忽略adwaynum: {adwaynum_ignored} 处\n'
            f'- 纯底板方案: {"是" if is_pure_baseplate else "否"}\n'
            f'{f"- 填充信息: {fill_info}" if fill_info else ""}\n'
            f'\n'
            f'## 🔍 JSON 功能差异列表\n'
            f'{diffs_text}\n'
            f'\n'
            f'{doc_context}\n'
            f'\n'
            f'请根据以上数据，结合文档中描述的预期改动，生成逐条验证报告。'
        )

        # ── 步骤4：构建隔离的报告生成上下文 ──
        # 关键：使用专用的 _REPORT_SYSTEM_PROMPT，完全隔离主对话的 TOOL_CALL 指令
        report_messages = [
            {'role': 'system', 'content': _REPORT_SYSTEM_PROMPT},
            {'role': 'user', 'content': report_prompt},
        ]

        # ── 步骤5：调用 AI 网关生成报告 ──
        logger.info('调用AI网关生成报告(隔离上下文), 消息条数: %d, 差异数: %d',
                    len(report_messages), diff_count)
        try:
            ai_report = call_agent_gateway(report_messages)
        except RuntimeError:
            ai_report = None

        logger.info('AI 报告内容(前300字): %s', (ai_report or '')[:300])

        # ── 步骤6：质量验证 ──
        MIN_REPORT_LENGTH = 50
        if ai_report and len(ai_report) >= MIN_REPORT_LENGTH:
            return ai_report
        else:
            logger.warning(
                'AI报告生成失败(len=%s)，使用简洁摘要',
                len(ai_report) if ai_report else 0,
            )
            return _build_simple_summary(
                project, row_number, left_scheme, right_scheme,
                key_same, key_count, diff_count, adwaynum_ignored,
                is_pure_baseplate, diffs, fill_info,
            )

    except FileNotFoundError as e:
        logger.error('执行 hot_update_test 文件未找到: %s', e)
        return (
            f'❌ 配置比对执行失败\n\n'
            f'**错误原因**：{e}\n\n'
            f'**修复建议**：上传的文档可能已过期，请重新上传 Excel 文档后再试。'
        )
    except ValueError as e:
        logger.error('执行 hot_update_test 参数错误: %s', e)
        return (
            f'❌ 配置比对执行失败\n\n'
            f'**错误原因**：{e}\n\n'
            f'**修复建议**：请确认文档格式正确、方案号有效，或联系管理员。'
        )
    except RuntimeError as e:
        logger.error('执行 hot_update_test 运行时错误: %s', e)
        error_msg = str(e)
        if 'Executable doesn\'t exist' in error_msg or 'playwright install' in error_msg:
            suggestion = '浏览器驱动未安装，请管理员在服务器上执行：playwright install chromium'
        elif '目录不存在' in error_msg:
            suggestion = 'git 配置仓库未克隆或路径不正确，请联系管理员同步 hsabtest_config 仓库。'
        elif '未找到' in error_msg and '方案' in error_msg:
            suggestion = '方案号在配置页面中未找到，请确认方案号正确。如果页面刚选择项目，请等待 loading 完成后再试。'
        elif '页面' in error_msg and '下拉' in error_msg:
            suggestion = '项目名称在页面下拉列表中未找到，请确认项目名称拼写与页面一致。'
        elif '期数' in error_msg or 'business_v' in error_msg:
            suggestion = '无法获取项目期数，请确认 git 仓库��同步且项目配置正确。'
        elif '页面' in error_msg and ('超时' in error_msg or '无法访问' in error_msg):
            suggestion = '配置比对页面无法访问，请检查 config/ai_helper_config.json 中 config_compare_page_url 是否正确。'
        else:
            suggestion = '请确认配置比对页面可正常访问，方案号正确，或联系管理员。'
        return (
            f'❌ 配置比对执行失败\n\n'
            f'**错误原因**：{error_msg}\n\n'
            f'**修复建议**：{suggestion}\n\n'
            f'> 详细日志请查看服务器后台。'
        )
    except Exception as e:
        logger.exception('执行 hot_update_test 未预期异常: %s', e)
        error_msg = str(e)
        if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
            suggestion = '请求超时，可能是配置比对页面响应慢。请稍后重试，或检查服务器网络与 config_compare_page_url 配置。'
        elif 'connect' in error_msg.lower() or 'refused' in error_msg.lower():
            suggestion = '无法连接配置比对页面，请检查 config/ai_helper_config.json 中 config_compare_page_url 是否正确，以及目标服务是否启动。'
        elif 'executable' in error_msg.lower() or 'playwright' in error_msg.lower() or 'chromium' in error_msg.lower() or 'browser' in error_msg.lower():
            suggestion = '浏览器驱动未安装或异常，请管理员在服务器上执行：playwright install chromium'
        else:
            suggestion = '请稍后重试。如持续失败，请联系管理员检查服务器日志。'
        return (
            f'❌ 配置比对执行失败\n\n'
            f'**错误类型**：{type(e).__name__}\n'
            f'**错误原因**：{error_msg[:300]}\n\n'
            f'**修复建议**：{suggestion}\n\n'
            f'> 详细日志请查看服务器后台。'
        )


def _format_diffs_for_ai(diffs):
    """将差异列表格式化为 AI 易于理解的文本（长值自动截断）。"""
    if not diffs:
        return '(无功能差异)'

    lines = []
    for i, d in enumerate(diffs, 1):
        path = d.get('path', '?')
        dtype = d.get('type', '?')
        old_val = _truncate_diff_value(d.get('old', ''))
        new_val = _truncate_diff_value(d.get('new', ''))

        if dtype == 'value_changed':
            lines.append(f'{i}. [{path}] 变更: {old_val} → {new_val}')
        elif dtype == 'only_in_first':
            lines.append(f'{i}. [{path}] 仅底板存在: {old_val}')
        elif dtype == 'only_in_second':
            lines.append(f'{i}. [{path}] 仅新方案存在: {new_val}')
        elif dtype == 'array_length_changed':
            lines.append(f'{i}. [{path}] 数组长度变化: {old_val or new_val}')
        else:
            lines.append(f'{i}. [{path}] {dtype}: old={old_val}, new={new_val}')

    return '\n'.join(lines)


def _truncate_diff_value(val, max_len=120):
    """截断过长的 diff 值（如整段 JSON），避免撑爆 AI 上下文。"""
    s = str(val)
    if len(s) <= max_len:
        return s
    # 如果是 dict/list 的字符串表示，提取关键信息
    if s.startswith('{') and s.endswith('}'):
        # 提取 dict 的 keys 作为摘要
        try:
            import json as _json
            d = _json.loads(s.replace("'", '"'))
            keys = list(d.keys())[:8]
            summary = ', '.join(f'{k}={_truncate_diff_value(str(d[k]), 40)}' for k in keys)
            more = f' ...(+{len(d) - 8} keys)' if len(d) > 8 else ''
            return f'{{{summary}{more}}}'
        except Exception:
            pass
    if s.startswith('[') and s.endswith(']'):
        return s[:max_len] + f'...](len={len(s)})'
    return s[:max_len] + '...'


def _build_doc_context(overview_text, detail_text):
    """构建文档上下文文本，供 AI 参考匹配。"""
    parts = []
    if overview_text:
        parts.append(f'## 📄 文档内容 — 方案概述\n{overview_text}')
    if detail_text:
        parts.append(f'## 📄 文档内容 — 方案细节\n{detail_text}')
    if not parts:
        return '## 📄 文档内容\n(文档中无额外描述)'
    return '\n\n'.join(parts)


def _build_simple_summary(project, row_number, left_scheme, right_scheme,
                          key_same, key_count, diff_count, adwaynum_ignored,
                          is_pure_baseplate, diffs, fill_info):
    """
    当 AI 网关无法生成报告时的简洁兜底摘要。
    仅展示结构化数据，不做代码级智能匹配。
    """
    lines = [
        f'## 📊 热更测试报告 — 第 {row_number} 行',
        '',
        f'| 项目 | 底板方案 | 新方案 | Key结构 | 功能差异 |',
        f'|------|----------|--------|---------|----------|',
        f'| {project} | {left_scheme} | {right_scheme} | {"✅一致" if key_same else "❌不一致"} ({key_count}) | {diff_count}处 |',
    ]

    if fill_info:
        lines.append(f'\n📌 {fill_info}')

    if is_pure_baseplate and diff_count == 0:
        lines.append(f'\n📌 **纯底板方案**：仅方案号不同，配置完全一致。')
    elif is_pure_baseplate and diff_count > 0:
        lines.append(f'\n⚠️ **纯底板方案异常**：仅方案号不同但存在 {diff_count} 处差异。')

    if adwaynum_ignored > 0:
        lines.append(f'\n### 🔕 已忽略的 adwaynum 差异')
        lines.append(f'共 **{adwaynum_ignored}** 处（仅方案号从 `{left_scheme}` 变更为 `{right_scheme}`）。')

    if diffs:
        lines.append(f'\n### 🔍 差异列表（共 {diff_count} 处）')
        lines.append('')
        for i, d in enumerate(diffs, 1):
            path = d.get('path', '?')
            dtype = d.get('type', '?')
            old_val = _truncate_diff_value(d.get('old', ''))
            new_val = _truncate_diff_value(d.get('new', ''))

            lines.append(f'**{i}.** `{path}`')
            if dtype == 'value_changed':
                lines.append(f'   > 变更: `{old_val}` → `{new_val}`')
            elif dtype == 'only_in_first':
                lines.append(f'   > 仅底板存在: `{old_val}`')
            elif dtype == 'only_in_second':
                lines.append(f'   > 仅新方案存在: `{new_val}`')
            elif dtype == 'array_length_changed':
                lines.append(f'   > {old_val or new_val}')
            lines.append(f'   > ⚠️ 需人工确认（AI 报告生成失败，无法自动验证）')
            lines.append('')

    if diff_count == 0:
        lines.append(f'\n### 🎯 结论：✅ 配置一致')
    elif is_pure_baseplate:
        lines.append(f'\n### 🎯 结论：❌ 纯底板异常，需排查')
    else:
        lines.append(f'\n### 🎯 结论：需人工逐条验证')

    lines.append(f'\n> ⚠️ AI 网关报告生成失败，以上为基础数据摘要。请重试或人工分析。')

    return '\n'.join(lines)


def _is_in_hot_update_flow(conv):
    """
    判断当前对话是否处于热更测试流程中。

    检查最近的消息是否包含文档解析结果或热更测试相关提示，
    且最后一条助手消息是在询问「请确认要测试第几行」。

    返回:
        bool
    """
    recent_messages = AiMessage.objects.filter(
        conversation=conv
    ).order_by('-id')[:10]

    # 检查最近消息中是否有热更测试流程的标志
    has_doc_parsing = False
    has_row_prompt = False

    for msg in recent_messages:
        content = msg.content or ''
        # 检查文档解析结果标记
        if '📋 文档解析结果' in content:
            has_doc_parsing = True
        # 检查助手询问行号的提示
        if msg.role == 'assistant' and '请确认要测试第几行' in content:
            has_row_prompt = True
        # 检查热更测试流程标记
        if '@热更测试' in content or '@hot-update-test' in content:
            has_doc_parsing = True

    return has_doc_parsing and has_row_prompt


def _parse_row_number_from_message(message):
    """
    从用户消息中解析行号（仅接受明确的纯数字或「第N行」格式）。

    支持格式：
    - "20" → 20
    - "第20行" → 20
    - "全部" → None（由调用方特殊处理）
    - "测试第4行" → 4

    返回:
        int | None — 行号，无法解析返回 None

    注意：不再使用「消息中任意数字」的兜底匹配，避免将项目名中的
    数字（如「IOS方块-AB3.5」中的 3、5）误判为行号。
    """
    import re as _re
    if not message:
        return None

    message = message.strip()

    # "全部" 不是单个行号
    if message in ('全部', '所有', 'all'):
        return None

    # 尝试匹配纯数字（整条消息就是数字）
    if message.isdigit():
        return int(message)

    # 尝试匹配 "第N行" 格式
    m = _re.search(r'第\s*(\d+)\s*行', message)
    if m:
        return int(m.group(1))

    # 不再兜底匹配任意数字 — 防止「IOS方块-AB3.5」误判为行号
    return None


def _extract_last_assistant_question(conv):
    """
    获取对话中最后一条助手消息的内容。

    返回:
        str — 助手消息内容，没有则返回空字符串
    """
    last_assistant = AiMessage.objects.filter(
        conversation=conv,
        role='assistant',
    ).order_by('-id').first()
    return last_assistant.content if last_assistant else ''


def _extract_all_row_numbers_from_conversation(conv):
    """
    从对话历史的文档解析结果中提取所有数据行号。

    解析助手消息中的「第 N 行」标记来获取行号列表。

    返回:
        list[int] — 行号列表（已排序），提取失败返回空列表
    """
    import re as _re

    all_messages = AiMessage.objects.filter(
        conversation=conv,
    ).order_by('id')

    row_numbers = set()
    for msg in all_messages:
        content = msg.content or ''
        # 匹配 "第 N 行" 格式
        for m in _re.finditer(r'第\s*(\d+)\s*行', content):
            row_numbers.add(int(m.group(1)))

    return sorted(row_numbers)


def _extract_hot_update_params_from_conversation(conv):
    """
    从对话历史中提取热更测试所需的 project 和 file_id。

    搜索策略：
    1. file_id：在所有用户消息中查找 [FILE_ID:xxx] 标记
    2. project：在用户消息中匹配已知的项目名称（中英文）

    返回:
        tuple[str | None, str | None] — (project, file_id)
    """
    import re as _re

    all_messages = AiMessage.objects.filter(
        conversation=conv,
        role='user',
    ).order_by('id')

    project = None
    file_id = None

    # 合并所有用户消息用于搜索
    combined_content = '\n'.join(msg.content or '' for msg in all_messages)

    # 1. 提取 file_id（最新优先 — 从后往前找）
    # 格式：[FILE_ID:32位hex] 或 [FILE_ID:32位hex, 上传时间: ...]
    file_id_matches = _re.findall(r'\[FILE_ID:([a-f0-9]{32})[^\]]*\]', combined_content)
    if file_id_matches:
        file_id = file_id_matches[-1]  # 取最后一个（最新上传的）

    # 2. 提取 project（在用户消息中搜索项目名）
    from apps.ai_helper.tools import PROJECT_NAME_ALIASES

    # 构建反向映射: 中文名 → 内部标识
    cn_to_internal = {v: k for k, v in PROJECT_NAME_ALIASES.items()}

    # 先尝试匹配内部标识（如 gp_blockblast_orth）
    for internal_name in PROJECT_NAME_ALIASES:
        if internal_name in combined_content:
            project = internal_name
            break

    # 如果没找到，尝试匹配中文名称
    if not project:
        for cn_name, internal_name in cn_to_internal.items():
            if cn_name in combined_content:
                project = internal_name
                break

    # 兜底：尝试匹配 "项目已确认为" 后面的内容
    if not project:
        m = _re.search(r'项目已确认为[：:]\s*(\S+)', combined_content)
        if m:
            name = m.group(1).strip()
            # 尝试精确匹配
            if name in PROJECT_NAME_ALIASES:
                project = name
            elif name in cn_to_internal:
                project = cn_to_internal[name]
            else:
                # 模糊匹配（大小写不敏感）
                name_lower = name.lower()
                for internal, cn_name in PROJECT_NAME_ALIASES.items():
                    if name_lower == cn_name.lower() or name_lower == internal.lower():
                        project = internal
                        break

    return project, file_id


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def chat(request):
    """
    发送消息并获取 AI 回复。

    请求体 JSON:
        conversation_code: str | None — 对话编码，为空则新建对话
        message: str — 用户消息内容
        file_ids: list[str] | None — 引用的已上传文件 ID 列表
        model_provider: str | None — 模型后端："gateway"（默认，远端网关）或 "local"（本地 Ollama）

    响应:
        code: 0
        data: { conversation_code, reply, title, model_provider, model }
    """
    user = request.z_user
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)

    message = (body.get('message') or '').strip()
    if not message:
        return JsonResponse({'code': 400, 'message': '消息不能为空'}, status=400)

    conversation_code = (body.get('conversation_code') or '').strip() or None
    file_ids = body.get('file_ids') or []
    model_provider = (body.get('model_provider') or 'gateway').strip()

    # 1. 获取或创建对话
    conv = get_or_create_conversation(user, conversation_code)

    # 2. 判断是否为首条消息（需在保存用户消息之前检查）
    has_history = AiMessage.objects.filter(conversation=conv).exists()

    # 3. 构建带文件引用的富文本用户消息
    enriched_message = message
    if file_ids:
        file_blocks = _build_file_context_blocks(file_ids)
        if file_blocks:
            enriched_message = file_blocks + '\n\n' + message

    # 4. 保存用户消息（保存原始 message，不含文件内容块，避免重复存储）
    save_user_message(conv, enriched_message)

    # 5. 设置标题（仅首条消息）
    if not conv.title:
        conv.title = create_conversation_title(message)
        conv.save(update_fields=['title'])

    # 6. 构建上下文并调用网关
    # ★ @ 指令上下文隔离（通用规则）
    #    任何以 @ 开头的消息（@热更测试、@命令、@xxx 等现有及未来新增指令），
    #    一律切断历史上下文，仅发送 system prompt + 当前消息。
    #    目的：防止上下文过长导致 AI 回复超时或失败；减少无关 token 消耗。
    #    不以 @ 开头的消息（如回复行号"20"）则保留完整历史上下文。
    is_at_command = message.startswith('@')
    try:
        # ── 根据模型后端选择 system prompt ──
        # 本地模型上下文窗口较小（4096 tokens），使用精简版 prompt
        # 远端网关使用完整的 build_system_prompt（含工具调用指令）
        if model_provider == 'local':
            # 精简版 system prompt：去掉复杂的 TOOL_CALL 指令，
            # 仅保留基本角色描述，适配小模型的小上下文窗口
            system_prompt = (
                '你是一个测试平台 AI 助手，可以帮助用户解答问题、分析文件内容。'
                '请用中文回复。回复简洁明了。'
            )
        else:
            system_prompt = build_system_prompt()

        if is_at_command:
            # @ 命令：仅发送 system prompt + 当前消息（含文件解析块）
            context_messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': enriched_message},
            ]
            logger.info(
                '检测到 @ 命令，已切断历史上下文 (消息长度=%d, 文件块=%s)',
                len(enriched_message),
                '是' if file_ids else '否',
            )
        else:
            # 普通消息：包含完整对话历史
            context_messages = build_context_messages(conv, system_prompt=system_prompt)

        # ── 按 model_provider 路由到不同后端 ──
        if model_provider == 'local':
            # 本地 Ollama 模型：上下文窗口有限，需截断历史消息
            # 从 context_messages 中分离 system prompt（如有）
            ollama_system = None
            ollama_messages = context_messages
            if context_messages and context_messages[0].get('role') == 'system':
                ollama_system = context_messages[0]['content']
                ollama_messages = context_messages[1:]

            # 本地模型上下文窗口有限（默认 8192 tokens），截断历史消息：
            # 只保留最近 10 条，且总字符数不超过 20000（约 5000 tokens）
            MAX_LOCAL_MESSAGES = 10
            MAX_LOCAL_CHARS = 20000
            if len(ollama_messages) > MAX_LOCAL_MESSAGES:
                ollama_messages = ollama_messages[-MAX_LOCAL_MESSAGES:]
                logger.info('本地模型：历史消息截断至最近 %d 条', MAX_LOCAL_MESSAGES)
            total_chars = sum(len(m.get('content', '')) for m in ollama_messages)
            if total_chars > MAX_LOCAL_CHARS:
                # 从最早的消息开始移除，直到总字符数在限制内
                trimmed = []
                running = 0
                for m in reversed(ollama_messages):
                    mc = len(m.get('content', ''))
                    if running + mc > MAX_LOCAL_CHARS and trimmed:
                        break
                    trimmed.insert(0, m)
                    running += mc
                ollama_messages = trimmed
                logger.info('本地模型：历史消息字符数截断 %d → %d', total_chars, running)

            reply = call_ollama_chat(ollama_messages, system_prompt=ollama_system)
            active_model = getattr(settings, 'OLLAMA_MODEL', 'deepseek-r1:1.5b')
            logger.info('使用本地模型: %s', active_model)
        else:
            # 远端智能体网关（默认）
            reply = call_agent_gateway(context_messages)
            gateway_cfg = load_gateway_config()
            active_model = gateway_cfg.get('model', 'unknown')
    except RuntimeError as e:
        logger.error('调用 %s 失败: %s', model_provider, e)
        return JsonResponse({'code': 500, 'message': str(e)}, status=500)

    # 7. 检测并处理 TOOL_CALL
    all_calls = parse_all_tool_calls(reply)
    hot_update_calls = [(n, p) for n, p in all_calls if n == 'hot_update_test' and p]

    if len(hot_update_calls) > 1:
        # 多条热更测试（用户选择「全部」）：逐行执行后合并，发给 AI 网关做逐条验证
        # 清除旧 token，确保新批次只登录一次
        clear_cached_token()
        all_reports = []
        errors = []
        for _tool_name, tool_params in hot_update_calls:
            try:
                file_id = tool_params.get('file_id', '')
                project = tool_params.get('project', '')
                row_number = int(tool_params.get('row_number', 4))
                if not file_id or not project:
                    errors.append(f'第{row_number}行: 缺少参数')
                    continue
                report = perform_hot_update_test(file_id, project, row_number)
                all_reports.append(report)
                logger.info('热更测试完成: project=%s, file_id=%s, row=%s',
                            project, file_id, row_number)
            except (FileNotFoundError, ValueError, RuntimeError) as e:
                logger.error('第%d行热更测试失败: %s', tool_params.get('row_number', 0), e)
                errors.append(f'第{tool_params.get("row_number", "?")}行: {e}')

        if all_reports:
            merged = '\n\n---\n\n'.join(all_reports)
            if errors:
                merged += '\n\n---\n\n### ⚠️ 以下行执行失败\n' + '\n'.join(f'- {e}' for e in errors)
            reply = merged
        else:
            reply = f'❌ 全部行执行失败\n\n' + '\n'.join(f'- {e}' for e in errors)
    elif len(hot_update_calls) == 1:
        # 单条热更测试：直接使用 parse_all_tool_calls 已解析的参数
        _tool_name, tool_params = hot_update_calls[0]
        logger.info('★★★ TOOL_CALL 已解析，开始执行热更测试: project=%s, row=%s',
                    tool_params.get('project'), tool_params.get('row_number'))
        reply = _execute_single_hot_update_test(
            tool_params, reply, context_messages
        )
    else:
        # 无 hot_update_test 调用：检查其他工具类型，或尝试热更测试流程自动恢复
        tool_name, tool_params = parse_tool_call(reply)
        tool_result_text = None

        if tool_name == 'config_compare_file' and tool_params:
            try:
                file_id_1 = tool_params.get('file_id_1', '')
                file_id_2 = tool_params.get('file_id_2', '')
                if not file_id_1 or not file_id_2:
                    raise ValueError('缺少文件 ID 参数')
                comparison = perform_file_compare(file_id_1, file_id_2)
                tool_result_text = format_comparison_result(comparison)
                logger.info('文件比对完成: %s vs %s, identical=%s',
                            file_id_1, file_id_2, comparison.get('is_identical'))

                # 将工具执行结果追加到上下文，再次调用网关让 AI 总结
                context_messages.append({'role': 'assistant', 'content': reply})
                context_messages.append({
                    'role': 'system',
                    'content': f'[工具执行结果]\n{tool_result_text}\n\n请基于以上比对结果，用中文给用户一个简洁明了的总结。'
                })
                final_reply = call_agent_gateway(context_messages)
                reply = final_reply
            except (FileNotFoundError, ValueError, RuntimeError) as e:
                logger.error('执行 config_compare_file 工具失败: %s', e)
                # 工具执行失败时，追加错误信息让 AI 告知用户
                context_messages.append({'role': 'assistant', 'content': reply})
                context_messages.append({
                    'role': 'system',
                    'content': f'[工具执行失败] {e}\n请用中文告知用户工具执行失败的原因，并给出建议。'
                })
                try:
                    error_reply = call_agent_gateway(context_messages)
                    reply = error_reply
                except RuntimeError:
                    pass  # 保持原始 reply

        elif tool_name == 'hot_update_test' and tool_params:
            # 单条 hot_update_test（parse_tool_call 找到但 parse_all_tool_calls 漏掉的情况）
            reply = _execute_single_hot_update_test(
                tool_params, reply, context_messages
            )

        elif not is_at_command and _is_in_hot_update_flow(conv):
            # ★ 关键修复：AI 没有生成 TOOL_CALL，但对话处于热更测试流程中。
            # 仅当用户消息明确是「行号回复」或「全部」时才触发自动恢复，
            # 防止用户发送项目名、文档等非行号消息时错误触发。
            logger.info('★★★ 进入自动恢复路径: message=%s, is_at_command=%s',
                        message[:80], is_at_command)

            is_all = message.strip() in ('全部', '所有', 'all')
            is_row_reply = is_all or _parse_row_number_from_message(message) is not None

            if not is_row_reply:
                # 用户消息不是行号回复（如发送项目名、上传文档等），
                # AI 已给出正常回复（如展示解析结果），不触发自动恢复
                logger.info(
                    '热更测试流程中但用户消息非行号回复，跳过自动恢复 (message=%s)',
                    message[:80]
                )
            elif is_all:
                # 「全部」模式：需要知道总行数
                project, file_id = _extract_hot_update_params_from_conversation(conv)
                # 从文档解析结果中提取行号列表
                all_row_numbers = _extract_all_row_numbers_from_conversation(conv)

                if project and file_id and all_row_numbers:
                    logger.info(
                        '自动恢复热更测试（全部）: project=%s, file_id=%s, rows=%s',
                        project, file_id, all_row_numbers
                    )
                    clear_cached_token()
                    all_reports = []
                    errors = []
                    for rn in all_row_numbers:
                        try:
                            report = perform_hot_update_test(file_id, project, rn)
                            all_reports.append(report)
                            logger.info('热更测试完成: row=%s', rn)
                        except (FileNotFoundError, ValueError, RuntimeError) as e:
                            logger.error('第%d行热更测试失败: %s', rn, e)
                            errors.append(f'第{rn}行: {e}')

                    if all_reports:
                        merged = '\n\n---\n\n'.join(all_reports)
                        if errors:
                            merged += '\n\n---\n\n### ⚠️ 以下行执行失败\n' + '\n'.join(f'- {e}' for e in errors)
                        reply = merged
                    else:
                        reply = f'❌ 全部行执行失败\n\n' + '\n'.join(f'- {e}' for e in errors)
                else:
                    missing = []
                    if not project:
                        missing.append('项目名称')
                    if not file_id:
                        missing.append('文件ID')
                    if not all_row_numbers:
                        missing.append('行号列表')
                    logger.error(
                        '自动恢复热更测试（全部）失败，缺少参数: %s', ', '.join(missing)
                    )
                    reply = (
                        f'{reply}\n\n'
                        f'⚠️ 自动执行全部热更测试失败：无法从对话中提取 {"、".join(missing)}。\n'
                        f'请重新发送 @热更测试 开始测试流程。'
                    )
            else:
                # 单个行号模式
                row_number = _parse_row_number_from_message(message)
                if row_number is None:
                    row_number = _parse_row_number_from_message(
                        _extract_last_assistant_question(conv)
                    )
                project, file_id = _extract_hot_update_params_from_conversation(conv)

                if row_number and project and file_id:
                    logger.info(
                        '自动恢复热更测试: project=%s, file_id=%s, row=%s',
                        project, file_id, row_number
                    )
                    auto_params = {
                        'project': project,
                        'file_id': file_id,
                        'row_number': row_number,
                    }
                    reply = _execute_single_hot_update_test(
                        auto_params, reply, context_messages
                    )
                else:
                    missing = []
                    if not row_number:
                        missing.append('行号')
                    if not project:
                        missing.append('项目名称')
                    if not file_id:
                        missing.append('文件ID')
                    logger.error(
                        '自动恢复热更测试失败，缺少参数: %s', ', '.join(missing)
                    )
                    reply = (
                        f'{reply}\n\n'
                        f'⚠️ 自动执行热更测试失败：无法从对话中提取 {"、".join(missing)}。\n'
                        f'请重新发送 @热更测试 开始测试流程。'
                    )

    # 8. 保存 AI 回复
    logger.info('★★★ 最终返回 reply (前200字): %s', (reply or '')[:200])
    save_assistant_message(conv, reply)
    conv.save(update_fields=['update_time'])

    return JsonResponse({
        'code': 0,
        'data': {
            'conversation_code': conv.conversation_code,
            'reply': reply,
            'title': conv.title,
            'model_provider': model_provider,
            'model': active_model,
        },
    })


def _build_file_context_blocks(file_ids):
    """
    根据 file_ids 构建文件上下文块，用于拼接到用户消息中。

    参数:
        file_ids — 文件 ID 列表

    返回:
        str — 文件上下文文本
    """
    blocks = []
    for fid in file_ids:
        if not fid or not isinstance(fid, str):
            continue
        try:
            content, original_name, file_type, upload_time = get_upload_file_content(fid)
            # 限制文件内容长度，避免超出 AI token 限制
            content_display = content
            if len(content) > 30000:
                content_display = content[:30000] + '\n... (文件过大，已截断)'

            # 构建上传时间标签
            time_tag = ''
            if upload_time:
                time_tag = f', 上传时间: {upload_time}'

            if file_type == 'Image':
                # 图片 OCR 内容用纯文本格式，不包裹 json 代码块
                blocks.append(
                    f'[FILE_ID:{fid}{time_tag}] 文件名: {original_name}\n'
                    f'{content_display}'
                )
            elif file_type == 'Excel':
                # Excel 文件：预解析所有行生成结构化摘要，供 AI 直接使用
                summary = _build_excel_row_summary(fid)
                if summary:
                    blocks.append(
                        f'[FILE_ID:{fid}{time_tag}] 文件名: {original_name}\n'
                        f'{summary}'
                    )
                else:
                    # 降级：原始文本
                    blocks.append(
                        f'[FILE_ID:{fid}{time_tag}] 文件名: {original_name}\n'
                        f'```\n{content_display}\n```'
                    )
            else:
                blocks.append(
                    f'[FILE_ID:{fid}{time_tag}] 文件名: {original_name}\n'
                    f'```json\n{content_display}\n```'
                )
        except FileNotFoundError:
            blocks.append(f'[FILE_ID:{fid}] (文件未找到或已过期)')
        except ValueError as e:
            blocks.append(f'[FILE_ID:{fid}] (文件内容异常: {e})')
    return '\n\n'.join(blocks) if blocks else ''


def _build_excel_row_summary(file_id):
    """
    解析 Excel 文件的所有数据行，生成结构化方案行摘要（含前向填充）。

    返回:
        str | None — Markdown 表格格式的方案行列表，解析失败返回 None
    """
    import re as _re

    try:
        excel_path = _find_original_excel(file_id)
        if not excel_path:
            return None

        import openpyxl
        wb = openpyxl.load_workbook(excel_path, data_only=True)

        # 选择 sheet
        sheet_name = 'All'
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
        else:
            ws = wb.active
            sheet_name = ws.title

        rows = list(ws.iter_rows(values_only=True))
        wb.close()

        if len(rows) < 4:
            return None

        # 表头检测（第 3 行，0-based index 2）
        header_row_idx = 2
        headers = list(rows[header_row_idx]) if header_row_idx < len(rows) else []
        col_map = _build_column_map_from_headers(headers)

        # 方案号正则
        scheme_pattern = _re.compile(r'(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])')
        base_rules = [
            _re.compile(r'【底板】[^\n]*?(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])'),
            _re.compile(r'[（(]?底板[）)]?[^\n]*?(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])'),
            _re.compile(r'基于[^\n]*?(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])'),
        ]

        def _s(v):
            return str(v).strip() if v is not None else ''

        def _extract_base_scheme(text):
            if not text:
                return ''
            for rule in base_rules:
                m = rule.search(text)
                if m:
                    return m.group(1)
            all_s = scheme_pattern.findall(text)
            return all_s[0] if all_s else ''

        # 解析所有数据行（从第 4 行开始，0-based index 3）
        parsed_rows = []
        last_new_scheme = ''
        last_base_scheme = ''

        for row_idx in range(3, len(rows)):
            row = rows[row_idx]
            if not row or all(v is None for v in row):
                continue  # 跳过完全空行

            rn = row_idx + 1  # 1-based row number
            new_scheme = _s(row[col_map.get('原始方案编号', 0)]) if len(row) > col_map.get('原始方案编号', 0) else ''
            ad_type = _s(row[col_map.get('广告类型', 1)]) if len(row) > col_map.get('广告类型', 1) else ''
            overview_text = _s(row[col_map.get('方案概述', 2)]) if len(row) > col_map.get('方案概述', 2) else ''
            base_scheme = _extract_base_scheme(overview_text)

            # 前向填充
            if not new_scheme:
                new_scheme = last_new_scheme
            if not base_scheme:
                base_scheme = last_base_scheme

            # 更新上一次有效值
            if new_scheme:
                last_new_scheme = new_scheme
            if base_scheme:
                last_base_scheme = base_scheme

            # 合并方案概述 + 方案细节作为修改概述
            detail_text = _s(row[col_map.get('方案细节', 5)]) if len(row) > col_map.get('方案细节', 5) else ''
            full_overview = overview_text.replace('\n', ' ')
            if detail_text:
                detail_clean = detail_text.replace('\n', ' ')
                full_overview = f'{full_overview} | {detail_clean}'
            # 截取前 800 字作为摘要
            overview_summary = full_overview[:800]
            if len(full_overview) > 800:
                overview_summary += '...'

            parsed_rows.append({
                'row': rn,
                'new_scheme': new_scheme or '（无）',
                'base_scheme': base_scheme or '（无）',
                'ad_type': ad_type or '-',
                'overview': overview_summary,
            })

        if not parsed_rows:
            return None

        # 生成分块展示格式
        separator = '─' * 30
        lines = [
            f'## 📋 文档解析结果 — 共 {len(parsed_rows)} 行方案（已应用前向填充）',
            '',
        ]
        for pr in parsed_rows:
            lines.append(separator)
            lines.append(f'第 {pr["row"]} 行')
            lines.append(f'  新方案号：{pr["new_scheme"]}')
            lines.append(f'  原方案号：{pr["base_scheme"]}')
            lines.append(f'  新方案修改概述：{pr["overview"]}')
        lines.append(separator)

        return '\n'.join(lines)

    except Exception:
        return None


def _build_column_map_from_headers(headers):
    """根据表头行构建列名→列索引的映射（供 _build_excel_row_summary 使用）。"""
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
    return col_map


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def upload_file(request):
    """
    上传配置文件（JSON / Excel）供 AI 分析。

    请求: multipart/form-data
        file: 上传的文件（.json / .xlsx / .xls）
        conversation_code: str | None — 可选，关联的对话编码

    响应:
        code: 0
        data: { file_id, filename, size, file_type }
    """
    uploaded = request.FILES.get('file')
    if not uploaded:
        return JsonResponse({'code': 400, 'message': '未检测到上传文件'}, status=400)

    # 校验文件扩展名
    _, ext = os.path.splitext(uploaded.name)
    ext_lower = ext.lower()
    if ext_lower not in ALLOWED_EXTENSIONS:
        return JsonResponse({
            'code': 400,
            'message': f'不支持的文件类型（{ext_lower}），仅允许: {", ".join(sorted(ALLOWED_EXTENSIONS))}',
        }, status=400)

    # 校验文件大小
    if uploaded.size > MAX_UPLOAD_SIZE:
        max_mb = MAX_UPLOAD_SIZE / (1024 * 1024)
        return JsonResponse({
            'code': 400,
            'message': f'文件大小超过限制（最大 {max_mb:.0f}MB）',
        }, status=400)

    is_excel = ext_lower in ('.xlsx', '.xls')
    is_image = ext_lower in ('.png', '.jpg', '.jpeg', '.gif', '.webp')
    raw_bytes = None  # 初始化，用于 Excel 文件的原始二进制

    if is_image:
        # 图片文件：用 Pillow 读取元信息并生成文本描述
        try:
            content = _read_image_as_text(uploaded)
        except Exception as e:
            logger.exception('读取图片文件失败')
            return JsonResponse({
                'code': 400,
                'message': f'图片文件解析失败，请确认文件未损坏且格式正确: {e}',
            }, status=400)
    elif is_excel:
        # Excel 文件：用 openpyxl 读取并转为文本，同时保留原始文件二进制
        try:
            # 先保存原始二进制（用于后续热更测试等需要原始 Excel 的操作）
            raw_bytes = uploaded.read()
            content = _read_excel_as_text(raw_bytes)
        except Exception as e:
            logger.exception('读取 Excel 文件失败')
            return JsonResponse({
                'code': 400,
                'message': f'Excel 文件解析失败，请确认文件未损坏且格式正确: {e}',
            }, status=400)
    else:
        # JSON 文件：读取并校验
        try:
            content = uploaded.read().decode('utf-8')
            json.loads(content)
        except UnicodeDecodeError:
            return JsonResponse({'code': 400, 'message': '文件编码不支持，请使用 UTF-8 编码的 JSON 文件'}, status=400)
        except json.JSONDecodeError as e:
            return JsonResponse({'code': 400, 'message': f'文件不是合法的 JSON: {e}'}, status=400)

    # 保存文件（文本形式，统一用 .json 后缀存放）
    file_id = uuid.uuid4().hex
    original_filename = uploaded.name

    if is_image:
        file_type = 'Image'
    elif is_excel:
        file_type = 'Excel'
    else:
        file_type = 'JSON'

    # 对于 Excel 文件，同时保存原始二进制文件（供热更测试等需要原始 Excel 的场景）
    save_uploaded_file(file_id, original_filename, content, file_type=file_type, raw_bytes=raw_bytes)

    logger.info('%s 文件上传成功: file_id=%s, filename=%s, size=%d',
                file_type, file_id, original_filename, uploaded.size)

    # ── 生成文件内容预览（仅截取文本前 N 字符，不做文档解析） ──
    content_preview = _truncate_preview(content, 3000)

    return JsonResponse({
        'code': 0,
        'message': '上传成功',
        'data': {
            'file_id': file_id,
            'filename': original_filename,
            'size': uploaded.size,
            'file_type': file_type,
            'content_preview': content_preview,
        },
    })


def _read_excel_as_text(file_obj_or_bytes):
    """
    用 openpyxl 读取 Excel 文件，转为制表符分隔的文本。
    每个 Sheet 转为独立的段落。
    支持传入文件对象或 bytes。
    """
    import io as _io

    if isinstance(file_obj_or_bytes, bytes):
        file_obj = _io.BytesIO(file_obj_or_bytes)
    else:
        file_obj = file_obj_or_bytes

    wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
    parts = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        parts.append(f'## Sheet: {sheet_name}')
        for row in ws.iter_rows(values_only=True):
            parts.append('\t'.join(str(c) if c is not None else '' for c in row))
    wb.close()
    return '\n'.join(parts)


def _read_image_as_text(file_obj):
    """
    用 Pillow 读取图片元信息，并通过腾讯云 OCR 提取图片中的文字内容。
    如果 OCR 失败，降级为仅返回元数据描述（上传不中断）。
    """
    # Step 1: 用 Pillow 获取图片元数据
    img = Image.open(file_obj)
    fmt = img.format or '未知'
    mode = img.mode
    width, height = img.size
    file_size = file_obj.size if hasattr(file_obj, 'size') else 0
    size_kb = file_size / 1024

    lines = [
        f'图片文件（已通过 OCR 提取文字内容）',
        f'格式: {fmt}',
        f'尺寸: {width} x {height} 像素',
        f'色彩模式: {mode}',
        f'文件大小: {size_kb:.1f} KB',
    ]

    # Step 2: 尝试 OCR 识别图片中的文字
    ocr_text = ''
    try:
        file_obj.seek(0)
        raw_bytes = file_obj.read()
        b64 = base64_en(raw_bytes, is_file=True)
        img_base = ImageBase(
            secret_id=getattr(settings, 'TENCENT_OCR_SECRET_ID', None),
            secret_key=getattr(settings, 'TENCENT_OCR_SECRET_KEY', None),
        )
        resp_json_str = img_base.image_text_orc(b64)
        ocr_text = _extract_detected_text_from_tencent_json(resp_json_str)
    except Exception as e:
        logger.warning('图片 OCR 识别失败，降级为仅元数据: %s', e)

    # Step 3: 追加 OCR 结果或降级提示
    lines.append('')
    if ocr_text and ocr_text.strip():
        lines.append('--- OCR 识别文字内容 ---')
        lines.append(ocr_text.strip())
    else:
        lines.append('（未能从图片中识别出文字内容，请确认图片中包含可识别的文字）')

    return '\n'.join(lines)


def _truncate_preview(content, max_len=3000):
    """截断内容用于预览显示（不做文档解析）。"""
    if not content:
        return ''
    if len(content) <= max_len:
        return content
    return content[:max_len] + '\n... (内容已截断)'


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def compare_files(request):
    """
    手动触发两个已上传文件的比对（无需通过聊天）。

    请求体 JSON:
        file_id_1: str — 第一个文件 ID
        file_id_2: str — 第二个文件 ID

    响应:
        code: 0
        data: { comparison: {...}, summary: "..." }
    """
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)

    file_id_1 = (body.get('file_id_1') or '').strip()
    file_id_2 = (body.get('file_id_2') or '').strip()

    if not file_id_1 or not file_id_2:
        return JsonResponse({'code': 400, 'message': '缺少 file_id_1 或 file_id_2'}, status=400)

    try:
        comparison = perform_file_compare(file_id_1, file_id_2)
        summary = format_comparison_result(comparison)
        return JsonResponse({
            'code': 0,
            'data': {
                'comparison': comparison,
                'summary': summary,
            },
        })
    except FileNotFoundError as e:
        return JsonResponse({'code': 404, 'message': str(e)}, status=404)
    except ValueError as e:
        return JsonResponse({'code': 400, 'message': str(e)}, status=400)
    except Exception as e:
        logger.exception('compare_files')
        return JsonResponse({'code': 500, 'message': f'比对失败: {e}'}, status=500)


# ── 模型列表（供前端切换模型后端）───────────────────────────────────

@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def models_info(request):
    """
    获取可用的 AI 模型后端列表，供前端切换选择。

    响应:
        code: 0
        data: {
            providers: [
                { key: "gateway", label: "智能体网关", is_default: true, model: "deepseek-v4-pro" },
                { key: "local", label: "本地模型 (Ollama)", is_default: false, model: "deepseek-r1:1.5b" },
            ]
        }
    """
    # 远端网关信息
    gateway_cfg = load_gateway_config()
    gateway_model = gateway_cfg.get('model', 'unknown')

    # 本地 Ollama 模型列表（仅在能连上 Ollama 且确实存在模型时才展示）
    local_models = []
    try:
        local_models = list_ollama_models()
    except RuntimeError:
        # Ollama 不可用或未部署模型：不展示本地模型选项
        local_models = []

    providers = [
        {
            'key': 'gateway',
            'label': '智能体网关',
            'is_default': True,
            'model': gateway_model,
            'description': '远端大模型，功能完整，支持工具调用',
        },
    ]

    # 只有真实查询到本地模型时才展示"本地模型"选项
    if local_models:
        # 展示名优先用配置的 OLLAMA_MODEL（若其确实存在于本地模型列表中），否则用查询到的第一个模型
        configured_model = getattr(settings, 'OLLAMA_MODEL', '')
        local_model_name = next(
            (m['name'] for m in local_models if m['name'] == configured_model),
            local_models[0]['name'],
        )
        providers.append({
            'key': 'local',
            'label': f'本地模型 ({local_model_name})',
            'is_default': False,
            'model': local_model_name,
            'description': '本地 Ollama 部署，数据不出本机，响应速度取决于硬件',
            'available_models': [
                {'name': m['name'], 'size': m.get('size', 0)}
                for m in local_models
            ],
        })

    return JsonResponse({
        'code': 0,
        'data': {
            'providers': providers,
            'default_provider': 'gateway',
        },
    })
