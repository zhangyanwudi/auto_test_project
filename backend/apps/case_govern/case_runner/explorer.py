# -*- coding: utf-8 -*-
"""
巡检自主探索执行器：让 AI「观察页面 → 决策下一步 → 执行 → 失败回喂重试」，
直到完成用户目标或穷尽所有办法，而不是一次性盲写 selector 执行。

流程：
    打开起始 URL
      → 循环（最多 max_rounds 轮）：
          1. observe_page 提取当前页面可交互元素（带 ref 编号的清单）
          2. 把「清单 + 目标 + 历史」发给 AI，让它下指令（click/type/press/wait/goto/upload）
          3. 按 ref 直接定位执行，记录结果
          4. 失败原因回喂给 AI，下一轮换方式重试
      → AI 声明 done（成功）或 failed（穷尽）
      → 返回真实走通的动作序列，供 finalize 反推规范

全程通过 case_explore 日志记录探索轨迹，失败时可按日志路径定位问题。
"""
import json
import os
import re

try:
    from base_utils.logger_base import get_logger
    explore_logger = get_logger('case_explore', tag='巡检探索')
except Exception:  # noqa: BLE001 兜底
    import logging
    explore_logger = logging.getLogger('case_explore')


class ExploreError(Exception):
    """探索失败（穷尽所有办法仍未达成目标）。"""


# 单轮动作上限，防止 AI 一次下太多动作导致中间态失控
_MAX_ACTIONS_PER_ROUND = 5

# 总决策步数上限（成功推进不计入失败次数，但仍需要防止死循环）
_MAX_STEPS = 60

# 元素清单条数上限，避免 DOM 过大时把上下文撑爆
_MAX_ELEMENTS = 120

# 可见文本截断长度
_MAX_VISIBLE_TEXT = 2000


def _extract_candidates_js():
    """返回在页面里提取可交互元素清单的 JS 代码。

    提取三类：可点击（菜单/链接/按钮/可点文字）、输入（input/textarea/可编辑）、
    下拉选择（select / 带 role=combobox）。每类都带：
      - ref: 元素在页面上的位置标记（写入 data 属性，供后续按 ref 定位）
      - label: 关联表单项 label 文本或自身文字/placeholder（用于展示给 AI）
    定位时用 data-zy-explore-ref 精确定位，避免 AI 猜 selector。
    """
    return """
    () => {
      const result = [];
      let idx = 0;
      const push = (el, kind, label) => {
        if (!el || idx >= 200) return;
        el.setAttribute('data-zy-explore-ref', String(idx));
        result.push({ref: idx, kind, label: String(label || '').trim().slice(0, 80)});
        idx += 1;
      };
      // 关联表单项里取 label 文案（批量上传框常是隐藏的无文字 input，靠这个给 AI 提示语义）
      const formLabel = (el) => {
        const formItem = el.closest('.arco-form-item, .el-form-item, .ant-form-item, [class*="form-item"]');
        if (formItem) {
          const labelEl = formItem.querySelector('.arco-form-item-label, .el-form-item__label, .ant-form-item-label, label');
          if (labelEl) return (labelEl.innerText || '').trim();
        }
        return '';
      };

      // 1. 文件上传框：input[type=file] 常被样式隐藏（offset 为 0），不能按可见性过滤，
      //    单列为 file 类型，AI 用 upload(ref) 上传
      document.querySelectorAll('input[type="file"]').forEach(el => {
        const label = formLabel(el) || el.getAttribute('aria-label') || el.name || '上传文件';
        push(el, 'file', label);
      });

      // 2. 可点击元素：菜单项、链接、按钮、以及带点击语义的元素
      const clickables = document.querySelectorAll(
        'a, button, .arco-menu-item, .el-menu-item, .ant-menu-item, [class*="menu-item"], [role="menuitem"], [role="button"], [role="tab"], [class*="tab"], .arco-dropdown-menu-item'
      );
      clickables.forEach(el => {
        if (el.offsetWidth === 0 && el.offsetHeight === 0) return;
        const t = (el.innerText || el.getAttribute('aria-label') || el.title || '').trim();
        if (t) push(el, 'click', t);
      });

      // 3. 输入框：input / textarea / contenteditable（文件框已在上方单独处理，这里跳过）
      const inputs = document.querySelectorAll('input, textarea, [contenteditable="true"]');
      inputs.forEach(el => {
        if (el.type === 'hidden' || el.type === 'file') return;
        if (el.offsetWidth === 0 && el.offsetHeight === 0 && el.tagName !== 'TEXTAREA') return;
        let label = formLabel(el);
        if (!label) label = el.getAttribute('placeholder') || el.getAttribute('aria-label') || el.name || '';
        push(el, 'input', label);
      });

      // 4. 下拉/选择
      const selects = document.querySelectorAll('select, [role="combobox"], .arco-select, [class*="select"]');
      selects.forEach(el => {
        if (el.offsetWidth === 0 && el.offsetHeight === 0) return;
        let label = formLabel(el);
        if (!label) label = el.getAttribute('placeholder') || el.getAttribute('aria-label') || el.innerText || '';
        push(el, 'select', label);
      });

      return result;
    }
    """


def observe_page(page):
    """提取当前页面状态：可交互元素清单、标题、URL、可见文本、列表数据情况。

    返回 dict，供组装给 AI 的观察块。
    """
    state = {'url': '', 'title': '', 'elements': [], 'visible_text': '', 'has_list_data': None}
    try:
        state['url'] = page.url
        state['title'] = page.title()
    except Exception:  # noqa: BLE001
        pass

    # 页面上的文件上传框数量（含被样式隐藏的 input[type=file]），供 AI 判断是否有上传入口
    try:
        state['file_input_count'] = page.locator('input[type="file"]').count()
    except Exception:  # noqa: BLE001
        state['file_input_count'] = 0

    try:
        raw = page.evaluate(_extract_candidates_js())
        if isinstance(raw, list):
            state['elements'] = raw[:_MAX_ELEMENTS]
    except Exception as e:  # noqa: BLE001
        explore_logger.warning('提取可交互元素失败：{}', e)

    try:
        text = page.inner_text('body')
        state['visible_text'] = (text or '')[: _MAX_VISIBLE_TEXT]
    except Exception:  # noqa: BLE001
        pass

    # 列表数据情况：优先数 tr / list-item / card 等，帮助 AI 判断查询是否出数据
    try:
        candidates = ('tr', '[class*="list-item"]', '[class*="item"]', '[class*="row"]',
                      '.arco-list-item', '.arco-card', 'tbody tr')
        count = 0
        for c in candidates:
            n = page.locator(c).count()
            if n > 0:
                count = n
                break
        state['has_list_data'] = count > 0
    except Exception:  # noqa: BLE001
        state['has_list_data'] = None

    # 表单字段当前值：让 AI 能看到链接是否已录入、handle 是否已自动生成
    try:
        state['form_values'] = page.evaluate(_FORM_VALUES_JS) or []
    except Exception:  # noqa: BLE001
        state['form_values'] = []

    return state


_FORM_VALUES_JS = """
() => {
  const out = [];
  document.querySelectorAll('[data-zy-explore-ref]').forEach(el => {
    const tag = el.tagName.toLowerCase();
    if (!['input', 'textarea'].includes(tag)) return;
    if (el.type === 'file' || el.type === 'hidden') return;
    const ph = el.placeholder || '';
    const val = (el.value || '').trim();
    if (!ph && !val) return;
    out.push({ref: Number(el.getAttribute('data-zy-explore-ref')), placeholder: ph.slice(0, 40),
              value: val.slice(0, 80), readonly: !!el.readOnly});
  });
  return out.slice(0, 80);
}
"""


def _format_observe(state):
    """把观察结果格式化为一段文本，供 AI 阅读。"""
    lines = []
    lines.append(f'当前 URL: {state.get("url") or ""}')
    lines.append(f'页面标题: {state.get("title") or ""}')
    lines.append('')

    elems = state.get('elements') or []
    lines.append(f'## 可交互元素清单（共 {len(elems)} 个，用 ref 编号下指令）')
    if not elems:
        lines.append('（未提取到元素，可尝试 wait 等待页面渲染，或 goto 其它地址）')
    for e in elems:
        lines.append(f'- ref={e["ref"]} [{e["kind"]}] {e["label"] or "（无文字）"}')

    lines.append('')
    form_values = state.get('form_values') or []
    lines.append('## 表单字段当前值（值为空表示未填写；录入链接后派生字段如 handle 有值，才算该条已添加成功）')
    if not form_values:
        lines.append('（无）')
    for f in form_values:
        v = f.get('value') or ''
        lines.append(f'- ref={f["ref"]} 占位符「{f.get("placeholder") or ""}」 当前值=「{v or "（空）"}」'
                     + (' [只读]' if f.get('readonly') else ''))

    lines.append('')
    lines.append('## 可见文本（用于判断是否出现目标数据/文案）')
    lines.append(state.get('visible_text') or '（无）')

    lines.append('')
    list_state = state.get('has_list_data')
    lines.append('列表数据情况：' + ('有数据' if list_state else ('无数据' if list_state is False else '未知')))

    fc = state.get('file_input_count')
    if fc:
        lines.append(f'文件上传框数量：{fc}（元素清单里 kind=file 的即为上传框，用 upload(ref) 上传）')
    return '\n'.join(lines)


def _call_ai(messages):
    """调用 AI 网关。"""
    from apps.ai_helper.gateway import call_agent_gateway
    return call_agent_gateway(messages)


def _parse_decision(text):
    """解析 AI 返回的决策 JSON。返回 dict 或 None。"""
    if not text:
        return None
    s = text.strip()
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', s, re.DOTALL)
    if m:
        s = m.group(1)
    else:
        start = s.find('{')
        end = s.rfind('}')
        if start == -1 or end <= start:
            return None
        s = s[start:end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


_SCROLL_JS = """
([ref, dy]) => {
  const isScrollable = e => {
    const st = getComputedStyle(e);
    return /(auto|scroll)/.test(st.overflowY) && e.scrollHeight > e.clientHeight + 4;
  };
  let target = null;
  if (ref !== null) {
    const el = document.querySelector(`[data-zy-explore-ref="${ref}"]`);
    for (let n = el; n && !target; n = n.parentElement) {
      if (isScrollable(n)) target = n;
    }
  }
  if (!target) {
    // 没有 ref 或 ref 所在链路无滚动容器：优先找弹窗内的滚动区，其次页面上可见的第一个滚动区
    const dialogs = [...document.querySelectorAll('[role="dialog"], .ant-modal-body, .el-dialog__body')];
    for (const d of dialogs) {
      const cand = [d, ...d.querySelectorAll('*')].find(isScrollable);
      if (cand) { target = cand; break; }
    }
  }
  if (!target) {
    target = [...document.querySelectorAll('div')].find(e => e.offsetParent !== null && isScrollable(e)) || null;
  }
  if (target) { target.scrollBy(0, dy); return 'container'; }
  window.scrollBy(0, dy);
  return 'window';
}
"""


def _capture_screenshot_b64(page):
    """截取当前视口截图，返回 base64 字符串（PNG）；失败返回 None。"""
    import base64
    try:
        return base64.b64encode(page.screenshot(type='png', timeout=10000)).decode('ascii')
    except Exception as e:  # noqa: BLE001
        explore_logger.warning('[巡检探索] 截图失败：{}', e)
        return None


def _call_ai_vision(messages):
    """探索专用调用：使用配置的视觉模型（explore_model），图片消息随 messages 一起发送。"""
    from apps.ai_helper.gateway import call_agent_gateway, load_config
    return call_agent_gateway(messages, model=load_config().get('explore_model') or None)


def _remap_refs(actions, old_elements, new_elements):
    """AI 基于旧快照给出的 ref，在动作执行前映射到当前页面的新 ref。

    按 (kind, label) 匹配，同名元素按出现次序一一对应；找不到则保留原 ref（由 _do_action 的文字兜底处理）。
    返回被改写的 ref 数量。
    """
    def key(e):
        return (e.get('kind'), (e.get('label') or '').strip())

    old_by_ref = {e.get('ref'): e for e in old_elements or []}
    new_by_key = {}
    for e in new_elements or []:
        new_by_key.setdefault(key(e), []).append(e.get('ref'))
    seen = {}
    occurrence = {}
    for e in old_elements or []:
        k = key(e)
        occurrence[e.get('ref')] = seen.get(k, 0)
        seen[k] = seen.get(k, 0) + 1

    changed = 0
    for act in actions or []:
        ref = act.get('ref')
        if ref is None or ref not in old_by_ref:
            continue
        k = key(old_by_ref[ref])
        if not k[1]:
            continue  # 无文字的元素无法可靠对应，保留原 ref
        cands = new_by_key.get(k)
        if not cands:
            continue
        new_ref = cands[min(occurrence[ref], len(cands) - 1)]
        if new_ref != ref:
            act['ref'] = new_ref
            changed += 1
    return changed


def _ref_locator(page, ref):
    """按 data-zy-explore-ref 精确定位 ref 对应的元素。"""
    return page.locator(f'[data-zy-explore-ref="{ref}"]')


def _ref_label(elements, ref):
    """根据 ref 从元素清单里取回元素显示文字（供反推规范时给出确定性元素名）。"""
    for e in elements or []:
        if e.get('ref') == ref:
            return e.get('label') or ''
    return ''


def _do_action(page, action, elements, upload_file_path=None):
    """执行单个动作，返回 (是否成功, 结果说明)。失败抛 ExploreError。

    :param upload_file_path: 上传类动作的兜底文件路径；AI 未在 action 里给 path 时用它。
    """
    act = (action or {}).get('action')
    ref = action.get('ref')

    if act == 'click':
        if ref is None:
            raise ExploreError('click 缺少 ref')
        loc = _ref_locator(page, ref)
        if loc.count() == 0 and action.get('label'):
            # ref 已失效（页面重新渲染）：按元素文字定位兜底
            try:
                _click_by_label(page, action['label'])
            except ExploreError as e:
                raise ExploreError(f'点击 ref={ref} 失败，文字兜底也未找到：{e}')
            return f'点击 ref={ref}（按文字「{action["label"]}」定位）成功'
        try:
            loc.first.click(timeout=10000)
        except Exception as e:  # noqa: BLE001
            raise ExploreError(f'点击 ref={ref} 失败：{e}')
        return f'点击 ref={ref} 成功'

    if act == 'type':
        if ref is None:
            raise ExploreError('type 缺少 ref')
        text = action.get('text', '')
        loc = _ref_locator(page, ref)
        if loc.count() == 0 and action.get('label'):
            try:
                _fill_by_label(page, action['label'], text)
            except ExploreError as e:
                raise ExploreError(f'输入 ref={ref} 失败，字段兜底也未找到：{e}')
            return f'输入 ref={ref}（按字段「{action["label"]}」定位）= {text}'
        try:
            loc.first.fill(str(text), timeout=10000)
        except Exception as e:  # noqa: BLE001
            raise ExploreError(f'输入 ref={ref} 失败：{e}')
        return f'输入 ref={ref} = {text}'

    if act == 'upload':
        # 上传文件：走 input[type=file].set_input_files，不能用 fill（文件框禁止 fill 填路径）。
        # 文件路径优先用 AI 给的，AI 没给则用系统配置的 upload_file_path 兜底。
        if ref is None:
            raise ExploreError('upload 缺少 ref')
        file_path = action.get('path') or action.get('text') or upload_file_path or ''
        if not file_path:
            raise ExploreError('upload 缺少文件路径：请在 UPLOAD_FILE_PATH 或调用参数里指定真实文件')
        # 路径归一化：AI 可能给出 Windows 反斜杠、浏览器伪路径、或被引号包裹的字符串
        if file_path.startswith('C:\\fakepath\\') or file_path.startswith('C:/fakepath/'):
            raise ExploreError(f'AI 给出了浏览器伪路径（{file_path}），请改用 UPLOAD_FILE_PATH 指定的真实文件路径')
        file_path = file_path.strip().strip('"\'').replace('\\', '/')
        if not os.path.isabs(file_path):
            raise ExploreError(f'上传路径不是绝对路径：{file_path}')
        if not os.path.isfile(file_path):
            raise ExploreError(f'上传文件不存在：{file_path}')
        loc = _ref_locator(page, ref)
        try:
            loc.first.set_input_files(file_path, timeout=10000)
        except Exception as e:  # noqa: BLE001
            raise ExploreError(f'上传文件 ref={ref} 失败：{e}')
        return f'上传文件 ref={ref} = {file_path}'

    if act == 'press':
        key = action.get('key', 'Enter')
        if ref is not None:
            loc = _ref_locator(page, ref)
            try:
                loc.first.press(key, timeout=10000)
                return f'按键 ref={ref} {key}'
            except Exception as e:  # noqa: BLE001
                raise ExploreError(f'按键 ref={ref} {key} 失败：{e}')
        page.keyboard.press(key)
        return f'按键 {key}'

    if act == 'wait':
        # wait 的真实时长以 ms 为准（纯数字），text 里「N秒/Ns」也会被解析成 ms。
        # 归一化后写回 action['ms']，保证反推规范时「等待 N秒」的 N 来自真实等待时长。
        raw_ms = action.get('ms')
        if raw_ms is None:
            raw_ms = action.get('text')
        try:
            ms = int(raw_ms)
        except (TypeError, ValueError):
            m = re.search(r'(\d+)\s*(?:秒|s)?', str(raw_ms or ''))
            ms = int(m.group(1)) * 1000 if m else 1000
        action['ms'] = ms
        page.wait_for_timeout(ms)
        return f'等待 {ms}ms'

    if act == 'select_first':
        # 下拉框点击被弹窗遮罩拦截时的替代方式：聚焦 → 下箭头 → 回车，选中列表第一项
        if ref is None:
            raise ExploreError('select_first 缺少 ref')
        loc = _ref_locator(page, ref)
        if loc.count() == 0:
            raise ExploreError(f'select_first：ref={ref} 已失效，请基于最新元素清单重新选择')
        try:
            loc.first.evaluate('el => el.focus()')
            page.keyboard.press('ArrowDown')
            page.wait_for_timeout(300)
            page.keyboard.press('Enter')
        except Exception as e:  # noqa: BLE001
            raise ExploreError(f'select_first ref={ref} 失败：{e}')
        page.wait_for_timeout(300)
        return f'下拉 ref={ref} 选择第一项（键盘）'

    if act == 'scroll':
        direction = str(action.get('direction') or 'down').lower()
        try:
            px = int(action.get('px') or 400)
        except (TypeError, ValueError):
            px = 400
        dy = -abs(px) if direction in ('up', 'top') else abs(px)
        try:
            where = page.evaluate(_SCROLL_JS, [ref if ref is not None else None, dy])
        except Exception as e:  # noqa: BLE001
            raise ExploreError(f'滚动失败：{e}')
        action['px'] = px
        action['direction'] = 'up' if dy < 0 else 'down'
        page.wait_for_timeout(300)
        return f'滚动 {"上" if dy < 0 else "下"} {abs(px)}px（{where}）'

    if act == 'goto':
        url = action.get('url')
        if not url:
            raise ExploreError('goto 缺少 url')
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        return f'打开 {url}'

    raise ExploreError(f'未知动作：{act}')


# 基建平台一级菜单关键词 → 菜单名（用于从目标描述里识别要先点哪个菜单进入）
_MODULE_MENU_KEYWORDS = {
    '达人管理': ['达人管理', '达人'],
    '订单管理': ['订单管理', '订单'],
    '建联管理': ['建联'],
    '投流管理': ['投流'],
    '线索库': ['线索'],
}


def guess_module_from_goal(goal):
    """从目标描述里识别要进入的一级菜单名（如「达人管理」）。

    命中 _MODULE_MENU_KEYWORDS 里的关键词即返回菜单名；未命中返回 None。
    用于探索时提示 AI 先点对应菜单，确保完整导航链路被探索/固化。
    """
    if not goal:
        return None
    for menu_name, keywords in _MODULE_MENU_KEYWORDS.items():
        if any(k in goal for k in keywords):
            return menu_name
    return None


def parse_goal_hierarchy(goal):
    """从目标描述里解析出「模块 → 子功能 → 功能点」三层结构，用于固化时按模块分层建节点树。

    解析策略：
      1. 优先按分隔符（-- / — / → / -）切分，形如「达人管理--上传达人--批量上传」；
      2. 无分隔符时，用关键词识别模块（一级菜单名）与子功能/功能点。

    返回 dict: {'module': str|None, 'feature': str|None, 'action': str|None}。
    """
    if not goal:
        return {'module': None, 'feature': None, 'action': None}

    module = guess_module_from_goal(goal)

    # ── 关键词定位：feature=二级入口（如「上传达人」），action=三级操作点（如「批量上传」）──
    # feature 关键词（二级入口，通常是「达人之下的功能页」）
    feature_keywords = ['上传达人', '创建订单', '导入达人', '批量导入', '单个导入', '导入']
    # action 关键词（三级操作点，feature 下的具体操作）
    action_keywords = ['批量上传', '单个上传', '批量导入', '单个导入', '创建订单', '提交']

    feature = None
    action = None

    # 先找 feature（二级入口），再在其后文本里找 action（三级点）
    for kw in feature_keywords:
        idx = goal.find(kw)
        if idx >= 0:
            if feature is None or idx < goal.find(feature):
                feature = kw
    if feature:
        # 在 feature 出现位置之后找 action
        after = goal[goal.find(feature) + len(feature):]
        for kw in action_keywords:
            if kw in after and kw != feature:
                action = kw
                break
        if action is None:
            # 整个 goal 里兜底找 action（排除与 feature 相同的词）
            for kw in action_keywords:
                if kw in goal and kw != feature:
                    action = kw
                    break
    else:
        # 无 feature 时，用 action 关键词兜底
        for kw in action_keywords:
            if kw in goal:
                action = kw
                break
        if action:
            feature = action
            action = None

    return {'module': module, 'feature': feature, 'action': action}


def _build_history_text(history):
    """把历史动作/结果序列化成文本给 AI。"""
    if not history:
        return '（暂无历史）'
    lines = []
    for h in history[-20:]:
        lines.append(f'- 决策说明：{h.get("note", "")}')
        for act in h.get('actions', []):
            lines.append(f'  · 动作 {act.get("action")} ref={act.get("ref")} text={act.get("text", "")}')
        lines.append(f'  · 结果：{h.get("result", "")}')
    return '\n'.join(lines)


# ── 分层节点缓存回放：按路径逐级回放已固化节点，只探索缓存缺失的部分 ──

from . import node_cache as nc


def _click_by_label(page, label):
    """按元素文字点击（回放用，避免依赖每次变化的 ref）。优先可见元素，其次精确匹配，最后模糊匹配。"""
    loc = page.locator(f'text="{label}" >> visible=true')
    if loc.count() == 0:
        loc = page.get_by_text(label, exact=True)
    if loc.count() == 0:
        loc = page.get_by_text(label, exact=False)
    if loc.count() == 0:
        raise ExploreError(f'页面上找不到文字「{label}」')
    loc.first.click(timeout=10000)


def _fill_by_label(page, label, text):
    """按字段名录入（回放用）：label 关联 → placeholder → 字段名文字之后的第一个输入框（表单行布局）。"""
    loc = page.get_by_label(label, exact=True)
    if loc.count() == 0:
        loc = page.get_by_placeholder(label)
    if loc.count() == 0:
        loc = page.locator(
            f'xpath=//*[normalize-space(.)="{label}" and not(*[normalize-space(.)="{label}"])]'
            '/following::input[1]')
    if loc.count() == 0:
        raise ExploreError(f'页面上找不到字段「{label}」')
    loc.first.fill(str(text), timeout=10000)


def _select_first_by_label(page, label):
    """回放 select_first：按字段名定位下拉输入框，键盘选择第一项。"""
    loc = page.get_by_label(label, exact=True)
    if loc.count() == 0:
        loc = page.get_by_placeholder(label)
    if loc.count() == 0:
        raise ExploreError(f'页面上找不到下拉字段「{label}」')
    loc.first.evaluate('el => el.focus()')
    page.keyboard.press('ArrowDown')
    page.wait_for_timeout(300)
    page.keyboard.press('Enter')


def _upload_file(page, upload_file_path):
    """回放上传：使用本次的唯一副本路径。"""
    if not upload_file_path:
        raise ExploreError('节点包含上传动作，但未配置上传文件')
    loc = page.locator('input[type="file"]')
    if loc.count() == 0:
        raise ExploreError('页面上没有文件上传框')
    loc.last.set_input_files(upload_file_path, timeout=10000)


def _body_text(page):
    try:
        return page.inner_text('body') or ''
    except Exception:  # noqa: BLE001
        return ''


def replay_actions(page, actions, marker, upload_file_path=None, inputs=None, where=''):
    """回放一组动作（按文字 label 定位）。失败抛 ExploreError。

    录入值支持 {{user_name}}（本次唯一标识）与 ${inputs.字段名}（调用参数），
    动作的值优先取 value，其次 text。
    """
    for a in actions or []:
        act = a.get('action')
        try:
            if act == 'click':
                _click_by_label(page, a.get('label') or '')
            elif act == 'type':
                value = a.get('value', a.get('text', ''))
                _fill_by_label(page, a.get('label') or '', nc.fill_values(value, marker, inputs))
            elif act == 'upload':
                _upload_file(page, upload_file_path)
            elif act == 'select_first':
                _select_first_by_label(page, a.get('label') or '')
            elif act == 'scroll':
                dy = -abs(int(a.get('px') or 400)) if a.get('direction') == 'up' else abs(int(a.get('px') or 400))
                page.evaluate(_SCROLL_JS, [None, dy])
            elif act == 'press':
                page.keyboard.press(a.get('key') or 'Enter')
            elif act == 'wait':
                page.wait_for_timeout(int(a.get('ms') or 0))
        except ExploreError as e:
            raise ExploreError(f'{where}回放 {act} 失败：{e}')
        except Exception as e:  # noqa: BLE001
            raise ExploreError(f'{where}回放 {act} 异常：{e}')
        page.wait_for_timeout(600)


def _verify_text(page, text, marker, inputs, where):
    """回放后的完成校验：文字经占位符替换后必须出现在页面上。"""
    text = nc.fill_values(text, marker, inputs)
    if not text:
        return
    page.wait_for_timeout(800)
    if text not in _body_text(page):
        raise ExploreError(f'{where}回放后页面未出现校验文字「{text}」')


def replay_page(page, name, pg, marker, upload_file_path=None):
    """回放一个页面：不在该页时先执行 enter 跳转，再执行页内固定动作，最后校验 verify。"""
    anchor = pg.get('anchor')
    where = f'页面「{name}」'
    enter = (pg.get('enter') or {}).get('actions') or []
    if enter and not (anchor and anchor in _body_text(page)):
        replay_actions(page, enter, marker, upload_file_path, where=where + ' 进入：')
    if anchor and anchor not in _body_text(page):
        raise ExploreError(f'{where}进入后页面未出现识别文字「{anchor}」')
    replay_actions(page, pg.get('actions') or [], marker, upload_file_path, where=where + '：')
    _verify_text(page, pg.get('verify'), marker, None, where)


def replay_filters(page, pg, filter_values, marker):
    """按调用传入的字段录入筛选项（只录入传入的字段），最后点击查询。"""
    filters = pg.get('filters') or {}
    fields = filters.get('fields') or {}
    actions = []
    for field, value in (filter_values or {}).items():
        spec = fields.get(field)
        if not spec:
            raise ExploreError(f'筛选项「{field}」在页面缓存中未定义')
        actions.append(dict(spec, value=value))
    if filters.get('submit'):
        actions.append(filters['submit'])
    replay_actions(page, actions, marker, where='筛选：')


def replay_operation(page, op_name, op, marker, inputs, upload_file_path=None):
    """回放页面上的带参数操作：enter（可选）→ steps（值用 ${inputs.X} 替换）→ verify。"""
    where = f'操作「{op_name}」'
    if op.get('enter'):
        replay_actions(page, op['enter'], marker, upload_file_path, inputs, where=where + ' 进入：')
    replay_actions(page, op.get('steps') or [], marker, upload_file_path, inputs, where=where + '：')
    _verify_text(page, op.get('verify'), marker, inputs, where)


def _replayed_actions(actions, marker, inputs=None):
    """把缓存动作还原成探索动作序列（供反推规范用），占位符替换为本次值。"""
    out = []
    for a in actions or []:
        b = dict(a)
        if 'value' in b or b.get('action') == 'type':
            b['text'] = nc.fill_values(b.get('value', b.get('text', '')), marker, inputs)
            b.pop('value', None)
        out.append(b)
    return out


def run_explore_loop(page, goal, max_rounds=10, upload_file_path=None, start_url=None,
                     on_progress=None, unique_marker=None, inputs=None, on_recorded=None):
    """在 page 上执行「页面缓存回放 + AI 探索」，直到 AI 声明 done 且校验通过。

    流程：
      1. 目标解析为路径（达人管理--达人列表--单个上传）；
      2. 按页面链逐页回放已缓存页面（不在该页则先 enter 跳转）；回放失败则删除该页及其子页面，从此处重新探索；
      3. 路径剩余段若是叶子页的操作名（operations），按 inputs 回放该操作；
      4. 其余未缓存部分由 AI 探索，AI 每条决策用 page 字段标注所属页面，页面名变化即新页面；
      5. AI 声明 done 且（有唯一标识时）页面正文中能看到本次唯一标识，才算成功，并固化新探索出的页面。

    :param unique_marker:    本次运行的唯一标识（如 auto_20261113113940）；为 None 时不做唯一数据校验
    :param inputs:           调用参数（如 {'昵称': 'ZnYan'}），用于回放操作与筛选项
    :return (success, actions, last_note)
    """
    from .prompts import build_explorer_system_prompt

    system = build_explorer_system_prompt(upload_file_path=upload_file_path)
    history = []
    performed_actions = []
    inputs = inputs or {}

    path = nc.split_goal_path(goal) if start_url else []
    chain, covered = nc.lookup(path) if path else ([], 0)

    # ── 1. 逐页回放已缓存页面 ──
    replayed_names = []
    for i, (name, pg) in enumerate(list(chain)):
        try:
            replay_page(page, name, pg, unique_marker, upload_file_path=upload_file_path)
        except ExploreError as e:
            explore_logger.warning('[巡检探索] 页面缓存回放失败，删除该页面及其子页面，从此处重新探索：{}', e)
            nc.delete_page(path[0], name)
            chain = chain[:i]
            break
        replayed_names.append(name)
        performed_actions.extend(_replayed_actions((pg.get('enter') or {}).get('actions') or [], unique_marker))
        performed_actions.extend(_replayed_actions(pg.get('actions') or [], unique_marker))
        explore_logger.info('[巡检探索] 已回放页面「{}」，{} 个动作', name, len(pg.get('actions') or []))
        try:
            page.wait_for_timeout(800)
        except Exception:  # noqa: BLE001
            pass

    covered = nc.covered_depth(chain, path) if chain else 0
    remaining = path[covered:] if path else []

    # ── 2. 叶子页的操作（路径剩余第一段命中 operations）：按调用参数回放 ──
    if path and chain and remaining:
        leaf_name, leaf = chain[-1]
        op = (leaf.get('operations') or {}).get(remaining[0])
        if op is not None:
            try:
                replay_operation(page, remaining[0], op, unique_marker, inputs, upload_file_path=upload_file_path)
                performed_actions.extend(_replayed_actions(op.get('steps') or [], unique_marker, inputs))
                explore_logger.info('[巡检探索] 已回放操作「{}」', remaining[0])
                replayed_names.append(remaining[0])
                remaining = remaining[1:]
            except ExploreError as e:
                explore_logger.warning('[巡检探索] 操作「{}」回放失败，改由 AI 探索：{}', remaining[0], e)
        if inputs.get('筛选') and leaf.get('filters'):
            try:
                replay_filters(page, leaf, inputs.get('筛选'), unique_marker)
            except ExploreError as e:
                explore_logger.warning('[巡检探索] 筛选回放失败，改由 AI 探索：{}', e)

    # 路径已全部命中：检查唯一数据是否真的存在，存在则直接成功，否则删除叶子页重新探索
    if path and not remaining and chain:
        if not unique_marker or unique_marker in _body_text(page):
            explore_logger.info('[巡检探索] 目标路径全部页面已缓存并回放成功，无需 AI 探索')
            return True, performed_actions, '全部页面已缓存，回放成功'
        explore_logger.warning('[巡检探索] 页面回放完成但未看到本次唯一标识「{}」，删除叶子页重新探索', unique_marker)
        leaf_name = chain[-1][0]
        nc.delete_page(path[0], leaf_name)
        chain = chain[:-1]
        covered = nc.covered_depth(chain, path) if chain else 0
        remaining = path[covered:]

    parent_name = chain[-1][0] if chain else None
    parent_depth = covered
    recorder = nc.PageRecorder()
    last_round_failed = False  # 上一轮有动作失败 → 本轮附带截图，让 AI 结合画面自行分析原因并换方式
    known_text = ' → '.join(replayed_names) or '（无）'
    pending_text = ' → '.join(remaining) or '（目标未指定层级路径，由你根据目标自行划分页面）'
    marker_text = (
        f'本次唯一标识：{unique_marker}（目标里的 {nc.NODE_MARKER} 已替换为它）。'
        '完成条件：页面上必须能看到本次录入的数据（含该标识），仅「列表有数据」不算完成。'
        if unique_marker else '（本次目标无唯一标识）'
    )

    explore_logger.info('[巡检探索] 目标={} 开始，已回放页面={}，待探索={}，最多 {} 轮，上传文件={}',
                        goal, known_text, pending_text, max_rounds, upload_file_path or '（未配置）')

    # 轮数只在「失败」时计入（失败次数达到 max_rounds 才判定探索失败）；成功推进不消耗次数，
    # 另设总步数上限 _MAX_STEPS 防止无限循环
    failures = 0
    step_no = 0
    while failures < max_rounds and step_no < _MAX_STEPS:
        step_no += 1
        round_no = step_no
        state = observe_page(page)
        observe_text = _format_observe(state)
        history_text = _build_history_text(history)
        visible = state.get('visible_text') or ''

        shot = _capture_screenshot_b64(page) if last_round_failed else None
        shot_hint = (
            '\n\n【上一轮有动作失败，已附带当前页面截图】请结合截图判断失败原因'
            '（元素被弹窗遮挡 / 在弹窗下方未滚动到 / 页面已重新渲染导致 ref 失效 / 弹窗未关闭等），'
            '再决定 scroll、press Escape、wait 或换一种操作方式，不要重复执行失效的 ref。'
            if shot else ''
        )

        user = (
            f'目标：{goal}\n\n'
            f'## 页面状态\n'
            f'- 已回放成功的页面/操作：{known_text}\n'
            f'- 待探索的页面层级：{pending_text}\n'
            f'- {marker_text}\n\n'
            f'—— 第 {round_no} 轮观察 ——\n'
            f'{observe_text}\n\n'
            f'—— 历史 ——\n{history_text}\n\n'
            '请根据当前页面与目标，输出下一轮决策 JSON（必须带 node 字段）。'
            + shot_hint
        )
        if shot:
            user_content = [
                {'type': 'text', 'text': user},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + shot}},
            ]
        else:
            user_content = user

        explore_logger.info('[巡检探索] 第 {} 轮观察：元素 {} 个，列表数据={}',
                            round_no, len(state.get('elements') or []), state.get('has_list_data'))

        messages = [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user_content},
        ]
        reply = _call_ai_vision(messages)
        decision = _parse_decision(reply)
        explore_logger.info('[巡检探索] 第 {} 轮 AI 决策：{}', round_no, (reply or '')[:500])

        if decision is None:
            history.append({'note': '（AI 返回无法解析）', 'actions': [], 'result': f'解析失败：{reply[:200]}'})
            failures += 1
            continue

        note = decision.get('note', '')
        done = bool(decision.get('done'))
        failed = bool(decision.get('failed'))

        if done:
            if failed:
                explore_logger.warning('[巡检探索] 第 {} 轮 AI 声明失败：{}', round_no, note)
                return False, performed_actions, note
            body = _body_text(page)
            if unique_marker and unique_marker not in body:
                explore_logger.warning('[巡检探索] 第 {} 轮 AI 声明完成，但页面未出现唯一标识「{}」，判定未完成', round_no, unique_marker)
                history.append({'note': note, 'actions': [],
                                'result': f'未通过校验：页面上没有本次录入数据的唯一标识「{unique_marker}」，请确认数据已保存并出现在列表中'})
                failures += 1
                continue
            explore_logger.info('[巡检探索] 第 {} 轮 AI 声明完成：{}', round_no, note)
            # 成功 → 固化本次新探索出的页面（挂在已回放的叶子页之下）
            pages_recorded = recorder.finish(body, unique_marker)
            if path and pages_recorded:
                if on_recorded is not None:
                    # 调用方自行处理探索结果（如写入 page_patrol 目录），不再写草稿
                    on_recorded(path, parent_name, parent_depth, pages_recorded)
                else:
                    nc.save_recorded(path, parent_name, parent_depth, pages_recorded)
            return True, performed_actions, note

        actions = decision.get('actions') or []
        if not isinstance(actions, list):
            actions = []
        actions = actions[:_MAX_ACTIONS_PER_ROUND]

        page_name = str(decision.get('page') or decision.get('node') or '').strip()
        if not page_name:
            page_name = recorder.current() or '未命名页面'
        if path:
            recorder.switch(page_name, visible)

        # AI 决策期间页面可能已变化（决策耗时较长）：执行前重新观察，并把 ref 映射到当前页面
        fresh = observe_page(page)
        remapped = _remap_refs(actions, state.get('elements') or [], fresh.get('elements') or [])
        if remapped:
            explore_logger.info('[巡检探索] 第 {} 轮：页面在决策期间已变化，重映射 {} 个 ref', round_no, remapped)
        state = fresh

        round_result_parts = []
        round_failed = False
        for act in actions:
            if round_failed:
                # 前一个动作失败（多半是页面已重新渲染，ref 失效），剩余动作取消，交给 AI 基于新页面重新决策
                break
            action_name = act.get('action')
            if action_name in ('click', 'type', 'upload', 'select_first') and act.get('ref') is not None:
                act['label'] = _ref_label(state.get('elements') or [], act.get('ref'))
            try:
                result_text = _do_action(page, act, state.get('elements') or [], upload_file_path=upload_file_path)
                performed_actions.append(act)
                if path:
                    recorder.add(act, unique_marker)
                round_result_parts.append(result_text)
                explore_logger.info('[巡检探索] 第 {} 轮执行 {} ref={} text={} → 成功',
                                    round_no, action_name, act.get('ref'), act.get('text', ''))
                if on_progress and action_name in ('click', 'type', 'upload'):
                    from .runner import _describe_action
                    on_progress(f'✅ {_describe_action(act)}，结果 ✅ 通过')
            except ExploreError as e:
                round_failed = True
                round_result_parts.append(f'失败：{e}')
                explore_logger.warning('[巡检探索] 第 {} 轮执行 {} ref={} 失败：{}',
                                       round_no, action_name, act.get('ref'), e)
                if on_progress and action_name in ('click', 'type', 'upload'):
                    from .runner import _describe_action
                    on_progress(f'❌ {_describe_action(act)}，结果 ❌ 失败：{e}')
            except Exception as e:  # noqa: BLE001
                round_failed = True
                round_result_parts.append(f'异常：{e}')
                explore_logger.error('[巡检探索] 第 {} 轮执行 {} 异常：{}', round_no, action_name, e)
                if on_progress and action_name in ('click', 'type', 'upload'):
                    from .runner import _describe_action
                    on_progress(f'❌ {_describe_action(act)}，结果 ❌ 失败：{e}')

        history.append({
            'note': note,
            'actions': actions,
            'result': ' | '.join(round_result_parts) if round_result_parts else '（本轮无动作）',
        })
        last_round_failed = round_failed
        if round_failed:
            failures += 1

        try:
            page.wait_for_timeout(1000)
        except Exception:  # noqa: BLE001
            pass

    explore_logger.error('[巡检探索] 失败次数达到 {} 或总步数达到 {}，仍未达成目标', max_rounds, _MAX_STEPS)
    return False, performed_actions, f'探索失败次数达到上限（{max_rounds}）或总步数达到上限（{_MAX_STEPS}）仍未达成目标'
