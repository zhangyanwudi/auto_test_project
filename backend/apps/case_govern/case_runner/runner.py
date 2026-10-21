# -*- coding: utf-8 -*-
"""
巡检试运行编排：AI 生成规范 → Playwright 无痕执行 → 每步日志 → 报告。

执行前会拉取巡检账号（默认 zhangyan02195@***.com）的登录态注入 localStorage，
避免访问需要 SSO 登录的页面（如 marketing-test.youxi123.com）时被重定向到登录页。
"""
import json
import re

from .prompts import build_explore_system_prompt, build_translate_prompt
from .schema import parse_steps_json, validate_step
from .step_logger import StepLogger

# 巡检执行器注入登录态用的默认账号（拉取 token 时传的邮箱，须为完整真实邮箱）
EXPLORE_ACCOUNT_EMAIL = "zhangyan02195@hungrystudio.com"


def _call_ai(messages):
    """调用 AI 网关，返回回复文本。"""
    from apps.ai_helper.gateway import call_agent_gateway
    return call_agent_gateway(messages)


def generate_spec(user_description):
    """阶段一：根据用户描述生成「节点规范草稿」文本。"""
    messages = [
        {'role': 'system', 'content': build_explore_system_prompt()},
        {'role': 'user', 'content': user_description},
    ]
    reply = _call_ai(messages)
    return reply


def _parse_spec_to_nodes(spec_text):
    """把「节点规范草稿」文本解析成 precondition/step/result 三段。

    返回 dict: {"precondition": str, "steps": [str], "results": [str]}
    """
    pre = ''
    steps = []
    results = []
    section = None
    for line in spec_text.splitlines():
        s = line.strip()
        if '【precondition】' in s:
            section = 'pre'
            continue
        if '【step】' in s:
            section = 'step'
            continue
        if '【result】' in s:
            section = 'result'
            continue
        if not s or s.startswith('#') or s.startswith('```'):
            continue
        if section == 'pre':
            if s.startswith('http'):
                pre = s
        elif section == 'step':
            steps.append(s)
        elif section == 'result':
            results.append(s)
    return {'precondition': pre, 'steps': steps, 'results': results}


def _build_translate_messages(spec_text):
    """构建「翻译执行」的 AI 消息。"""
    return [
        {'role': 'system', 'content': build_translate_prompt()},
        {'role': 'user', 'content': spec_text},
    ]


def _merge_steps_with_nodes(steps, nodes):
    """把翻译出的 steps 与节点信息关联，便于日志里记录「来自哪个节点」。

    step 动作按顺序映射 nodes.steps；assert 动作按顺序映射 nodes.results。
    """
    step_texts = nodes['steps']
    result_texts = nodes['results']
    step_idx = 0
    result_idx = 0
    for s in steps:
        action = s.get('action')
        if action == 'assert' and result_idx < len(result_texts):
            s['node_title'] = result_texts[result_idx]
            s['node_type'] = 'result'
            result_idx += 1
        elif action in ('goto', 'click', 'type', 'wait', 'screenshot', 'press'):
            s['node_title'] = step_texts[step_idx] if step_idx < len(step_texts) else ''
            s['node_type'] = 'step'
            step_idx += 1
        else:
            s['node_title'] = ''
            s['node_type'] = ''
    return steps


def _inject_explore_login(page, target_url):
    """给巡检页面注入登录态（localStorage），避免访问 SSO 站点被重定向到登录页。

    先打开目标域名建立一个同源页面（否则无法写 localStorage），再拉取巡检账号
    的 token，把 7 个登录态 key 写进 localStorage，最后重新跳转到目标页面。
    """
    from urllib.parse import urlparse
    from base_utils.logger_base import logger

    host = (urlparse(target_url).netloc or '').strip()
    if not host:
        logger.warning('巡检登录态注入跳过：无法从 URL 解析域名 %s', target_url)
        return

    # 1. 先打开目标域名（任意路径），让浏览器建立该 origin 的页面
    origin = f"https://{host}/"
    try:
        page.goto(origin, wait_until='domcontentloaded', timeout=30000)
    except Exception as e:  # noqa: BLE001
        logger.warning('巡检登录态注入：打开 %s 失败（继续尝试注入）：%s', origin, e)

    # 2. 每次巡检都调用 get_user_token 拉取最新 token（该方法内部会用真实邮箱请求
    #    iam 接口，拿到当前有效的 token 与用户信息），再组装成登录态注入 localStorage
    try:
        from apis.server_api.kol_api import KolsysApi
        api = KolsysApi(is_debug=True)
        ok, info = api.get_user_token(EXPLORE_ACCOUNT_EMAIL, is_set_cache=False)
        if not ok:
            logger.error('巡检登录态注入：获取 token 失败，跳过注入：%s', info)
            return
        values = api._build_auth_payload({'user': info.user})
    except Exception as e:  # noqa: BLE001
        logger.error('巡检登录态注入：获取 token 失败，跳过注入：%s', e)
        return

    if not values:
        logger.warning('巡检登录态注入：token payload 为空，跳过注入')
        return

    # 3. 把登录态写入当前 origin 的 localStorage
    try:
        for key, value in values.items():
            page.evaluate("([k, v]) => localStorage.setItem(k, v)", [key, value])
        logger.info('巡检登录态注入成功，域名：%s，key 数：%d', host, len(values))
    except Exception as e:  # noqa: BLE001
        logger.error('巡检登录态注入：写入 localStorage 失败：%s', e)


def run_explore(user_description):
    """完整试运行：生成规范 → 翻译 → 执行 → 返回报告。

    返回 dict:
      {
        'spec': str,                    # 节点规范草稿文本
        'steps': [StepRunResult dict],  # 每步明细
        'passed': int, 'failed': int, 'total': int,
        'error': str|None,
      }
    """
    spec_text = generate_spec(user_description)
    nodes = _parse_spec_to_nodes(spec_text)

    if not nodes['precondition']:
        return {'spec': spec_text, 'steps': [], 'passed': 0, 'failed': 0, 'total': 0,
                'error': '规范草稿中未提取到页面地址（precondition 需含 http 开头的 URL）'}

    # 翻译成操作 JSON
    steps_json = _call_ai(_build_translate_messages(spec_text))
    steps, err = parse_steps_json(steps_json)
    if err:
        return {'spec': spec_text, 'steps': [], 'passed': 0, 'failed': 0, 'total': 0,
                'error': f'操作 JSON 解析失败：{err}，AI 返回：{steps_json[:500]}'}

    # 校验步骤
    for i, s in enumerate(steps, start=1):
        ok, msg = validate_step(s, i)
        if not ok:
            return {'spec': spec_text, 'steps': [], 'passed': 0, 'failed': 0, 'total': 0,
                    'error': msg}

    # 关联节点信息
    steps = _merge_steps_with_nodes(steps, nodes)

    # Playwright 无痕执行
    step_logger = StepLogger(case_name=nodes['precondition'])
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            # 注入巡检账号登录态到 localStorage，避免访问 SSO 站点被重定向到登录页
            _inject_explore_login(page, nodes['precondition'])
            from .interpreter import execute_steps
            ok, first_error = execute_steps(page, steps, step_logger)
            browser.close()
    except Exception as e:  # noqa: BLE001
        return {'spec': spec_text, 'steps': step_logger.to_list(),
                'passed': 0, 'failed': 0, 'total': 0, 'error': f'执行器异常：{e}'}

    passed, failed, total = step_logger.summary()
    return {
        'spec': spec_text,
        'steps': step_logger.to_list(),
        'passed': passed,
        'failed': failed,
        'total': total,
        'error': None if ok else first_error,
    }
