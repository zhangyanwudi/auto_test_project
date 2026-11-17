# -*- coding: utf-8 -*-
"""按页面分层的缓存：保存探索成功的页面结构、页面进入方式与页内操作。

目标描述里用 `--` 分隔层级，例如「达人管理--达人列表--单个上传，……」→ 路径 [达人管理, 达人列表, 单个上传]。
路径第一段是模块名；其余段由页面的 goals（页面层级）匹配，超出页面层级的段（如「单个上传」）作为操作名匹配。

存储：backend/data/explore_cache/<模块名>.json，每个模块一个文件：
    {
      "module": "达人管理",
      "pages": {
        "达人列表": {
          "anchor": "达人管理",
          "enter": {"from": "首页", "actions": [{"action": "click", "label": "达人管理"}]},
          "actions": [],
          "verify": null,
          "goals": ["达人管理--达人列表"],
          "children": ["上传达人"],
          "filters": {...},      # 可选：筛选项定义，按调用时传入的字段录入
          "operations": {...}    # 可选：带参数的操作模板（enter / steps / verify）
        }
      }
    }

- anchor：识别是否已在该页的文字；已在该页则跳过 enter；
- enter：从 from 页面进入本页的跳转动作，同一跳转只存一份；
- actions：进入页面后执行的页内固定动作；
- goals：页面层级路径（不含操作名），用于按目标路径查找页面；
- 动作只存文字 label，不存 ref；本次唯一标识存为 {{user_name}}，调用时传入的其它值存为 ${inputs.字段名}；
- 回放失败的页面及其子页面会被删除，从该处重新探索。
"""
import json
import os
import re

try:
    from base_utils.logger_base import get_logger
    cache_logger = get_logger('case_explore', tag='巡检探索')
except Exception:  # noqa: BLE001 兜底
    import logging
    cache_logger = logging.getLogger('case_explore')


# 页面进入链的起点：enter.from 为它表示从平台首页/一级菜单进入
ENTRY_PAGE = '首页'
# 唯一标识占位符（与 runner 的 UPLOAD_FILE_REPLACE_VAR 一致）
NODE_MARKER = '{{user_name}}'

# 层级分隔符：-- / —— / -> / → / >
_SEP_RE = re.compile(r'\s*(?:--|——|->|→|>)\s*')
# 描述里第一个中英文逗号/冒号之前的部分才参与层级解析，后面是校验说明
_HEAD_SPLIT_RE = re.compile(r'[，,：:；;]')
# 调用参数占位符：${inputs.字段名}
_INPUT_RE = re.compile(r'\$\{inputs\.([^}]+)\}')


def _segments(text):
    text = re.sub(r'https?://\S+', '', text or '')  # 起始 URL 与录入的链接不参与层级解析
    head = _HEAD_SPLIT_RE.split(text, 1)[0]
    return [p.strip() for p in _SEP_RE.split(head) if p and p.strip()]


def split_goal_path(goal):
    """从目标描述解析路径。

    '达人管理--达人列表--单个上传，平台账号……' → ['达人管理', '达人列表', '单个上传']
    只有一级或无法解析时返回 []，此时不启用页面缓存。
    """
    parts = _segments(goal)
    return parts if len(parts) >= 2 else []


def fill_values(text, marker=None, inputs=None):
    """回放时替换占位符：{{user_name}} → 本次唯一标识，${inputs.X} → 调用参数 X。"""
    s = '' if text is None else str(text)
    if marker:
        s = s.replace(NODE_MARKER, marker)
    if inputs:
        s = _INPUT_RE.sub(lambda m: str(inputs.get(m.group(1), '')), s)
    return s


def templatize(text, marker):
    """保存时：把本次唯一标识替换回占位符，让缓存可跨次复用。"""
    if not marker:
        return text
    return (text or '').replace(marker, NODE_MARKER)


# ── 文件存取 ──────────────────────────────────────────────────────────

def _cache_dir(sub='explore_cache'):
    from django.conf import settings
    d = os.path.join(str(settings.BASE_DIR), 'data', sub)
    os.makedirs(d, exist_ok=True)
    return d


def _module_file(module, draft=False):
    safe = re.sub(r'[\\/:*?"<>|\s]+', '_', module)
    return os.path.join(_cache_dir('explore_drafts' if draft else 'explore_cache'), f'{safe}.json')


def list_drafts():
    """列出待人工确认的草稿模块名。"""
    d = _cache_dir('explore_drafts')
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith('.json'))


def load_module(module, draft=False):
    """读取某模块的页面结构（正式库或草稿）；不存在或损坏返回 None。"""
    path = _module_file(module, draft)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        cache_logger.warning('读取页面缓存失败 {}：{}', path, e)
        return None
    ok = isinstance(data, dict) and data.get('module') == module and isinstance(data.get('pages'), dict)
    return data if ok else None


def _save_module(module, data, draft=False):
    path = _module_file(module, draft)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        cache_logger.error('页面缓存写入失败 {}：{}', path, e)


def approve_draft(module):
    """人工确认草稿后入库：草稿中的页面覆盖正式库同名页面，其余页面保留，随后删除草稿。"""
    draft = load_module(module, draft=True)
    if draft is None:
        cache_logger.warning('没有可确认的草稿：{}', module)
        return False
    formal = load_module(module) or {'module': module, 'pages': {}}
    formal['pages'].update(draft['pages'])
    _save_module(module, formal)
    os.remove(_module_file(module, draft=True))
    cache_logger.info('草稿已确认入库：{}（{} 个页面）', module, len(draft['pages']))
    return True


def discard_draft(module):
    """丢弃草稿（人工判定探索结果不可用）。"""
    try:
        os.remove(_module_file(module, draft=True))
    except FileNotFoundError:
        return False
    cache_logger.info('草稿已丢弃：{}', module)
    return True


def parse_target(target):
    """回归入口的目标解析，任意层级均可：'达人管理' → ['达人管理']，'达人管理--上传达人--单个上传' → 三段。"""
    return _segments(target)


_INPUT_NAME_RE = re.compile(r'\$\{inputs\.([^}]+)\}')


def required_inputs(obj):
    """返回动作/操作结构里引用到的调用参数名集合（${inputs.X} 中的 X）。"""
    return set(_INPUT_NAME_RE.findall(json.dumps(obj, ensure_ascii=False)))


# ── 查找 / 删除 / 保存 ────────────────────────────────────────────────

def _depth(page, path):
    """页面覆盖路径的段数：页面某个 goal 是 path 的前缀时，返回该 goal 的段数，否则 0。"""
    best = 0
    for g in page.get('goals') or []:
        segs = _segments(g)
        if segs and len(segs) <= len(path) and path[:len(segs)] == segs:
            best = max(best, len(segs))
    return best


def lookup(path):
    """按目标路径查找页面链。

    返回 (chain, covered)：
      - chain: [(页面名, 页面数据)]，从入口页到覆盖路径最深的页面；未命中为 []；
      - covered: 链的叶子页覆盖的路径段数，path[covered:] 为待执行操作或待探索的部分。
    """
    if not path:
        return [], 0
    data = load_module(path[0])
    if data is None:
        return [], 0
    pages = data['pages']
    best_name, best = None, 0
    for name, page in pages.items():
        d = _depth(page, path)
        if d > best:
            best_name, best = name, d
    if best_name is None:
        return [], 0
    chain, seen, name = [], set(), best_name
    while name in pages and name not in seen:
        seen.add(name)
        chain.append((name, pages[name]))
        name = (pages[name].get('enter') or {}).get('from')
    chain.reverse()
    return chain, best


def covered_depth(chain, path):
    """链的叶子页覆盖的路径段数（链为空返回 0）。"""
    return _depth(chain[-1][1], path) if chain else 0


def delete_page(module, name):
    """删除页面及其全部子页面，并从其它页面的 children 中移除引用。"""
    data = load_module(module)
    if data is None:
        return
    pages = data['pages']
    if name not in pages:
        return
    doomed, stack = set(), [name]
    while stack:
        n = stack.pop()
        if n in doomed or n not in pages:
            continue
        doomed.add(n)
        stack.extend(pages[n].get('children') or [])
    for n in doomed:
        pages.pop(n, None)
    for p in pages.values():
        p['children'] = [c for c in p.get('children') or [] if c not in doomed]
    if pages:
        _save_module(module, data)
    else:
        try:
            os.remove(_module_file(module))
        except FileNotFoundError:
            pass
    cache_logger.info('已删除页面缓存：{}（共 {} 个页面）', ' / '.join([module, name]), len(doomed))


def save_recorded(path, parent_name, parent_depth, pages, draft=True):
    """把本次探索记录的页面链写入草稿文件（draft=True，默认）。草稿需人工确认后才进入正式库。"""
    if not pages:
        return
    module = path[0]
    data = build_recorded(load_module(module, draft) or {'module': module, 'pages': {}},
                          path, parent_name, parent_depth, pages)
    _save_module(module, data, draft)
    cache_logger.info('{}：{} → {}', '草稿已保存（待人工确认）' if draft else '页面缓存已保存',
                      module, ' → '.join(p['name'] for p in pages))


def build_recorded(data, path, parent_name, parent_depth, pages):
    """把探索记录的页面链合并进 data（纯内存，不写文件），返回 data。

    对应规则（以页面名为准，不按序号）：
      - 页面名与路径段相同（如「上传达人」），该页面覆盖到该段，goals 记为 path 前缀；
      - 页面名不在路径中的（如「达人列表」「上传完成弹窗」）不写 goals；
      - 路径最后一段不是页面名时，视为操作：挂在最后一个匹配页面下，operations[段名]，
        其步骤为该页面及其之后页面的动作（弹窗等），之后的页面并入操作，不再单独保存。
      - 若一个路径段都没匹配到，则整条记录挂到路径末端（兼容旧行为）。
    """
    all_pages = data['pages']
    module = path[0]
    segs = path[1:]

    matches, cursor = {}, 0
    for i, p in enumerate(pages):
        if p['name'] in segs[cursor:]:
            j = segs.index(p['name'], cursor)
            matches[i] = j + 2  # 段数：模块名 + 之前的段 + 本段
            cursor = j + 1
    if not matches:
        matches[len(pages) - 1] = len(path)
    last_i = max(matches)
    last_depth = matches[last_i]

    op_name = None
    if last_depth < len(path) and len(path) - last_depth == 1:
        op_name = path[-1]

    stored = pages[:last_i + 1] if op_name else pages
    prev = parent_name or ENTRY_PAGE
    for i, p in enumerate(stored):
        name = p['name']
        old = all_pages.get(name) or {}
        goals = list(old.get('goals') or [])
        if i in matches:
            goal = '--'.join(path[:matches[i]])
            if goal not in goals:
                goals.append(goal)

        actions = p['actions']
        enter = p['enter']['actions']
        verify = p.get('verify')
        operations = dict(old.get('operations') or {})
        if op_name and i == last_i:
            steps = []
            for q in pages[last_i:]:
                if q is not p:
                    steps.extend(q['enter']['actions'])
                steps.extend(q['actions'])
            verify = pages[-1].get('verify') or verify
            operations[op_name] = {
                'enter': [],  # 页面的跳转动作仍在页面 enter 里
                'steps': [_to_value_action(a) for a in steps],
                'verify': verify,
            }
            actions, verify = [], None

        new = {
            'anchor': p.get('anchor') or old.get('anchor'),
            'enter': {'from': prev, 'actions': enter},
            'actions': actions,
            'verify': verify,
            'goals': goals,
            'children': list(old.get('children') or []),
        }
        if old.get('filters'):
            new['filters'] = old['filters']
        if operations:
            new['operations'] = operations
        all_pages[name] = new
        parent = all_pages.get(prev)
        if parent is not None and name not in (parent.get('children') or []):
            parent.setdefault('children', []).append(name)
        prev = name
    return data


def _to_value_action(a):
    """操作步骤统一用 value 字段承载录入值（回放时用 ${inputs.X} 或唯一标识占位符替换）。"""
    b = dict(a)
    if b.get('action') == 'type' and 'text' in b:
        b['value'] = b.pop('text')
    return b


# ── 探索记录 ──────────────────────────────────────────────────────────

class PageRecorder:
    """探索过程中记录页面边界与动作。

    AI 每条决策带 page 字段，页面名变化即视为进入新页面；
    页面切换前最后一个 click 视为进入新页面的跳转动作，移入新页面的 enter。
    """

    def __init__(self):
        self.blocks = []

    def current(self):
        return self.blocks[-1]['name'] if self.blocks else None

    def switch(self, name, visible_text):
        if self.blocks and self.blocks[-1]['name'] == name:
            return
        self.blocks.append({
            'name': name, 'actions': [], 'cacheable': True,
            'anchor': name if visible_text and name in visible_text else None,
        })

    def add(self, action, marker):
        if not self.blocks:
            return
        cur = self.blocks[-1]
        stored = _storable(action, marker)
        if stored is None:
            return
        if stored['action'] in ('click', 'type', 'upload', 'select_first') and not stored.get('label'):
            # 没有文字 label 的动作无法稳定回放，整个页面不缓存
            cur['cacheable'] = False
        cur['actions'].append(stored)

    def finish(self, visible_text, marker=None):
        """返回按顺序的页面列表：[{name, anchor, enter:{actions}, actions, verify}]。"""
        pages = []
        for i, b in enumerate(self.blocks):
            if not b['cacheable']:
                break  # 不可回放的页面及其后续页面都不保存
            enter = []
            if pages and pages[-1]['actions'] and pages[-1]['actions'][-1].get('action') == 'click':
                enter = [pages[-1]['actions'].pop()]  # 跳转动作移入本页的 enter
            pages.append({
                'name': b['name'], 'anchor': b['anchor'],
                'enter': {'actions': enter}, 'actions': b['actions'], 'verify': None,
            })
        if pages and marker and visible_text and marker in visible_text:
            pages[-1]['verify'] = NODE_MARKER
        return pages


def _storable(a, marker):
    act = a.get('action')
    if act == 'click':
        return {'action': 'click', 'label': a.get('label') or ''}
    if act == 'type':
        return {'action': 'type', 'label': a.get('label') or '',
                'text': templatize(str(a.get('text', '')), marker)}
    if act == 'upload':
        return {'action': 'upload', 'label': a.get('label') or ''}
    if act == 'select_first':
        return {'action': 'select_first', 'label': a.get('label') or ''}
    if act == 'scroll':
        return {'action': 'scroll', 'direction': a.get('direction') or 'down',
                'px': int(a.get('px') or 400)}
    if act == 'press':
        return {'action': 'press', 'label': a.get('label') or '', 'key': a.get('key') or 'Enter'}
    if act == 'wait':
        try:
            ms = int(a.get('ms') or 0)
        except (TypeError, ValueError):
            ms = 0
        return {'action': 'wait', 'ms': ms} if ms > 0 else None
    return None  # goto/screenshot 等不固化
