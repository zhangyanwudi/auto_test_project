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

    return state


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

    if act == 'goto':
        url = action.get('url')
        if not url:
            raise ExploreError('goto 缺少 url')
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        return f'打开 {url}'

    raise ExploreError(f'未知动作：{act}')


# ── 导航节点分层固化：探索成功后按「模块 → 子功能」固化导航，下次按目标描述匹配回放 ──
# 场景：达人管理 / 订单管理 是一级菜单（模块），达人管理下的上传达人 / 创建订单 是二级入口（子功能）。
# 分层固化后，未来可分别回放「只进某模块」或「只进某子功能」。
# 模块名 = 导航前缀第一个 click 的 label；子功能名 = 第二个 click 的 label（无则等于模块名）。
# goto 由 runner 每次统一执行，不固化。

# 视为「目标操作」的动作：导航前缀在这里结束，之后是每次目标特有的操作
_NAV_END_ACTIONS = ('type', 'upload', 'press')


def _nav_cache_dir():
    """导航缓存目录：backend/data/explore_cache。"""
    from django.conf import settings
    d = os.path.join(str(settings.BASE_DIR), 'data', 'explore_cache')
    os.makedirs(d, exist_ok=True)
    return d


def _nav_cache_path():
    """分层导航缓存文件路径：backend/data/explore_cache/nav_modules.json。"""
    return os.path.join(_nav_cache_dir(), 'nav_modules.json')


def _load_modules_cache():
    """读取分层导航缓存 {module: {feature: [nav_actions]}}；无则返回空 dict。"""
    path = _nav_cache_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        explore_logger.warning('读取导航缓存失败 {}：{}', path, e)
        return {}
    return data if isinstance(data, dict) else {}


def _save_modules_cache(data):
    """写回分层导航缓存。"""
    path = _nav_cache_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        explore_logger.error('导航缓存写入失败 {}：{}', path, e)


def save_nav_actions(module_name, feature_name, nav_actions):
    """按「模块/子功能」固化导航片段。nav_actions 为空时不写（避免误清已有缓存）。"""
    if not nav_actions or not module_name:
        return
    feature_name = feature_name or module_name
    data = _load_modules_cache()
    data.setdefault(module_name, {})
    data[module_name][feature_name] = nav_actions
    _save_modules_cache(data)
    explore_logger.info('导航片段已固化：{} / {} → {} 个动作', module_name, feature_name, len(nav_actions))


def load_nav_actions(module_name, feature_name=None):
    """按「模块/子功能」读取已固化的导航片段；命中返回 (nav_actions, module, feature)。

    - 指定 feature_name 时优先精确匹配该子功能；
    - 未命中子功能时回退到模块级导航（feature=module 的默认入口）；
    - 都未命中返回 None。
    """
    if not module_name:
        return None
    data = _load_modules_cache()
    mod = data.get(module_name)
    if not isinstance(mod, dict):
        return None
    if feature_name and feature_name in mod:
        return mod[feature_name], module_name, feature_name
    if module_name in mod:
        return mod[module_name], module_name, module_name
    return None


def remove_nav_actions(module_name, feature_name=None):
    """删除某模块/子功能的失效导航缓存，避免每次回放都对坏缓存反复失败。

    指定 feature_name 时只删该子功能；否则删整个模块。
    """
    if not module_name:
        return
    data = _load_modules_cache()
    mod = data.get(module_name)
    if not isinstance(mod, dict):
        return

    if feature_name:
        # 删指定子功能；删空后若该模块已无任何功能，则整个模块一并删掉
        if feature_name in mod:
            del mod[feature_name]
            if not mod:
                del data[module_name]
        else:
            return
    else:
        # 删整个模块
        if module_name in data:
            del data[module_name]
        else:
            return

    _save_modules_cache(data)
    explore_logger.info('已清除失效导航缓存：{} / {}', module_name, feature_name or '（整模块）')


def extract_nav_prefix(actions):
    """从成功探索的动作序列里，提取「固定导航片段」并识别模块/子功能名。

    导航片段 = 从开头连续出现的 click/wait，直到遇到第一个 type/upload/press 为止。
    只保留可稳定回放的动作：click 需有 label（否则无法按文字定位，导航在此截断）；
    goto 由 runner 每次统一执行，这里不固化。

    模块名 = 第一个 click 的 label（如「达人管理」）；
    子功能名 = 第二个 click 的 label（如「上传达人」），没有第二个则等于模块名。

    返回 (module_name, feature_name, nav_actions)。nav_actions 可能为空。
    """
    nav = []
    module_name = ''
    feature_name = ''
    for a in actions or []:
        act = a.get('action')
        if act in _NAV_END_ACTIONS:
            break
        if act == 'click':
            label = (a.get('label') or '').strip()
            if not label:
                break  # 无文字，无法稳定回放，截断
            nav.append({'action': 'click', 'label': label})
            if not module_name:
                module_name = label
            elif not feature_name:
                feature_name = label
        elif act == 'wait':
            ms = a.get('ms')
            if ms is None:
                try:
                    ms = int(a.get('text'))
                except (TypeError, ValueError):
                    ms = 0
            if ms and ms > 0:
                nav.append({'action': 'wait', 'ms': ms})
        # goto 不固化
    feature_name = feature_name or module_name
    return module_name, feature_name, nav


def _click_by_label(page, label):
    """按元素文字点击（回放固化导航用，避免依赖每次变化的 ref）。

    加固点：优先精确匹配（exact=True），精确匹配不到时才用包含匹配，
    且两个都找不到时直接抛错（而不是静默点空）。是否「点错/没到位」由
    replay_nav_actions 回放后统一校验兜底。
    """
    loc = page.get_by_text(label, exact=True)
    if loc.count() == 0:
        loc = page.get_by_text(label, exact=False)
    if loc.count() == 0:
        raise ExploreError(f'页面上找不到文字「{label}」')
    loc.first.click(timeout=10000)


def guess_nav_keys(goal):
    """从目标描述里猜测要执行的「模块/子功能」名，用于匹配分层缓存。

    策略：从 goal 里切出已固化缓存中的模块名/子功能名（精确子串匹配）。
    返回 (module_name, feature_name)，都未命中返回 (None, None)。
    """
    if not goal:
        return None, None
    data = _load_modules_cache()
    matched_module = None
    for module_name in data:
        if module_name and module_name in goal:
            matched_module = module_name
            break
    if not matched_module:
        return None, None
    matched_feature = None
    mod = data.get(matched_module) or {}
    for feature_name in mod:
        if feature_name and feature_name in goal and feature_name != matched_module:
            matched_feature = feature_name
            break
    return matched_module, matched_feature


def replay_nav_actions(page, nav_actions, expected_label=None):
    """回放固化的导航片段。失败抛 ExploreError，由调用方决定是否退化重新探索。

    :param expected_label: 期望最终到达的节点名（通常为模块名或子功能名），
                           回放完成后校验页面可见文本是否包含它，包含才算真的到位。
    """
    last_click_label = ''
    for a in nav_actions or []:
        act = a.get('action')
        if act == 'click':
            label = a.get('label')
            if not label:
                raise ExploreError('导航片段缺少 click label')
            try:
                _click_by_label(page, label)
                last_click_label = label
            except Exception as e:  # noqa: BLE001
                raise ExploreError(f'回放导航点击「{label}」失败：{e}')
        elif act == 'wait':
            try:
                ms = int(a.get('ms') or 0)
            except (TypeError, ValueError):
                ms = 0
            if ms > 0:
                page.wait_for_timeout(ms)
        elif act == 'goto':
            # 兼容旧缓存里可能含 goto
            url = a.get('url')
            if url:
                page.goto(url, wait_until='domcontentloaded', timeout=30000)

    # 回放后校验是否真的到位：页面可见文本应包含目标节点名（菜单点击后通常页面会渲染该模块标题/菜单）。
    # 校验失败说明「点错或没跳转」，抛错交由上层退化重新探索，避免在错误页面瞎操作。
    check_label = expected_label or last_click_label
    if check_label:
        try:
            page.wait_for_timeout(800)
            visible = page.inner_text('body') or ''
        except Exception as e:  # noqa: BLE001
            raise ExploreError(f'回放后校验页面失败：{e}')
        if check_label not in visible:
            raise ExploreError(f'回放后未进入目标节点「{check_label}」，页面未出现该文字，疑似点错')


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


def run_explore_loop(page, goal, max_rounds=10, upload_file_path=None, start_url=None, on_progress=None):
    """在 page 上执行自主探索循环，直到 AI 声明 done。

    :param upload_file_path: 上传类巡检要上传的本地文件绝对路径；为 None 时 AI 无法执行 upload 动作
    :param start_url:        入口 URL，用于「导航片段」的固化/回放缓存；为 None 时不启用缓存
    :param on_progress:      每步关键动作执行后回调 on_progress(text)，用于实时回报进度（可为 None）

    返回 (success, actions, last_note)：
      - success: bool，是否达成目标
      - actions: list，真实执行过的动作序列（供 finalize 反推规范）
      - last_note: AI 最后一句说明（成功说明或失败卡点）
    """
    from .prompts import build_explorer_system_prompt

    system = build_explorer_system_prompt(upload_file_path=upload_file_path)
    history = []
    performed_actions = []  # 真实走通的完整动作序列（含已回放的导航片段）

    # ── 回放已固化的导航片段（如「点达人管理菜单」），避免每次重复探索同一段导航 ──
    # 按目标描述猜测模块/子功能，命中分层缓存则回放对应导航。
    nav_result = None
    if start_url:
        module_name, feature_name = guess_nav_keys(goal)
        nav_result = load_nav_actions(module_name, feature_name) if module_name else None
    replayed = False
    if nav_result:
        nav_actions, _module, _feature = nav_result
        try:
            # 回放后校验是否真的进入了目标节点（模块/子功能），点错或没跳转会抛错
            replay_nav_actions(page, nav_actions, expected_label=(_feature if _feature != _module else _module))
            replayed = True
            # 把回放的导航合并进动作序列，反推规范时仍能保留导航步骤
            performed_actions = list(nav_actions)
            explore_logger.info('[巡检探索] 已回放固化导航 {}/{}：{} 个动作，跳过重复探索',
                                _module, _feature, len(nav_actions))
            try:
                page.wait_for_timeout(1000)
            except Exception:  # noqa: BLE001
                pass
        except ExploreError as e:
            explore_logger.warning('[巡检探索] 回放固化导航失败，退化重新探索：{}', e)
            # 回放失败 → 该条缓存已失效，清除后下次重新探索并重新固化
            remove_nav_actions(_module, _feature if _feature != _module else None)
            replayed = False
            performed_actions = []

    explore_logger.info('[巡检探索] 目标={} 开始，最多 {} 轮，上传文件={}', goal, max_rounds, upload_file_path or '（未配置）')

    for round_no in range(1, max_rounds + 1):
        state = observe_page(page)
        observe_text = _format_observe(state)
        history_text = _build_history_text(history)

        nav_hint = ''
        if replayed:
            nav_hint = '\n\n（已通过固化导航进入目标页面，请直接从当前页面执行目标操作，不要再重复点击导航菜单。）'

        user = (
            f'目标：{goal}\n\n'
            f'—— 第 {round_no} 轮观察 ——\n'
            f'{observe_text}\n\n'
            f'—— 历史 ——\n{history_text}\n'
            f'{nav_hint}\n\n'
            '请根据当前页面与目标，输出下一轮决策 JSON。'
        )

        explore_logger.info('[巡检探索] 第 {} 轮观察：元素 {} 个，列表数据={}',
                            round_no, len(state.get('elements') or []), state.get('has_list_data'))

        messages = [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ]
        reply = _call_ai(messages)
        decision = _parse_decision(reply)
        explore_logger.info('[巡检探索] 第 {} 轮 AI 决策：{}', round_no, (reply or '')[:500])

        if decision is None:
            history.append({'note': '（AI 返回无法解析）', 'actions': [], 'result': f'解析失败：{reply[:200]}'})
            continue

        note = decision.get('note', '')
        done = bool(decision.get('done'))
        failed = bool(decision.get('failed'))

        if done:
            if failed:
                explore_logger.warning('[巡检探索] 第 {} 轮 AI 声明失败：{}', round_no, note)
                return False, performed_actions, note
            explore_logger.info('[巡检探索] 第 {} 轮 AI 声明完成：{}', round_no, note)
            # 探索成功 → 从真实动作序列里提取「固定导航前缀 + 模块/子功能名」分层固化，
            # 供下次按模块/子功能直接回放。回放模式下 AI 不再导航，提取出的前缀为空，不会误覆盖已有缓存。
            if start_url and not replayed:
                module_name, feature_name, nav = extract_nav_prefix(performed_actions)
                save_nav_actions(module_name, feature_name, nav)
            return True, performed_actions, note

        actions = decision.get('actions') or []
        if not isinstance(actions, list):
            actions = []
        actions = actions[:_MAX_ACTIONS_PER_ROUND]

        round_result_parts = []
        round_ok = True
        for act in actions:
            action_name = act.get('action')
            # 执行前补上 ref 对应的元素文字，反推规范时能给出确定性元素名
            if action_name in ('click', 'type', 'upload') and act.get('ref') is not None:
                act['label'] = _ref_label(state.get('elements') or [], act.get('ref'))
            try:
                result_text = _do_action(page, act, state.get('elements') or [], upload_file_path=upload_file_path)
                performed_actions.append(act)
                round_result_parts.append(result_text)
                explore_logger.info('[巡检探索] 第 {} 轮执行 {} ref={} text={} → 成功',
                                    round_no, action_name, act.get('ref'), act.get('text', ''))
                # 关键动作执行成功后实时回报（wait/goto 这类辅助动作不打扰）
                if on_progress and action_name in ('click', 'type', 'upload'):
                    from .runner import _describe_action
                    on_progress(f'✅ {_describe_action(act)}，结果 ✅ 通过')
            except ExploreError as e:
                round_ok = False
                round_result_parts.append(f'失败：{e}')
                explore_logger.warning('[巡检探索] 第 {} 轮执行 {} ref={} 失败：{}',
                                       round_no, action_name, act.get('ref'), e)
                if on_progress and action_name in ('click', 'type', 'upload'):
                    from .runner import _describe_action
                    on_progress(f'❌ {_describe_action(act)}，结果 ❌ 失败：{e}')
            except Exception as e:  # noqa: BLE001
                round_ok = False
                round_result_parts.append(f'异常：{e}')
                explore_logger.error('[巡检探索] 第 {} 轮执行 {} 异常：{}',
                                     round_no, action_name, e)
                if on_progress and action_name in ('click', 'type', 'upload'):
                    from .runner import _describe_action
                    on_progress(f'❌ {_describe_action(act)}，结果 ❌ 失败：{e}')

        history.append({
            'note': note,
            'actions': actions,
            'result': ' | '.join(round_result_parts) if round_result_parts else '（本轮无动作）',
        })

        # 等页面渲染后再进入下一轮观察
        try:
            page.wait_for_timeout(1000)
        except Exception:  # noqa: BLE001
            pass

    explore_logger.error('[巡检探索] 达到最大轮数 {}，仍未达成目标', max_rounds)
    return False, performed_actions, f'探索达到最大轮数（{max_rounds}）仍未达成目标'
