"""
智能体网关调用层：读取本地配置，封装对 stargate 网关的 HTTP 请求。
默认采用 OpenAI Chat Completions 兼容格式构造请求与解析响应。
"""
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def load_config():
    """从 Django settings 获取 AI 助手网关配置，缺失项用默认值填充。"""
    cfg = getattr(settings, 'AI_HELPER_CONFIG', {}) or {}
    return {
        'gateway_url': cfg.get('gateway_url', ''),
        'api_key': cfg.get('api_key', ''),
        'model': cfg.get('model', ''),
        'max_tokens': int(cfg.get('max_tokens', 4096)),
        'temperature': float(cfg.get('temperature', 0.7)),
        'timeout_seconds': int(cfg.get('timeout_seconds', 60)),
        'config_compare_page_url': cfg.get('config_compare_page_url', 'http://localhost:5173'),
        'config_compare_page_path': cfg.get('config_compare_page_path', '/config-compare'),
    }


def build_request_body(messages, config):
    """
    构造发往智能体网关的请求体。
    默认按 OpenAI Chat Completions 格式，若网关使用不同格式请在此处调整。
    """
    body = {
        'model': config['model'],
        'messages': messages,
        'max_tokens': config['max_tokens'],
        'temperature': config['temperature'],
    }
    # 透传配置中的额外参数（如 language 等）
    for key in ('language',):
        if key in config and config[key]:
            body[key] = config[key]
    return body


def extract_reply(response_data):
    """
    从网关响应中提取 AI 回复文本。
    默认按 OpenAI 格式解析 choices[0].message.content。
    若网关使用不同的响应结构请在此处调整。
    """
    if 'choices' in response_data and len(response_data['choices']) > 0:
        choice = response_data['choices'][0]
        if 'message' in choice and 'content' in choice['message']:
            return choice['message']['content']
    # 若网关直接返回 text 或 reply 字段
    if isinstance(response_data, dict):
        if 'reply' in response_data:
            return response_data['reply']
        if 'text' in response_data:
            return response_data['text']
        if 'content' in response_data:
            return response_data['content']
        if 'data' in response_data:
            d = response_data['data']
            if isinstance(d, dict):
                return extract_reply(d)
            if isinstance(d, str):
                return d
    return str(response_data)


def call_agent_gateway(messages):
    """
    调用智能体网关发送消息并返回 AI 回复文本。

    参数:
        messages: list[dict] — 消息列表，每项含 {"role": "user"|"assistant", "content": "..."}

    返回:
        str — AI 回复文本

    异常:
        RuntimeError — 配置缺失、网关请求失败或返回异常
    """
    config = load_config()
    if not config['gateway_url']:
        raise RuntimeError('未配置智能体网关地址，请检查 config/ai_helper_config.json 中的 gateway_url')
    if not config['api_key']:
        raise RuntimeError('未配置智能体网关密钥，请检查 config/ai_helper_config.json 中的 api_key')

    body = build_request_body(messages, config)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {config["api_key"]}',
    }
    timeout = config['timeout_seconds']

    logger.info('调用智能体网关: %s, 消息条数: %d', config['gateway_url'], len(messages))

    try:
        resp = requests.post(
            config['gateway_url'],
            json=body,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = extract_reply(data)
        logger.info('智能体网关返回成功, 回复长度: %d', len(reply) if reply else 0)
        return reply
    except requests.exceptions.Timeout:
        logger.error('智能体网关请求超时 (%ds)', timeout)
        raise RuntimeError(f'请求智能体网关超时（{timeout}秒），请稍后重试')
    except requests.exceptions.HTTPError as e:
        logger.error('智能体网关返回 HTTP 错误: %s', e)
        detail = ''
        try:
            detail = e.response.text[:500]
        except Exception:
            pass
        raise RuntimeError(f'智能体网关返回错误 (HTTP {e.response.status_code})：{detail}')
    except requests.exceptions.RequestException as e:
        logger.error('智能体网关请求异常: %s', e)
        raise RuntimeError(f'无法连接智能体网关：{e}')
    except (KeyError, IndexError, TypeError) as e:
        logger.error('解析智能体网关响应失败: %s', e)
        raise RuntimeError(f'解析智能体网关响应失败，请检查网关返回格式')
