# -*- coding: utf-8 -*-
"""
巡检试运行编排：AI 自主探索 → 反推规范 → 报告。

流程（agentic 探索，而不是盲写规范）：
  1. 从用户描述提取起始 URL；
  2. 注入巡检账号登录态（默认 zhangyan02195@***.com），避免访问 SSO 站点被重定向到登录页；
  3. explorer.run_explore_loop 自主探索：AI 观察页面 → 决策 → 执行 → 失败回喂重试；
  4. 探索成功后用真实动作序列反推「节点规范草稿」，失败则返回卡点 + 日志路径。
"""
import json
import re

from .prompts import build_explore_system_prompt
from .step_logger import StepLogger

# 巡检执行器注入登录态用的默认账号（拉取 token 时传的邮箱，须为完整真实邮箱）
EXPLORE_ACCOUNT_EMAIL = "zhangyan02195@hungrystudio.com"


def _call_ai(messages):
    """调用 AI 网关，返回回复文本。"""
    from apps.ai_helper.gateway import call_agent_gateway
    return call_agent_gateway(messages)


def generate_spec(user_description):
    """阶段一：根据用户描述生成「节点规范草稿」文本。

    注意：run_explore 已改为「探索成功后再反推规范」，不再依赖盲写的 generate_spec；
    此函数保留供需要时直接生成草稿预览使用。
    """
    messages = [
        {'role': 'system', 'content': build_explore_system_prompt()},
        {'role': 'user', 'content': user_description},
    ]
    reply = _call_ai(messages)
    return reply


def _extract_start_url(user_description):
    """从用户描述里提取起始 URL（第一个 http 开头的 token）。"""
    m = re.search(r'https?://\S+', user_description or '')
    if not m:
        return None
    return m.group(0).rstrip('，。；;、,>）)')



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


def _inject_explore_login(context, target_url):
    """给巡检页面注入登录态（localStorage），避免访问 SSO 站点被重定向到登录页。

    通过 context.add_init_script 在「每个文档创建、页面脚本运行前」注入，这样即使
    首次访问被 SSO 重定向，最终回到目标域时登录态也已在 localStorage 中就绪，
    前端路由守卫能直接读到 token 而不再二次跳转（旧实现先 goto 再 evaluate 写入，
    会与重定向竞态，导致写到 SSO 域、注入失败）。
    """
    from urllib.parse import urlparse
    from base_utils.logger_base import logger

    host = (urlparse(target_url).netloc or '').strip()
    if not host:
        logger.warning('巡检登录态注入跳过：无法从 URL 解析域名 {}', target_url)
        return False

    origin = f"https://{host}"

    # 1. 每次巡检都调用 get_user_token 拉取最新 token（该方法内部会用真实邮箱请求
    #    iam 接口，拿到当前有效的 token 与用户信息），再组装成登录态注入 localStorage
    try:
        from apis.server_api.kol_api import KolsysApi
        api = KolsysApi(is_debug=True)
        ok, info = api.get_user_token(EXPLORE_ACCOUNT_EMAIL, is_set_cache=False)
        if not ok:
            logger.error('巡检登录态注入：获取 token 失败，跳过注入：{}', info)
            return False
        values = api._build_auth_payload({'user': info.user})
    except Exception as e:  # noqa: BLE001
        logger.error('巡检登录态注入：获取 token 失败，跳过注入：{}', e)
        return False

    if not values:
        logger.warning('巡检登录态注入：token payload 为空，跳过注入')
        return False

    # 2. 序列化 payload（dict 值存成 JSON 字符串，与前端 JSON.parse 读取一致）
    serialized = {}
    for key, value in values.items():
        serialized[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value

    # 3. 注册 init script：仅当页面落在目标 origin 时才写入，避免污染 SSO 等其它域
    init_js = (
        "if (location.origin === %s) {"
        "  const d = %s;"
        "  for (const [k, v] of Object.entries(d)) { localStorage.setItem(k, v); }"
        "}"
    ) % (json.dumps(origin), json.dumps(serialized, ensure_ascii=False))
    try:
        context.add_init_script(init_js)
        logger.info('巡检登录态注入已注册，域名：{}，key 数：{}', host, len(serialized))
        return True
    except Exception as e:  # noqa: BLE001
        logger.error('巡检登录态注入：注册 init script 失败：{}', e)
        return False


def finalize_spec(goal, actions, start_url):
    """阶段三：探索成功后，把真实走通的动作序列反推成「节点规范草稿」文本。"""
    from .prompts import build_finalize_spec_prompt

    actions_text = '\n'.join(
        f'- {a.get("action")} ref={a.get("ref")} label={a.get("label", "")} text={a.get("text", "")} '
        f'ms={a.get("ms", "")} url={a.get("url", "")} key={a.get("key", "")}'
        for a in actions
    ) or '（无动作）'
    user = f'目标：{goal}\n起始页面：{start_url}\n实际执行成功的动作序列：\n{actions_text}'
    messages = [
        {'role': 'system', 'content': build_finalize_spec_prompt()},
        {'role': 'user', 'content': user},
    ]
    reply = _call_ai(messages)
    return reply


def _empty_result(spec='', error=None, log_path=''):
    return {'spec': spec, 'steps': [], 'passed': 0, 'failed': 0, 'total': 0,
            'error': error, 'log_path': log_path}


def run_explore(user_description):
    """完整试运行：提取 URL → 自主探索 → 反推规范 → 返回报告。

    流程（agentic 探索，而不是盲写规范）：
      1. 从用户描述提取起始 URL，无法提取则报错；
      2. 注入巡检账号登录态，goto 起始 URL；
      3. explorer.run_explore_loop 自主探索：AI 观察页面 → 决策 → 执行 → 失败回喂重试；
      4. 探索成功后用真实动作序列反推「节点规范草稿」；失败则返回失败卡点 + 日志路径。

    返回 dict:
      {
        'spec': str,                    # 节点规范草稿文本（探索成功后反推）
        'steps': [StepRunResult dict],  # 每步明细（探索动作 + 结果）
        'passed': int, 'failed': int, 'total': int,
        'error': str|None,              # 失败原因（探索失败/执行异常）
        'log_path': str,                # 探索日志文件路径，用于排查
      }
    """
    from .explorer import run_explore_loop, explore_logger

    # 日志文件路径：与 base_utils.logger_base 的 sink 一致，格式 logs/case_explore_YYYY-MM-DD.log
    import os
    from datetime import datetime
    from base_utils.logger_base import _log_dir
    log_path = os.path.join(_log_dir, f'case_explore_{datetime.now():%Y-%m-%d}.log')

    start_url = _extract_start_url(user_description)
    if not start_url:
        return _empty_result(error='用户描述中未找到页面地址（需含 http:// 或 https:// 开头的 URL）',
                             log_path=log_path)

    step_logger = StepLogger(case_name=start_url)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            _inject_explore_login(context, start_url)
            page = context.new_page()
            page.goto(start_url, wait_until='domcontentloaded', timeout=30000)

            success, actions, note = run_explore_loop(page, user_description)

            # 探索结束后的页面截图
            try:
                page.screenshot(path='/tmp/zy_explore_last.png')
            except Exception:  # noqa: BLE001
                pass

            if not success:
                browser.close()
                return _empty_result(error=f'AI 未能在页面上完成目标：{note}', log_path=log_path)

            # 探索成功 → 反推规范
            spec_text = finalize_spec(user_description, actions, start_url)
            browser.close()
    except Exception as e:  # noqa: BLE001
        explore_logger.error('[巡检探索] 执行器异常：{}', e)
        return _empty_result(error=f'执行器异常：{e}', log_path=log_path)

    # 把探索动作整理成每步明细（供报告展示，页面只显示最终结果）
    steps_detail = []
    passed = 0
    failed = 0
    for i, a in enumerate(actions, start=1):
        action = a.get('action', '')
        target = a.get('ref') if a.get('ref') is not None else (a.get('url') or a.get('text') or '')
        steps_detail.append({
            'index': i, 'action': action, 'node_title': '', 'node_type': 'step',
            'target': str(target), 'status': 'pass', 'message': '探索执行成功', 'cost_ms': 0,
        })
        passed += 1

    explore_logger.info('[巡检探索] 探索完成，共 {} 个动作，规范草稿长度 {}', passed, len(spec_text or ''))

    return {
        'spec': spec_text,
        'steps': steps_detail,
        'passed': passed,
        'failed': failed,
        'total': passed,
        'error': None,
        'log_path': log_path,
    }
