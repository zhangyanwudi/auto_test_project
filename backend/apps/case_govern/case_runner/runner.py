# -*- coding: utf-8 -*-
"""
巡检试运行编排：AI 自主探索 → 反推规范 → 报告。

流程（agentic 探索，而不是盲写规范）：
  1. 从用户描述提取起始 URL；
  2. 注入巡检账号登录态（默认 zhangyan02195@***.com），避免访问 SSO 站点被重定向到登录页；
  3. explorer.run_explore_loop 自主探索：AI 观察页面 → 决策 → 执行 → 失败回喂重试；
  4. 探索成功后用真实动作序列反推「节点规范草稿」，失败则返回卡点 + 日志路径。

批量上传类巡检：执行前把 UPLOAD_FILE_PATH 改成要上传的本地文件绝对路径，
或调用 run_explore(user_description, upload_file_path='xxx') 显式传入。
"""
import json
import os
import re

from .step_logger import StepLogger

# 批量上传模板路径（相对 backend 目录）。每次执行上传类巡检前，
# 会自动把模板里的 {{user_name}} 占位符替换成唯一名（auto_+时间戳）生成副本再上传。
UPLOAD_FILE_PATH = "data/auto_file/达人批量上传模板.xlsx"

# 模板里要替换成唯一名的占位符
UPLOAD_FILE_REPLACE_VAR = "{{user_name}}"

# 巡检默认起始页面地址：用户描述未带 URL 时，默认从这里开始巡检
DEFAULT_START_URL = "https://marketing-test.youxi123.com/"

# 巡检执行器注入登录态用的默认账号（拉取 token 时传的邮箱，须为完整真实邮箱）
EXPLORE_ACCOUNT_EMAIL = "zhangyan02195@hungrystudio.com"


def _gen_unique_name():
    """生成唯一达人名：auto_ + 年月日时分秒（如 auto_20261112153045），避免多次上传重名。"""
    from datetime import datetime
    return 'auto_' + datetime.now().strftime('%Y%m%d%H%M%S')


def _prepare_upload_file(template_path):
    """准备上传文件：把模板里的 {{user_name}} 替换成唯一名，生成唯一副本。

    - 模板含 UPLOAD_FILE_REPLACE_VAR 占位符 → 替换成唯一名，副本存到模板同目录 generated/ 下；
    - 模板不含占位符 → 视为已准备好的文件，直接返回其绝对路径；
    - 相对路径以 backend（settings.BASE_DIR）为基准转绝对路径。

    :return: (ok, path|error_msg)
    """
    import openpyxl
    from django.conf import settings

    base = str(settings.BASE_DIR)
    abs_template = template_path if os.path.isabs(template_path) else os.path.join(base, template_path)
    if not os.path.isfile(abs_template):
        return False, f'上传文件不存在：{abs_template}'

    wb = openpyxl.load_workbook(abs_template)
    try:
        has_var = any(
            isinstance(c.value, str) and UPLOAD_FILE_REPLACE_VAR in c.value
            for ws in wb.worksheets for row in ws.iter_rows() for c in row
        )
        if not has_var:
            return True, abs_template

        unique_name = _gen_unique_name()
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and UPLOAD_FILE_REPLACE_VAR in c.value:
                        c.value = c.value.replace(UPLOAD_FILE_REPLACE_VAR, unique_name)

        out_dir = os.path.join(os.path.dirname(abs_template), 'generated')
        os.makedirs(out_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(abs_template))[0]
        out_path = os.path.join(out_dir, f'{stem}_{unique_name}.xlsx')
        wb.save(out_path)
        return True, out_path
    finally:
        wb.close()


def _call_ai(messages):
    """调用 AI 网关，返回回复文本。"""
    from apps.ai_helper.gateway import call_agent_gateway
    return call_agent_gateway(messages)


def _extract_start_url(user_description):
    """从用户描述里提取起始 URL（第一个 http 开头的 token）。"""
    m = re.search(r'https?://\S+', user_description or '')
    if not m:
        return None
    return m.group(0).rstrip('，。；;、,>）)')


def _describe_action(a):
    """把单个探索动作转成「可读中文描述」，供报告展示（如「点击 达人管理」）。

    click/type/upload 优先用执行时补上的 label（元素文字/字段名），
    否则回退到 ref/url/text；wait 展示等待时长。
    """
    action = a.get('action', '')
    label = (a.get('label') or '').strip()

    if action == 'click':
        name = label or f'元素(ref={a.get("ref")})'
        return f'点击 {name}'
    if action == 'type':
        name = label or f'输入框(ref={a.get("ref")})'
        text = a.get('text', '')
        return f'输入 {name} 为 {text}' if text else f'输入 {name}'
    if action == 'upload':
        name = label or '文件'
        return f'上传 {name}'
    if action == 'press':
        name = label or ''
        key = a.get('key', 'Enter')
        return f'按键 {name} {key}' if name else f'按键 {key}'
    if action == 'wait':
        ms = a.get('ms')
        if ms is None:
            try:
                ms = int(a.get('text'))
            except (TypeError, ValueError):
                ms = None
        secs = f'{ms / 1000:g}秒' if ms else ''
        return f'等待 {secs}' if secs else '等待'
    if action == 'goto':
        return f'打开 {a.get("url", "")}'
    return action or '操作'


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
        f'- {_describe_action(a)}'
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


def run_explore(user_description, upload_file_path=None, on_progress=None):
    """完整试运行：提取 URL → 自主探索 → 反推规范 → 返回报告。

    :param on_progress: 探索过程中每步关键动作执行后回调 on_progress(text)，用于实时回报进度。

    流程（agentic 探索，而不是盲写规范）：
      1. 从用户描述提取起始 URL，未提供则默认用 DEFAULT_START_URL（基建平台首页）；
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
        # 用户没提供 URL 时，默认从巡检基建平台首页开始
        start_url = DEFAULT_START_URL

    # 上传文件路径：优先用调用方传入的，否则回退到模块级常量 UPLOAD_FILE_PATH
    if upload_file_path is None:
        upload_file_path = UPLOAD_FILE_PATH
    upload_file_path = (upload_file_path or '').strip()

    # 若指定了模板，每次执行前替换 {{user_name}} 为唯一名，生成唯一副本再上传
    if upload_file_path:
        ok, prepared = _prepare_upload_file(upload_file_path)
        if not ok:
            return _empty_result(error=prepared, log_path=log_path)
        upload_file_path = prepared

    step_logger = StepLogger(case_name=start_url)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            _inject_explore_login(context, start_url)
            page = context.new_page()
            page.goto(start_url, wait_until='domcontentloaded', timeout=30000)

            success, actions, note = run_explore_loop(
                page, user_description, upload_file_path=upload_file_path, start_url=start_url,
                on_progress=on_progress,
            )

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
        desc = _describe_action(a)
        steps_detail.append({
            'index': i, 'action': action, 'node_title': desc, 'node_type': 'step',
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
