"""
本地 LLM API 接口层：会话管理、对话、文件上传与解析。

调用链：apis/llm/views.py → apps/llm/gateway.py（Ollama API）→ Ollama 本地服务
                            → apps/llm/file_parser.py（文件解析）
                            → apps/llm/chat_manager.py（会话上下文）
"""
import json
import logging
import uuid

from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.llm.chat_manager import (
    create_session,
    add_message,
    get_context,
    clear_session,
    delete_session,
    get_session_info,
    list_sessions,
    session_exists,
)
from apps.llm.file_parser import parse_file, ALLOWED_EXTENSIONS, MAX_FILE_SIZE
from apps.llm.gateway import (
    call_ollama_chat,
    call_ollama_stream,
    list_ollama_models,
)

logger = logging.getLogger(__name__)

# ── 文件上传存储目录 ──────────────────────────────────────────────

from apps.ai_helper.views import save_uploaded_file as _ai_save_uploaded_file


def _save_file(file_id, original_filename, content, file_type):
    """保存上传文件到磁盘（复用 ai_helper 的存储机制但使用独立目录）。"""
    from datetime import date, datetime
    from base_utils.path_base import check_dirs, joint_path
    import os

    root = joint_path(str(settings.BASE_DIR), 'data/llm_uploads')
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
        'file_type': file_type,
    }
    with open(meta_path, 'w', encoding='utf-8') as mf:
        json.dump(meta, mf, ensure_ascii=False)

    return file_path


def _read_uploaded_file(file_id):
    """从磁盘读取已上传文件的内容和元信息。"""
    from base_utils.path_base import joint_path, exists
    import os

    root = joint_path(str(settings.BASE_DIR), 'data/llm_uploads')
    if not exists(root):
        raise FileNotFoundError(f'文件不存在: {file_id}')

    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if fname == f'{file_id}.json':
                file_path = joint_path(dirpath, fname)
                meta_path = file_path + '.meta'

                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                original_filename = f'{file_id}.json'
                file_type = None
                if exists(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as mf:
                            meta = json.load(mf)
                        original_filename = meta.get('original_filename', original_filename)
                        file_type = meta.get('file_type')
                    except (json.JSONDecodeError, IOError):
                        pass

                return content, original_filename, file_type

    raise FileNotFoundError(f'文件不存在: {file_id}')


# ── 工具函数 ──────────────────────────────────────────────────────

def _parse_body(request):
    """解析 JSON 请求体。"""
    try:
        return json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return None


def _json_response(code=0, message=None, data=None, status=200):
    """构建统一 JSON 响应。"""
    body = {'code': code}
    if message:
        body['message'] = message
    if data is not None:
        body['data'] = data
    return JsonResponse(body, status=status)


def _build_file_context_blocks(file_ids):
    """根据 file_ids 构建文件上下文文本块。"""
    blocks = []
    for fid in file_ids:
        if not fid or not isinstance(fid, str):
            continue
        try:
            content, original_name, file_type = _read_uploaded_file(fid)
            # 限制文件内容长度
            content_display = content
            if len(content) > 30000:
                content_display = content[:30000] + '\n... (文件过大，已截断)'

            blocks.append(
                f'[文件: {original_name}]\n'
                f'```\n{content_display}\n```'
            )
        except FileNotFoundError:
            blocks.append(f'[文件 ID: {fid}] (文件不存在或已过期)')
    return '\n\n'.join(blocks) if blocks else ''


# ── 会话管理 API ──────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def session_new(request):
    """创建新的对话会话。"""
    session_id = create_session()
    return _json_response(data={
        'session_id': session_id,
        'message': '会话已创建',
    })


@csrf_exempt
@require_http_methods(['GET'])
def session_list(request):
    """列出所有活跃会话。"""
    sessions = list_sessions()
    return _json_response(data={'sessions': sessions, 'total': len(sessions)})


@csrf_exempt
@require_http_methods(['GET'])
def session_history(request, session_id):
    """获取会话历史消息。"""
    if not session_exists(session_id):
        return _json_response(code=404, message='会话不存在', status=404)

    info = get_session_info(session_id)
    messages = get_context(session_id)
    return _json_response(data={
        'session_id': session_id,
        'info': info,
        'messages': messages,
    })


@csrf_exempt
@require_http_methods(['POST'])
def session_clear(request, session_id):
    """清空会话消息。"""
    count = clear_session(session_id)
    if count == 0 and not session_exists(session_id):
        return _json_response(code=404, message='会话不存在', status=404)
    return _json_response(data={'session_id': session_id, 'deleted_count': count})


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
def session_delete(request, session_id):
    """删除整个会话。"""
    ok = delete_session(session_id)
    if not ok:
        return _json_response(code=404, message='会话不存在', status=404)
    return _json_response(data={'session_id': session_id, 'message': '会话已删除'})


# ── 对话 API ──────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def chat(request):
    """
    发送消息并获取 LLM 回复。

    请求体 JSON:
        session_id: str | None — 会话 ID，为空则自动创建新会话
        message: str — 用户消息内容
        system_prompt: str | None — 可选系统提示词
        file_ids: list[str] | None — 引用的已上传文件 ID 列表
        stream: bool — 是否启用流式响应（默认 false）

    响应（非流式）:
        { code: 0, data: { session_id, reply, model } }

    响应（流式）:
        SSE 格式: data: {"token": "..."}\n\n
    """
    body = _parse_body(request)
    if body is None:
        return _json_response(code=400, message='请求体格式错误', status=400)

    message = (body.get('message') or '').strip()
    if not message:
        return _json_response(code=400, message='消息不能为空', status=400)

    session_id = (body.get('session_id') or '').strip() or None
    system_prompt = (body.get('system_prompt') or '').strip() or None
    file_ids = body.get('file_ids') or []
    use_stream = body.get('stream', False)

    # 默认系统提示词
    if not system_prompt:
        system_prompt = getattr(
            settings, 'OLLAMA_DEFAULT_SYSTEM_PROMPT',
            '你是一个有帮助的AI助手，请用中文回答用户的问题。',
        )

    # 1. 获取或创建会话
    if not session_id or not session_exists(session_id):
        session_id = create_session()

    # 2. 构建文件上下文
    enriched_message = message
    if file_ids:
        file_blocks = _build_file_context_blocks(file_ids)
        if file_blocks:
            enriched_message = file_blocks + '\n\n' + message

    # 3. 保存用户消息到会话
    add_message(session_id, 'user', enriched_message)

    # 4. 构建上下文消息列表
    history = get_context(session_id)
    # 将 system prompt 作为第一条，历史消息跟随
    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.extend(history)

    # 5. 调用 Ollama
    config_model = getattr(settings, 'OLLAMA_MODEL', 'deepseek-r1:1.5b')

    try:
        if use_stream:
            # 流式响应：使用 SSE
            def stream_generator():
                full_reply = ''
                try:
                    for chunk in call_ollama_stream(messages):
                        full_reply += chunk
                        yield f'data: {json.dumps({"token": chunk}, ensure_ascii=False)}\n\n'
                    # 保存完整回复
                    add_message(session_id, 'assistant', full_reply)
                    yield f'data: {json.dumps({"done": true, "session_id": session_id, "model": config_model}, ensure_ascii=False)}\n\n'
                except RuntimeError as e:
                    yield f'data: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'

            response = StreamingHttpResponse(
                stream_generator(),
                content_type='text/event-stream',
            )
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response
        else:
            # 非流式
            reply = call_ollama_chat(messages)
    except RuntimeError as e:
        logger.error('调用 Ollama 失败: %s', e)
        return _json_response(code=500, message=str(e), status=500)

    # 6. 保存 AI 回复
    add_message(session_id, 'assistant', reply)

    return _json_response(data={
        'session_id': session_id,
        'reply': reply,
        'model': config_model,
    })


# ── 文件上传 API ──────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def upload_file(request):
    """
    上传文件并解析为文本。

    请求: multipart/form-data
        file: 上传的文件

    响应:
        { code: 0, data: { file_id, filename, file_type, size, content_preview } }
    """
    uploaded = request.FILES.get('file')
    if not uploaded:
        return _json_response(code=400, message='未检测到上传文件', status=400)

    # 校验文件扩展名
    import os
    _, ext = os.path.splitext(uploaded.name)
    ext_lower = ext.lower()
    if ext_lower not in ALLOWED_EXTENSIONS:
        return _json_response(
            code=400,
            message=f'不支持的文件类型（{ext_lower}）。'
                    f'支持的格式: {", ".join(sorted(ALLOWED_EXTENSIONS))}',
            status=400,
        )

    # 校验文件大小
    if uploaded.size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        return _json_response(
            code=400,
            message=f'文件大小超过限制（最大 {max_mb:.0f}MB）',
            status=400,
        )

    # 读取并解析文件
    raw_bytes = uploaded.read()
    try:
        result = parse_file(raw_bytes, uploaded.name)
    except ValueError as e:
        return _json_response(code=400, message=str(e), status=400)
    except ImportError as e:
        return _json_response(code=400, message=str(e), status=400)
    except Exception as e:
        logger.exception('文件解析异常: %s', uploaded.name)
        return _json_response(code=500, message=f'文件解析失败: {e}', status=500)

    # 保存文件
    file_id = uuid.uuid4().hex
    _save_file(file_id, uploaded.name, result['text'], result['file_type'])

    # 生成预览（截取前 2000 字符）
    preview = result['text'][:2000]
    if len(result['text']) > 2000:
        preview += '\n... (已截断)'

    logger.info('文件上传成功: file_id=%s, filename=%s, type=%s, size=%d',
                file_id, uploaded.name, result['file_type'], result['size'])

    return _json_response(data={
        'file_id': file_id,
        'filename': uploaded.name,
        'file_type': result['file_type'],
        'size': result['size'],
        'content_preview': preview,
    })


# ── 模型列表 API ──────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(['GET'])
def model_list(request):
    """获取 Ollama 可用的模型列表。"""
    try:
        models = list_ollama_models()
        current_model = getattr(settings, 'OLLAMA_MODEL', 'deepseek-r1:1.5b')
        return _json_response(data={
            'models': models,
            'current_model': current_model,
        })
    except RuntimeError as e:
        return _json_response(code=500, message=str(e), status=500)
