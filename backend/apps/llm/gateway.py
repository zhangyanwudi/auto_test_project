"""
Ollama 本地模型网关调用层。

封装对 Ollama /api/chat 的 HTTP 请求，支持：
- 纯文本对话
- 图片消息（需配置 OLLAMA_VISION_MODEL）
- 流式响应
"""
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _ollama_config():
    """从 Django settings 读取 Ollama 配置，缺失项用默认值填充。"""
    return {
        'base_url': getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434'),
        'model': getattr(settings, 'OLLAMA_MODEL', 'deepseek-r1:1.5b'),
        'vision_model': getattr(settings, 'OLLAMA_VISION_MODEL', ''),
        'timeout': int(getattr(settings, 'OLLAMA_TIMEOUT_SECONDS', 120)),
        'num_ctx': int(getattr(settings, 'OLLAMA_NUM_CTX', 8192)),
        'temperature': float(getattr(settings, 'OLLAMA_TEMPERATURE', 0.7)),
    }


def _extract_reply(response_data):
    """
    从 Ollama /api/chat 响应中提取 AI 回复文本。

    Ollama 返回格式：
    {"model": "...", "message": {"role": "assistant", "content": "..."}, "done": true}
    """
    if isinstance(response_data, dict):
        msg = response_data.get('message') or {}
        content = msg.get('content', '')
        if content:
            return content.strip()
    return str(response_data)


def call_ollama_chat(messages, system_prompt=None, stream=False):
    """
    调用 Ollama 本地模型进行对话。

    参数:
        messages: list[dict] — 消息列表，每项含 {"role": "user"|"assistant", "content": "..."}
        system_prompt: str | None — 可选系统提示词
        stream: bool — 是否启用流式响应

    返回:
        str — AI 回复文本

    异常:
        RuntimeError — 连接失败、超时或返回异常
    """
    cfg = _ollama_config()
    url = cfg['base_url'].rstrip('/') + '/api/chat'
    model = cfg['model']

    # 构建消息列表：system prompt（如有）+ 历史消息
    chat_messages = []
    if system_prompt:
        chat_messages.append({'role': 'system', 'content': system_prompt})
    chat_messages.extend(messages)

    body = {
        'model': model,
        'messages': chat_messages,
        'stream': stream,
        'options': {
            'num_ctx': cfg['num_ctx'],
            'temperature': cfg['temperature'],
        },
    }

    logger.info(
        '调用 Ollama: %s, model=%s, 消息条数=%d, stream=%s, num_ctx=%d',
        url, model, len(chat_messages), stream, cfg['num_ctx'],
    )

    try:
        resp = requests.post(
            url,
            json=body,
            timeout=cfg['timeout'],
        )
        resp.raise_for_status()
        data = resp.json()
        reply = _extract_reply(data)
        logger.info('Ollama 返回成功, 回复长度: %d', len(reply) if reply else 0)
        return reply
    except requests.exceptions.Timeout:
        logger.error('Ollama 请求超时 (%ds)', cfg['timeout'])
        raise RuntimeError(f'Ollama 请求超时（{cfg["timeout"]}秒），请稍后重试')
    except requests.exceptions.ConnectionError as e:
        logger.error('无法连接 Ollama 服务: %s', e)
        raise RuntimeError(
            f'无法连接 Ollama 服务（{cfg["base_url"]}）。'
            f'请确认 Ollama 已启动：在终端运行 `ollama serve`'
        )
    except requests.exceptions.HTTPError as e:
        logger.error('Ollama 返回 HTTP 错误: %s', e)
        detail = ''
        try:
            detail = e.response.text[:500]
        except Exception:
            pass
        raise RuntimeError(f'Ollama 返回错误 (HTTP {e.response.status_code})：{detail}')
    except requests.exceptions.RequestException as e:
        logger.error('Ollama 请求异常: %s', e)
        raise RuntimeError(f'请求 Ollama 异常：{e}')
    except (KeyError, TypeError) as e:
        logger.error('解析 Ollama 响应失败: %s', e)
        raise RuntimeError(f'解析 Ollama 响应失败，请检查返回格式')


def call_ollama_stream(messages, system_prompt=None):
    """
    调用 Ollama 并返回流式迭代器，逐块产出文本。

    参数:
        messages: list[dict]
        system_prompt: str | None

    返回:
        generator — 逐块产出 str 文本

    异常:
        RuntimeError
    """
    cfg = _ollama_config()
    url = cfg['base_url'].rstrip('/') + '/api/chat'
    model = cfg['model']

    chat_messages = []
    if system_prompt:
        chat_messages.append({'role': 'system', 'content': system_prompt})
    chat_messages.extend(messages)

    body = {
        'model': model,
        'messages': chat_messages,
        'stream': True,
        'options': {
            'num_ctx': cfg['num_ctx'],
            'temperature': cfg['temperature'],
        },
    }

    logger.info('Ollama 流式请求: model=%s, 消息条数=%d, num_ctx=%d',
                model, len(chat_messages), cfg['num_ctx'])

    try:
        resp = requests.post(
            url,
            json=body,
            timeout=cfg['timeout'],
            stream=True,
        )
        resp.raise_for_status()

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                chunk = json.loads(line)
                msg = chunk.get('message') or {}
                content = msg.get('content', '')
                if content:
                    yield content
                if chunk.get('done'):
                    break
            except json.JSONDecodeError:
                continue
    except requests.exceptions.Timeout:
        logger.error('Ollama 流式请求超时')
        raise RuntimeError(f'Ollama 请求超时，请稍后重试')
    except requests.exceptions.ConnectionError as e:
        logger.error('无法连接 Ollama: %s', e)
        raise RuntimeError('无法连接 Ollama 服务，请确认已启动 `ollama serve`')
    except requests.exceptions.RequestException as e:
        logger.error('Ollama 流式请求异常: %s', e)
        raise RuntimeError(f'请求 Ollama 异常：{e}')


def call_ollama_with_image(messages, image_base64, system_prompt=None):
    """
    使用多模态视觉模型处理图片 + 文本消息。

    参数:
        messages: list[dict] — 文本消息列表
        image_base64: str — 图片的 base64 编码
        system_prompt: str | None

    返回:
        str — AI 回复

    异常:
        RuntimeError — 未配置视觉模型或调用失败
    """
    cfg = _ollama_config()
    vision_model = cfg['vision_model']
    if not vision_model:
        raise RuntimeError(
            '未配置视觉模型。请在 settings.py 中设置 OLLAMA_VISION_MODEL，'
            '或通过 `ollama pull llava:7b` 拉取视觉模型'
        )

    url = cfg['base_url'].rstrip('/') + '/api/chat'

    chat_messages = []
    if system_prompt:
        chat_messages.append({'role': 'system', 'content': system_prompt})

    # 将历史文本消息加入
    chat_messages.extend(messages)

    # 最后一条消息应包含图片
    last_user_msg = chat_messages[-1]['content'] if chat_messages else ''
    chat_messages.append({
        'role': 'user',
        'content': last_user_msg,
        'images': [image_base64],
    })

    body = {
        'model': vision_model,
        'messages': chat_messages,
        'stream': False,
    }

    logger.info('Ollama 视觉模型请求: model=%s', vision_model)

    try:
        resp = requests.post(
            url,
            json=body,
            timeout=cfg['timeout'],
        )
        resp.raise_for_status()
        data = resp.json()
        return _extract_reply(data)
    except requests.exceptions.Timeout:
        raise RuntimeError(f'视觉模型请求超时，请稍后重试')
    except requests.exceptions.ConnectionError:
        raise RuntimeError('无法连接 Ollama 服务，请确认已启动 `ollama serve`')
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'请求视觉模型异常：{e}')


def list_ollama_models():
    """
    获取 Ollama 可用的模型列表。

    返回:
        list[dict] — [{"name": "deepseek-r1:1.5b", "size": ..., "modified_at": ...}, ...]

    异常:
        RuntimeError
    """
    cfg = _ollama_config()
    url = cfg['base_url'].rstrip('/') + '/api/tags'

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = data.get('models', [])
        return [
            {
                'name': m.get('name', ''),
                'size': m.get('size', 0),
                'modified_at': m.get('modified_at', ''),
            }
            for m in models
        ]
    except requests.exceptions.ConnectionError:
        raise RuntimeError('无法连接 Ollama 服务')
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'获取模型列表失败：{e}')
