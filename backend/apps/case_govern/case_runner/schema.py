# -*- coding: utf-8 -*-
"""
操作 JSON 校验：白名单 action + 参数校验，拦截非法指令。
"""
import re

# 白名单动作
ALLOWED_ACTIONS = ('goto', 'click', 'type', 'wait', 'assert', 'screenshot', 'press')

# assert 的 mode 白名单
ALLOWED_ASSERT_MODES = ('contains', 'has_data', 'clickable', 'exists')


def _clean_json_text(text):
    """从 AI 回复里提取 JSON（去除可能的 ```json ... ``` 包裹）。"""
    if not text:
        return None
    s = text.strip()
    # 去掉 ```json ... ``` 代码块
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', s, re.DOTALL)
    if m:
        return m.group(1)
    # 直接取第一个 { 到最后一个 }
    start = s.find('{')
    end = s.rfind('}')
    if start != -1 and end != -1 and end > start:
        return s[start:end + 1]
    return None


def parse_steps_json(text):
    """解析 AI 返回的操作 JSON 为 steps 列表；失败返回 (None, 错误信息)。"""
    import json
    clean = _clean_json_text(text)
    if not clean:
        return None, '未找到有效的 JSON'
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        return None, f'JSON 解析失败：{e}'
    steps = data.get('steps') if isinstance(data, dict) else None
    if not isinstance(steps, list) or not steps:
        return None, '缺少 steps 数组'
    return steps, None


def validate_step(step, index):
    """校验单个步骤，返回 (是否合法, 错误信息)。"""
    if not isinstance(step, dict):
        return False, f'步骤{index}不是对象'
    action = step.get('action')
    if action not in ALLOWED_ACTIONS:
        return False, f'步骤{index} action 非法：{action}'
    if action == 'goto':
        if not (step.get('url') or step.get('selector')):
            return False, f'步骤{index} goto 缺少 url'
    elif action in ('click', 'type'):
        if not step.get('selector'):
            return False, f'步骤{index} {action} 缺少 selector'
    elif action == 'assert':
        if not step.get('selector'):
            return False, f'步骤{index} assert 缺少 selector'
        mode = step.get('mode', 'exists')
        if mode not in ALLOWED_ASSERT_MODES:
            return False, f'步骤{index} assert mode 非法：{mode}'
        if mode == 'contains' and not step.get('text'):
            return False, f'步骤{index} assert contains 缺少 text'
    return True, None
