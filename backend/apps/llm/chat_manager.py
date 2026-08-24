"""
LLM 对话管理：基于内存 session 的上下文存储与管理。

每个 session 包含：
- session_id: UUID 字符串
- messages: [{role, content}, ...]
- created_at: 创建时间戳
- last_active: 最后活跃时间戳
"""
import logging
import threading
import time
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

# ── 内存会话存储 ──────────────────────────────────────────────────

# session_id → {messages, created_at, last_active}
_sessions: dict = {}
_lock = threading.Lock()

# 会话过期时间（秒）：24 小时无活动自动清除
SESSION_TTL_SECONDS = 24 * 60 * 60

# 每个会话最大存储消息数
MAX_MESSAGES_PER_SESSION = 100


def _now():
    return time.time()


def _cleanup_expired():
    """清理过期会话（内部调用，已加锁）。"""
    cutoff = _now() - SESSION_TTL_SECONDS
    expired = [
        sid for sid, s in _sessions.items()
        if s.get('last_active', 0) < cutoff
    ]
    for sid in expired:
        del _sessions[sid]
    if expired:
        logger.info('清理 %d 个过期会话', len(expired))


def create_session():
    """
    创建新的对话会话。

    返回:
        str — 新的 session_id（UUID4 hex，32位）
    """
    session_id = uuid.uuid4().hex
    with _lock:
        _cleanup_expired()
        _sessions[session_id] = {
            'messages': [],
            'created_at': _now(),
            'last_active': _now(),
        }
    logger.info('创建会话: %s', session_id)
    return session_id


def session_exists(session_id):
    """检查会话是否存在。"""
    with _lock:
        return session_id in _sessions


def add_message(session_id, role, content):
    """
    向会话添加一条消息。

    参数:
        session_id: str
        role: str — 'user' | 'assistant' | 'system'
        content: str — 消息内容
    """
    with _lock:
        _cleanup_expired()
        if session_id not in _sessions:
            # 会话不存在则自动创建
            _sessions[session_id] = {
                'messages': [],
                'created_at': _now(),
                'last_active': _now(),
            }
            logger.info('自动创建会话: %s', session_id)

        session = _sessions[session_id]
        session['messages'].append({
            'role': role,
            'content': content,
            'time': datetime.now().isoformat(),
        })
        session['last_active'] = _now()

        # 超过最大消息数时，移除最早的消息（但保留 system prompt 如果存在的话）
        if len(session['messages']) > MAX_MESSAGES_PER_SESSION:
            # 保留最近的消息，但如果第一条是 system 则跳过它
            overflow = len(session['messages']) - MAX_MESSAGES_PER_SESSION
            session['messages'] = session['messages'][overflow:]


def get_context(session_id, max_messages=None):
    """
    获取会话的消息上下文，用于发送给 LLM。

    参数:
        session_id: str
        max_messages: int | None — 最多取最近 N 条消息，None 则取全部

    返回:
        list[dict] — [{"role": "user"|"assistant", "content": "..."}, ...]
    """
    with _lock:
        if session_id not in _sessions:
            return []
        session = _sessions[session_id]
        session['last_active'] = _now()
        messages = session['messages']
        if max_messages and len(messages) > max_messages:
            messages = messages[-max_messages:]
        # 只返回 role 和 content，不暴露内部时间戳
        return [{'role': m['role'], 'content': m['content']} for m in messages]


def get_session_info(session_id):
    """
    获取会话信息。

    返回:
        dict | None — {session_id, message_count, created_at, last_active}
    """
    with _lock:
        if session_id not in _sessions:
            return None
        s = _sessions[session_id]
        return {
            'session_id': session_id,
            'message_count': len(s['messages']),
            'created_at': datetime.fromtimestamp(s['created_at']).isoformat(),
            'last_active': datetime.fromtimestamp(s['last_active']).isoformat(),
        }


def list_sessions():
    """
    列出所有活跃会话。

    返回:
        list[dict]
    """
    with _lock:
        _cleanup_expired()
        result = []
        for sid, s in _sessions.items():
            result.append({
                'session_id': sid,
                'message_count': len(s['messages']),
                'created_at': datetime.fromtimestamp(s['created_at']).isoformat(),
                'last_active': datetime.fromtimestamp(s['last_active']).isoformat(),
            })
        return sorted(result, key=lambda x: x['last_active'], reverse=True)


def clear_session(session_id):
    """
    清空会话消息（保留会话本身）。

    返回:
        int — 清除的消息数量
    """
    with _lock:
        if session_id not in _sessions:
            return 0
        count = len(_sessions[session_id]['messages'])
        _sessions[session_id]['messages'] = []
        _sessions[session_id]['last_active'] = _now()
        return count


def delete_session(session_id):
    """
    删除整个会话。

    返回:
        bool — 是否成功删除
    """
    with _lock:
        if session_id in _sessions:
            del _sessions[session_id]
            return True
        return False


def get_session_count():
    """获取当前活跃会话数。"""
    with _lock:
        _cleanup_expired()
        return len(_sessions)
