# -*- coding: utf-8 -*-
"""
AI 探索 → 生成模块 JSON。

流程：
  1. 调用 runner.run_explore（AI 在真实页面上按文字要求查找元素并完成目标）；
  2. 探索成功后，把记录下来的页面链转换为模块 JSON 结构；
  3. 写入指定路径。已有 JSON 中人工补充的 filters、operations 的 data 保留，不被覆盖。
"""
import os

from apps.case_govern.case_runner import node_cache as nc
from apps.case_govern.case_runner.runner import run_explore

from .patrol_core import load_json, save_json

# 人工维护的字段，探索重新生成时保留
_KEEP_PAGE_KEYS = ('filters',)
_KEEP_OP_KEYS = ('data',)


def _carry_manual_fields(new_pages, old_pages):
    for name, old in old_pages.items():
        target = new_pages.get(name)
        if target is None:
            continue
        for key in _KEEP_PAGE_KEYS:
            if key in old and key not in target:
                target[key] = old[key]
        for op_name, old_op in (old.get('operations') or {}).items():
            new_op = (target.get('operations') or {}).get(op_name)
            if new_op is not None:
                for key in _KEEP_OP_KEYS:
                    if key in old_op:
                        new_op[key] = old_op[key]


def explore_to_json(goal, out_path, upload_file_path=None, on_progress=None):
    """探索并生成模块 JSON。成功返回 (True, out_path, None)；失败返回 (False, None, 错误原因)。"""
    captured = {}

    def on_recorded(path, parent_name, parent_depth, pages):
        captured.update(path=path, pages=pages, parent_name=parent_name, parent_depth=parent_depth)

    result = run_explore(goal, upload_file_path=upload_file_path, on_progress=on_progress,
                         on_recorded=on_recorded)
    if result.get('error'):
        return False, None, result['error']
    if 'pages' not in captured:
        return False, None, '探索完成但未记录到页面结构，请检查目标描述是否包含层级（如 达人管理--上传达人--单个上传）'

    path = captured['path']
    data = {'module': path[0], 'pages': {}}
    nc.build_recorded(data, path, captured['parent_name'], captured['parent_depth'], captured['pages'])

    if os.path.isfile(out_path):
        _carry_manual_fields(data['pages'], load_json(out_path)['pages'])
    save_json(out_path, data)
    return True, out_path, None
