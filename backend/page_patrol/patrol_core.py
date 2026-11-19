# -*- coding: utf-8 -*-
"""
页面巡检执行核心：只读 JSON，按 JSON 在浏览器中回放，不调用 AI。

JSON 结构见 page_patrol 目录下的 *.json，核心字段：
  - module / pages：页面结构（由 explore.py 探索生成，或人工补充 filters）
  - run：本次执行参数
      target  目标路径，如 「达人管理--上传达人--单个上传」（页面层级 + 可选操作名）
      inputs  操作录入值，如 {"昵称": "{{user_name}}"}；步骤里的 ${inputs.昵称} 会替换为它
      filters 列表页筛选值，如 {"达人昵称": "ZnYan"}，只录入传入的字段，然后点击查询

调用前需先完成 django.setup()（由 page_patrol_task.py 负责）。
"""
import json
import os
import re
from datetime import datetime

from apps.case_govern.case_runner import node_cache as nc

PATROL_DIR = os.path.dirname(os.path.abspath(__file__))


def load_json(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get('pages'), dict) or not data.get('module'):
        raise ValueError(f'JSON 结构错误（需要 module 与 pages）：{path}')
    return data


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _page_depth(pg, segs):
    """页面 goals 覆盖目标路径的段数（goal 是 segs 的前缀时返回段数，否则 0）。"""
    best = 0
    for g in pg.get('goals') or []:
        gs = nc._segments(g)
        if gs and len(gs) <= len(segs) and segs[:len(gs)] == gs:
            best = max(best, len(gs))
    return best


def resolve(data, target):
    """解析目标 → (chain, op_name)。chain 为 [(页面名, 页面数据)]，从入口页到目标页面；op_name 可为 None。"""
    segs = nc._segments(target)
    if not segs:
        raise ValueError('run.target 为空')
    pages = data['pages']
    best_name, best = None, 0
    for name, pg in pages.items():
        d = _page_depth(pg, segs)
        if d > best:
            best_name, best = name, d
    if best_name is None:
        raise ValueError(f'目标「{target}」在 JSON 的 goals 中未找到页面')
    chain, seen, name = [], set(), best_name
    while name in pages and name not in seen:
        seen.add(name)
        chain.append((name, pages[name]))
        name = (pages[name].get('enter') or {}).get('from')
    chain.reverse()
    remaining = segs[best:]
    if not remaining:
        return chain, None
    if len(remaining) == 1 and remaining[0] in (chain[-1][1].get('operations') or {}):
        return chain, remaining[0]
    raise ValueError(f'目标中的「{"--".join(remaining)}」不是页面「{best_name}」下已定义的操作')


def validate(data):
    """检查 run 参数与 JSON 是否匹配，返回 (执行计划文字列表, 错误列表)。"""
    run = data.get('run') or {}
    errors, plan = [], []
    try:
        chain, op_name = resolve(data, run.get('target', ''))
    except ValueError as e:
        return plan, [str(e)]

    inputs = run.get('inputs') or {}
    filters = run.get('filters') or {}
    for name, pg in chain:
        enter = (pg.get('enter') or {}).get('actions') or []
        plan.append(f'页面「{name}」进入：' + (' → '.join(_label(a) for a in enter) or '（已在页面或无需跳转）'))

    filter_page = None
    if filters:
        for name, pg in chain:
            if pg.get('filters'):
                filter_page = (name, pg)
        if filter_page is None:
            errors.append('目标路径上的页面未定义 filters，无法录入筛选项')
        else:
            fields = filter_page[1]['filters'].get('fields') or {}
            for f in filters:
                if f not in fields:
                    errors.append(f'筛选项「{f}」在页面「{filter_page[0]}」的 filters.fields 中未定义')
            plan.append(f'页面「{filter_page[0]}」筛选：' + '、'.join(f'{k}={v}' for k, v in filters.items()) + ' → 查询')

    if op_name:
        op = chain[-1][1]['operations'][op_name]
        needed = nc.required_inputs(op.get('steps') or [])
        missing = sorted(k for k in needed if k not in inputs)
        if missing:
            errors.append('run.inputs 缺少：' + '、'.join(missing))
        plan.append(f'操作「{op_name}」：' + ' → '.join(_label(s) for s in op.get('steps') or []))
    return plan, errors


def _label(a):
    return f"{a.get('action')}({a.get('label') or a.get('key') or a.get('ms', '')})"


def _resolve_captured(items):
    """把事件回调里记录下来的原始报文解析成 {键: {'request': dict, 'response': dict}}。

    回调里只保存字符串（请求/响应体），解析放到回放结束后做。
    解析失败时保留原文片段，便于排查。
    """
    out = {}
    for it in items or []:
        key = it.get('key')
        if not key or key in out:
            continue
        # 请求体/响应体在事件回调里已读成字符串（回放结束后请求对象已失效，post_data 会返回 None）
        out[key] = _parse_body(it.get('request_text'), it.get('response_text'))
    return out


def _parse_body(req_text, resp_text):
    """把原始文本解析成 {'request': dict, 'response': dict}；解析失败保留原文，便于排查。"""
    entry = {}
    try:
        entry['request'] = json.loads(req_text) if req_text else {}
    except Exception:  # noqa: BLE001
        entry['request'] = {'_raw': (req_text or '')[:2000]}
    try:
        entry['response'] = json.loads(resp_text) if resp_text else {}
    except Exception:  # noqa: BLE001
        entry['response'] = {'_raw': (resp_text or '')[:2000]}
    return entry


def execute(data, upload_path=None, headless=False, post_check=None, response_watch=None):
    """按 JSON 回放。返回 {'ok', 'marker', 'error', 'screenshot'}。

    response_watch: {键名: URL 片段}，命中后记录该响应，解析好的 JSON 作为第二个参数传给
    post_check(page, captured)，供 case 从接口响应中取值（如订单ID）。
    """
    from playwright.sync_api import sync_playwright
    from apps.case_govern.case_runner.explorer import (
        ExploreError, replay_filters, replay_operation, replay_page,
    )
    from apps.case_govern.case_runner.runner import (
        DEFAULT_START_URL, UPLOAD_FILE_PATH, _gen_unique_name, _inject_explore_login, _prepare_upload_file,
    )

    run = data.get('run') or {}
    chain, op_name = resolve(data, run.get('target', ''))
    marker = _gen_unique_name()
    print(f'本次唯一标识：{marker}')

    upload = (upload_path or UPLOAD_FILE_PATH or '').strip()
    if upload:
        ok, prepared = _prepare_upload_file(upload, unique_name=marker)
        if not ok:
            return {'ok': False, 'marker': marker, 'error': prepared, 'screenshot': None}
        upload = prepared

    # 录入值里的 {{user_name}} 替换为本次唯一标识（占位符替换在回放前完成，之后 fill_values 不再处理）
    inputs = {k: str(v).replace(nc.NODE_MARKER, marker) for k, v in (run.get('inputs') or {}).items()}
    filters = run.get('filters') or {}

    with sync_playwright() as p:
        # 有界面时最大化窗口；no_viewport 让页面随窗口尺寸展示，不再是固定小视口
        browser = p.chromium.launch(
            headless=headless,
            args=[] if headless else ['--start-maximized'],
        )
        # 无痕模式（项目约定）：每次执行都新建独立 context，不复用 cookie / localStorage / 缓存，
        # 也不加载已登录的持久化 profile；登录态只由 _inject_explore_login 临时注入。
        # 注意：不要改成 launch_persistent_context 或复用 storage_state，否则会污染后续执行。
        context = browser.new_context(no_viewport=not headless)
        page = None
        captured_items = []
        try:
            _inject_explore_login(context, DEFAULT_START_URL)
            page = context.new_page()
            if response_watch:
                # 命中的请求/响应体必须在回调里立即读成字符串：
                # 回放结束后 Playwright 已释放 Request 对象，此时再读 post_data 只会得到 None。
                def _on_response(resp):
                    url = resp.url or ''
                    for key, frag in response_watch.items():
                        if not frag or frag not in url:
                            continue
                        if any(it.get('key') == key for it in captured_items):
                            break
                        try:
                            req_text = resp.request.post_data or ''
                        except Exception:  # noqa: BLE001
                            req_text = ''
                        try:
                            resp_text = resp.text()
                        except Exception:  # noqa: BLE001
                            resp_text = ''
                        if os.environ.get('PAGE_PATROL_DEBUG_RESP'):
                            print(f'[调试] 命中 {key}：{url} '
                                  f'post_data长度={len(req_text)} resp长度={len(resp_text)}', flush=True)
                        captured_items.append({'key': key, 'request_text': req_text,
                                               'response_text': resp_text})
                        break
                page.on('response', _on_response)
            page.goto(DEFAULT_START_URL, wait_until='domcontentloaded', timeout=30000)

            leaf_name, leaf = chain[-1]
            # 逐页回放：带 filters 的页面（列表页）在进入下一页之前完成筛选；
            # 叶子页在操作模式下只做进入与 anchor 校验，页内动作由操作承担
            for name, pg in chain:
                if name == leaf_name:
                    if op_name:
                        replay_page(page, name, dict(pg, actions=[], verify=None), marker, upload_file_path=upload)
                    else:
                        replay_page(page, name, pg, marker, upload_file_path=upload)
                else:
                    replay_page(page, name, pg, marker, upload_file_path=upload)
                print(f'✅ 进入页面「{name}」')
                if filters and pg.get('filters'):
                    replay_filters(page, pg, filters, marker)
                    print(f'✅ 页面「{name}」筛选查询：' + '、'.join(f'{k}={v}' for k, v in filters.items()))
                    filters = {}  # 只在第一个带 filters 的页面执行一次

            if op_name:
                op = leaf['operations'][op_name]
                replay_operation(page, op_name, op, marker, inputs, upload_file_path=upload)
                print(f'✅ 操作「{op_name}」执行成功')
            payload = None
            if post_check is not None:
                # 操作之后的业务校验（如订单状态、达人类型、产品组合）；失败则整个 case 失败
                captured = _resolve_captured(captured_items)
                for k, v in captured.items():
                    print(f'✅ 已捕获接口响应：{k}')
                good, msg, payload = post_check(page, captured)
                if not good:
                    return {'ok': False, 'marker': marker, 'error': msg, 'screenshot': _shot(page, marker)}
                print(f'✅ 校验通过：{msg}')
            return {'ok': True, 'marker': marker, 'error': None, 'screenshot': None, 'payload': payload}
        except ExploreError as e:
            return {'ok': False, 'marker': marker, 'error': str(e), 'screenshot': _shot(page, marker)}
        except Exception as e:  # noqa: BLE001
            return {'ok': False, 'marker': marker, 'error': f'异常：{e}', 'screenshot': _shot(page, marker)}
        finally:
            context.close()
            browser.close()


def _shot(page, marker):
    if page is None:
        return None
    from base_utils.logger_base import _log_dir
    path = os.path.join(_log_dir, f'page_patrol_fail_{datetime.now():%Y%m%d_%H%M%S}_{marker}.png')
    try:
        page.screenshot(path=path)
        return path
    except Exception:  # noqa: BLE001
        return None
