# -*- coding: utf-8 -*-
"""页面回归：按已入库（已人工确认）的页面结构在浏览器中回放，不调用 AI，只报告失败。

入口 run_regression(target, inputs=None, upload_file_path=None)，target 可以是任意层级：
  - '达人管理'                      → 回归该模块下全部页面及其全部操作（操作需要的参数须在 inputs 中提供）；
  - '达人管理--上传达人'            → 回归该页面（含进入链）；
  - '达人管理--上传达人--单个上传'  → 回归该操作（含进入链），录入值来自 inputs；
  - inputs 形如 {"昵称": "ZnYan", "筛选": {"达人昵称": "ZnYan"}}。

每个目标在独立的浏览器上下文中从起始页重新执行，互不影响；失败只记录，不重新探索，不修改 JSON。
"""
import os
from datetime import datetime

from . import node_cache as nc


def _chain_to(pages, name):
    """沿 enter.from 回溯到入口页，返回 [(页面名, 页面数据)]（从入口到 name）。"""
    chain, seen = [], set()
    while name in pages and name not in seen:
        seen.add(name)
        chain.append((name, pages[name]))
        name = (pages[name].get('enter') or {}).get('from')
    chain.reverse()
    return chain


def _resolve(data, module, segs):
    """把目标解析为回归项列表：[(标签, 进入链, 操作名或 None)]。无法解析时抛 ValueError。"""
    pages = data['pages']
    if len(segs) == 1:
        items = []
        for name, pg in pages.items():
            chain = _chain_to(pages, name)
            items.append(('--'.join([module, name]), chain, None))
            for op_name in pg.get('operations') or {}:
                items.append(('--'.join([module, name, op_name]), chain, op_name))
        return items

    chain, covered = nc.lookup(segs)
    if not chain:
        raise ValueError(f'目标「{"--".join(segs)}」在模块「{module}」中未找到页面')
    label = '--'.join(segs)
    remaining = segs[covered:]
    if not remaining:
        return [(label, chain, None)]
    if len(remaining) == 1 and remaining[0] in (chain[-1][1].get('operations') or {}):
        return [(label, chain, remaining[0])]
    raise ValueError(f'目标「{label}」中的「{"--".join(remaining)}」不是已入库的操作')


def _screenshot(page, label):
    try:
        from base_utils.logger_base import _log_dir
        path = os.path.join(_log_dir, f'regression_{datetime.now():%Y%m%d_%H%M%S}_{abs(hash(label)) % 10000}.png')
        page.screenshot(path=path)
        return path
    except Exception:  # noqa: BLE001
        return None


def _run_one(browser, label, chain, op_name, inputs, marker, upload_file_path):
    from .explorer import ExploreError, replay_page, replay_operation, replay_filters
    from .runner import DEFAULT_START_URL, _inject_explore_login

    # 无痕模式（项目约定）：每次新建独立 context，不复用 cookie / localStorage / storage_state。
    # 不要改成 launch_persistent_context 或传入已保存的登录态。
    context = browser.new_context()
    page = None
    try:
        _inject_explore_login(context, DEFAULT_START_URL)
        page = context.new_page()
        page.goto(DEFAULT_START_URL, wait_until='domcontentloaded', timeout=30000)
        for name, pg in chain:
            replay_page(page, name, pg, marker, upload_file_path=upload_file_path)
        leaf = chain[-1][1] if chain else {}
        if inputs.get('筛选') and leaf.get('filters'):
            replay_filters(page, leaf, inputs['筛选'], marker)
        if op_name:
            op = leaf['operations'][op_name]
            missing = nc.required_inputs(op) - set(k for k in inputs if k != '筛选')
            if missing:
                raise ExploreError(f'缺少调用参数：{"、".join(sorted(missing))}')
            replay_operation(page, op_name, op, marker, inputs, upload_file_path=upload_file_path)
        return {'target': label, 'ok': True, 'error': None, 'screenshot': None}
    except Exception as e:  # noqa: BLE001 回归只记录失败，不中断其它目标
        shot = _screenshot(page, label) if page is not None else None
        return {'target': label, 'ok': False, 'error': str(e), 'screenshot': shot}
    finally:
        context.close()


def run_regression(target, inputs=None, upload_file_path=None):
    """执行回归，返回报告：
      {'target', 'total', 'passed', 'failed', 'error', 'results': [{'target', 'ok', 'error', 'screenshot'}]}
    只读正式库；没有入库的模块直接报错，提示先人工确认草稿。
    """
    from .explorer import explore_logger
    from .runner import UPLOAD_FILE_PATH, _gen_unique_name, _prepare_upload_file

    inputs = dict(inputs or {})
    segs = nc.parse_target(target)
    report = {'target': target, 'total': 0, 'passed': 0, 'failed': 0, 'error': None, 'results': []}
    if not segs:
        report['error'] = '回归目标为空'
        return report
    module = segs[0]
    data = nc.load_module(module)
    if data is None:
        report['error'] = f'模块「{module}」未入库（请先人工确认草稿，或确认探索结果已入库）'
        return report
    try:
        items = _resolve(data, module, segs)
    except ValueError as e:
        report['error'] = str(e)
        return report

    marker = _gen_unique_name()
    upload = (upload_file_path if upload_file_path is not None else UPLOAD_FILE_PATH or '').strip()
    if upload:
        ok, prepared = _prepare_upload_file(upload, unique_name=marker)
        if not ok:
            report['error'] = prepared
            return report
        upload = prepared

    from playwright.sync_api import sync_playwright
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for label, chain, op_name in items:
                results.append(_run_one(browser, label, chain, op_name, inputs, marker, upload))
        finally:
            browser.close()

    report['results'] = results
    report['total'] = len(results)
    report['passed'] = sum(1 for r in results if r['ok'])
    report['failed'] = report['total'] - report['passed']
    for r in results:
        if not r['ok']:
            explore_logger.error('[页面回归] 失败：{}，{}', r['target'], r['error'])
    explore_logger.info('[页面回归] {}：共 {}，通过 {}，失败 {}', target, report['total'],
                        report['passed'], report['failed'])
    return report
