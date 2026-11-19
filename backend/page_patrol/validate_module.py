# -*- coding: utf-8 -*-
"""
模块 JSON 静态校验（不打开浏览器、不调用 AI）。

检查两类问题：
  1. 结构：对照 schema/module.schema.json 的字段、类型、枚举（纯 Python 实现，不新增依赖）；
  2. 语义：引用关系与约定是否成立，例如：
     - children / enter.from 指向的页面必须存在，且不能有环；
     - 操作的 ${inputs.X} 必须在该操作的 inputs 中声明；
     - 筛选 fields 的 action 必须是 type/click；
     - write 类操作必须有 verify，且 verify 或录入值里要包含 {{user_name}}（唯一标识）；
     - destructive 类操作禁止进入自动生成流程，这里直接报错；
     - 没有 goals 的页面无法被 target 直接指向（警告）。

用法：
  venv/bin/python page_patrol/validate_module.py page_patrol/examples/达人管理.example.json
返回码：0 通过（可有警告），1 存在错误。
"""
import json
import os
import re
import sys

ACTION_NAMES = {'click', 'type', 'upload', 'select_first', 'press', 'scroll', 'wait', 'repeat', 'recognize', 'select', 'click_row', 'table_select', 'table_type', 'table_upload', 'click_css'}
ACTION_KEYS = {'action', 'label', 'value', 'text', 'key', 'direction', 'px', 'ms',
               'over', 'steps', 'nth', 'except_last', 'timeout_ms', 'row', 'column', 'selector'}
DATA_REF = re.compile(r'\$\{data\.([^}]+)\}')
PAGE_KEYS = {'anchor', 'enter', 'actions', 'verify', 'goals', 'children', 'filters', 'operations'}
OP_KINDS = {'read', 'write', 'destructive'}
OP_KEYS = {'kind', 'inputs', 'enter', 'steps', 'verify', 'verify_row', 'data'}
INPUT_REF = re.compile(r'\$\{inputs\.([^}]+)\}')
MARKER = '{{user_name}}'
ENTRY = '首页'


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append(f'[{where}] {msg}')

    def warn(self, where, msg):
        self.warnings.append(f'[{where}] {msg}')


def _check_action(rep, where, a):
    if not isinstance(a, dict):
        rep.err(where, '动作必须是对象')
        return
    extra = set(a) - ACTION_KEYS
    if extra:
        rep.err(where, f'动作含未知字段：{"、".join(sorted(extra))}')
    if a.get('action') not in ACTION_NAMES:
        rep.err(where, f'动作类型非法：{a.get("action")!r}，应为 {"/".join(sorted(ACTION_NAMES))}')
    if a.get('action') == 'repeat':
        if not a.get('over'):
            rep.err(where, 'repeat 必须声明 over（循环的 data 键名）')
        _check_action_list(rep, f'{where}.steps', a.get('steps', []))
        if not a.get('steps'):
            rep.err(where, 'repeat 的 steps 不能为空')


def _check_action_list(rep, where, items):
    if not isinstance(items, list):
        rep.err(where, '应为数组')
        return
    for i, a in enumerate(items):
        _check_action(rep, f'{where}[{i}]', a)


def _structure(rep, data):
    if not isinstance(data.get('module'), str) or not data.get('module'):
        rep.err('根', 'module 必须是非空字符串')
    if 'run' in data:
        rep.err('根', '模块文件不应包含 run 块，执行参数请放到用例文件（cases）中')
    unknown = set(data) - {'module', 'pages'}
    if unknown:
        rep.err('根', f'含未知顶层字段：{"、".join(sorted(unknown))}')
    pages = data.get('pages')
    if not isinstance(pages, dict) or not pages:
        rep.err('根', 'pages 必须是非空对象')
        return {}

    for name, pg in pages.items():
        w = f'页面「{name}」'
        if not isinstance(pg, dict):
            rep.err(w, '页面必须是对象')
            continue
        unknown = set(pg) - PAGE_KEYS
        if unknown:
            rep.err(w, f'含未知字段：{"、".join(sorted(unknown))}')
        for key in ('anchor', 'enter', 'actions', 'verify', 'goals', 'children'):
            if key not in pg:
                rep.err(w, f'缺少字段 {key}')
        if 'anchor' in pg and pg['anchor'] is not None and not isinstance(pg['anchor'], str):
            rep.err(w, 'anchor 应为字符串或 null')
        enter = pg.get('enter')
        if isinstance(enter, dict):
            if not isinstance(enter.get('from'), str) or not enter.get('from'):
                rep.err(w, 'enter.from 必须是非空字符串')
            _check_action_list(rep, f'{w} enter.actions', enter.get('actions', []))
        elif enter is not None:
            rep.err(w, 'enter 必须是对象')
        _check_action_list(rep, f'{w} actions', pg.get('actions', []))
        for key in ('goals', 'children'):
            if not isinstance(pg.get(key, []), list):
                rep.err(w, f'{key} 应为数组')

        flt = pg.get('filters')
        if flt is not None:
            if not isinstance(flt, dict) or not isinstance(flt.get('fields'), dict):
                rep.err(w, 'filters 必须包含 fields 对象')
            else:
                for fname, spec in flt['fields'].items():
                    _check_action(rep, f'{w} filters.fields[{fname}]', spec)
                    if isinstance(spec, dict) and spec.get('action') not in ('type', 'click'):
                        rep.err(w, f'筛选字段「{fname}」的动作应为 type 或 click')
                for k in ('submit', 'reset'):
                    if k in flt:
                        _check_action(rep, f'{w} filters.{k}', flt[k])

        for op_name, op in (pg.get('operations') or {}).items():
            _check_operation(rep, f'{w} 操作「{op_name}」', op)
    return pages


def _check_operation(rep, w, op):
    if not isinstance(op, dict):
        rep.err(w, '操作必须是对象')
        return
    unknown = set(op) - OP_KEYS
    if unknown:
        rep.err(w, f'含未知字段：{"、".join(sorted(unknown))}')
    if op.get('kind') not in OP_KINDS:
        rep.err(w, f'缺少或非法的 kind（应为 {"/".join(sorted(OP_KINDS))}）')
    if op.get('kind') == 'destructive':
        rep.err(w, 'destructive 操作禁止进入自动生成流程，请人工编写并单独审批')
    if not isinstance(op.get('inputs'), list):
        rep.err(w, 'inputs 必须是数组（即使为空）')
    _check_action_list(rep, f'{w} enter', op.get('enter', []))
    _check_action_list(rep, f'{w} steps', op.get('steps', []))
    if not op.get('steps'):
        rep.err(w, 'steps 不能为空')


def _walk(actions):
    for a in actions or []:
        if isinstance(a, dict):
            yield a
            if a.get('action') == 'repeat':
                yield from _walk(a.get('steps') or [])


def _semantics(rep, pages):
    # 1. 引用关系
    for name, pg in pages.items():
        w = f'页面「{name}」'
        src = (pg.get('enter') or {}).get('from')
        if src and src != ENTRY and src not in pages:
            rep.err(w, f'enter.from 指向的页面「{src}」不存在')
        for c in pg.get('children') or []:
            if c not in pages:
                rep.err(w, f'children 中的「{c}」不存在')
            elif (pages[c].get('enter') or {}).get('from') != name:
                rep.warn(w, f'children 含「{c}」，但它的 enter.from 不是「{name}」')
        if not pg.get('goals') and not pg.get('operations'):
            rep.warn(w, '没有 goals，case 的 target 无法直接指向该页面')

    # 2. 进入链无环、可回溯到入口
    for name in pages:
        seen, cur = set(), name
        while cur in pages:
            if cur in seen:
                rep.err(f'页面「{name}」', '进入链存在环（enter.from 循环）')
                break
            seen.add(cur)
            cur = (pages[cur].get('enter') or {}).get('from')
            if cur == ENTRY:
                break

    # 3. 操作：inputs 声明与引用一致；写操作有唯一标识校验
    for name, pg in pages.items():
        for op_name, op in (pg.get('operations') or {}).items():
            w = f'页面「{name}」 操作「{op_name}」'
            if not isinstance(op, dict):
                continue
            declared = set(op.get('inputs') or [])
            text = json.dumps(op, ensure_ascii=False)
            referenced = set(INPUT_REF.findall(text))
            for k in sorted(referenced - declared):
                rep.err(w, f'引用了未声明的参数 ${{inputs.{k}}}，请加入 inputs')
            for k in sorted(declared - referenced):
                rep.warn(w, f'声明的参数「{k}」未在步骤中使用')
            data = op.get('data') or {}
            for ref in sorted(set(DATA_REF.findall(text))):
                cur, ok = data, True
                for key in ref.split('.'):
                    if isinstance(cur, dict) and key in cur:
                        cur = cur[key]
                    else:
                        ok = False
                        break
                if not ok:
                    rep.err(w, f'引用了 data 中不存在的字段 ${{data.{ref}}}')
            for rep_act in _walk(op.get('steps') or []):
                if rep_act.get('action') == 'repeat':
                    items = data
                    for key in str(rep_act.get('over', '')).split('.'):
                        items = items.get(key) if isinstance(items, dict) else None
                    if not isinstance(items, list):
                        rep.err(w, f'repeat 的 over「{rep_act.get("over")}」在 data 中必须是数组')
            if op.get('kind') == 'write':
                if not op.get('verify'):
                    rep.err(w, 'write 操作必须声明 verify，否则无法确认数据已写入')
                uses_marker = MARKER in text or bool(INPUT_REF.search(op.get('verify') or ''))
                if not uses_marker:
                    rep.err(w, 'write 操作的录入值或 verify 中必须包含 {{user_name}} 或 ${inputs.X}，用于区分本次数据')
                if op.get('verify') and not (MARKER in op['verify'] or INPUT_REF.search(op['verify'])):
                    rep.warn(w, 'verify 未包含 {{user_name}} 或 ${inputs.X}，可能误判历史数据')


def validate_file(path):
    rep = Report()
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        rep.err('文件', f'无法读取或不是合法 JSON：{e}')
        return rep
    if not isinstance(data, dict):
        rep.err('根', '顶层必须是对象')
        return rep
    pages = _structure(rep, data)
    if pages:
        _semantics(rep, pages)
    return rep


def main(argv):
    if not argv:
        print('用法：validate_module.py <模块JSON路径> [更多路径...]')
        return 2
    failed = False
    for path in argv:
        rep = validate_file(path)
        name = os.path.basename(path)
        print(f'== {name}')
        for e in rep.errors:
            print(f'  ❌ {e}')
        for w in rep.warnings:
            print(f'  ⚠️  {w}')
        if not rep.errors and not rep.warnings:
            print('  ✅ 通过')
        elif not rep.errors:
            print('  ✅ 通过（有警告）')
        failed = failed or bool(rep.errors)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
