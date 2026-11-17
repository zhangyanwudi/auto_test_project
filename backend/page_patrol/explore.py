# -*- coding: utf-8 -*-
"""
AI 探索 → 生成页面巡检 JSON。

流程：
  1. 调用 runner.run_explore（AI 在真实页面上按文字要求查找元素并完成目标）；
  2. 探索成功后，把记录下来的页面链转换为 JSON 结构（不写草稿库）；
  3. 按 run 参数写入 run 块，并把已有 JSON 中人工补充的 filters 保留下来；
  4. 写入 page_patrol 目录，供人工检查后用 patrol_core 执行。

目标文字约定：
  - 层级用 -- 分隔，如「达人管理--上传达人--单个上传」；
  - 需要唯一数据的录入值写 {{user_name}}，执行时替换为本次唯一标识；
  - 目标里的录入值若与 run.inputs 中的字段名一致，会在 JSON 中替换为 ${inputs.字段名}。
"""
import os

from apps.case_govern.case_runner import node_cache as nc
from apps.case_govern.case_runner.runner import run_explore

from .patrol_core import load_json, save_json


def _parameterize(pages, run_inputs):
    """把操作里值为 {{user_name}} 的录入项替换为 ${inputs.字段名}。

    字段名优先取步骤的 label（须在 run_inputs 中）；label 不是字段名时（如页面占位文字「请输入」），
    退而取 run_inputs 中唯一一个值为 {{user_name}} 的字段。
    """
    marker_keys = [k for k, v in run_inputs.items() if v == nc.NODE_MARKER]
    for pg in pages.values():
        for op in (pg.get('operations') or {}).values():
            for step in op.get('steps') or []:
                if step.get('action') != 'type' or step.get('value') != nc.NODE_MARKER:
                    continue
                key = step.get('label') if step.get('label') in run_inputs else None
                if key is None and len(marker_keys) == 1:
                    key = marker_keys[0]
                if key is not None:
                    step['value'] = '${inputs.' + key + '}'


def _carry_manual_fields(new_pages, old_pages):
    """保留已有 JSON 中人工补充的 filters（如列表页的 filters.fields）。

    优先按页面名匹配；AI 命名不一致时，挂到目标页面祖先链上最近的、没有 goals 的页面（即列表页）。
    """
    for name, old in old_pages.items():
        if 'filters' not in old:
            continue
        if name in new_pages:
            new_pages[name].setdefault('filters', old['filters'])
            continue
        target = _list_page(new_pages)
        if target is not None:
            target.setdefault('filters', old['filters'])


def _list_page(pages):
    """从带 goals 的页面沿 enter.from 向上，找到第一个没有 goals 的祖先页面。"""
    leaf = next((n for n, p in pages.items() if p.get('goals')), None)
    seen = set()
    name = (pages.get(leaf) or {}).get('enter', {}).get('from') if leaf else None
    while name in pages and name not in seen:
        seen.add(name)
        if not pages[name].get('goals'):
            return pages[name]
        name = (pages[name].get('enter') or {}).get('from')
    return None


def explore_to_json(goal, out_path, run_inputs=None, run_filters=None, upload_file_path=None, on_progress=None):
    """探索并生成 JSON。成功返回 (True, out_path, None)；失败返回 (False, None, 错误原因)。"""
    run_inputs = dict(run_inputs or {})
    run_filters = dict(run_filters or {})
    captured = {}

    def on_recorded(path, parent_name, parent_depth, pages):
        captured['path'] = path
        captured['pages'] = pages
        captured['parent_name'] = parent_name
        captured['parent_depth'] = parent_depth

    result = run_explore(goal, upload_file_path=upload_file_path, on_progress=on_progress,
                         on_recorded=on_recorded)
    if result.get('error'):
        return False, None, result['error']
    if 'pages' not in captured:
        return False, None, '探索完成但未记录到页面结构，请检查目标描述是否包含层级（如 达人管理--上传达人--单个上传）'

    path = captured['path']
    module = path[0]
    data = {'module': module, 'pages': {}}
    nc.build_recorded(data, path, captured['parent_name'], captured['parent_depth'], captured['pages'])

    old = load_json(out_path) if os.path.isfile(out_path) else None
    _parameterize(data['pages'], run_inputs)
    if old:
        _carry_manual_fields(data['pages'], old['pages'])

    data['run'] = {
        'target': '--'.join(path),
        'inputs': run_inputs,
        'filters': run_filters,
    }
    save_json(out_path, data)
    return True, out_path, None
