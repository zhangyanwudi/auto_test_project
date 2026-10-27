# -*- coding: utf-8 -*-
"""
巡检自主探索执行器：让 AI「观察页面 → 决策下一步 → 执行 → 失败回喂重试」，
直到完成用户目标或穷尽所有办法，而不是一次性盲写 selector 执行。

流程：
    打开起始 URL
      → 循环（最多 max_rounds 轮）：
          1. observe_page 提取当前页面可交互元素（带 ref 编号的清单）
          2. 把「清单 + 目标 + 历史」发给 AI，让它下指令（click/type/press/wait/goto）
          3. 按 ref 直接定位执行，记录结果
          4. 失败原因回喂给 AI，下一轮换方式重试
      → AI 声明 done（成功）或 failed（穷尽）
      → 返回真实走通的动作序列，供 finalize 反推规范

全程通过 case_explore 日志记录探索轨迹，失败时可按日志路径定位问题。
"""
import json
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

      // 1. 可点击元素：菜单项、链接、按钮、以及带点击语义的元素
      const clickables = document.querySelectorAll(
        'a, button, .arco-menu-item, .el-menu-item, .ant-menu-item, [class*="menu-item"], [role="menuitem"], [role="button"], [role="tab"], [class*="tab"], .arco-dropdown-menu-item'
      );
      clickables.forEach(el => {
        if (el.offsetWidth === 0 && el.offsetHeight === 0) return;
        const t = (el.innerText || el.getAttribute('aria-label') || el.title || '').trim();
        if (t) push(el, 'click', t);
      });

      // 2. 输入框：input / textarea / contenteditable，label 优先取关联表单项文字
      const inputs = document.querySelectorAll('input, textarea, [contenteditable="true"]');
      inputs.forEach(el => {
        if (el.type === 'hidden') return;
        if (el.offsetWidth === 0 && el.offsetHeight === 0 && el.tagName !== 'TEXTAREA') return;
        let label = '';
        const formItem = el.closest('.arco-form-item, .el-form-item, .ant-form-item, [class*="form-item"]');
        if (formItem) {
          const labelEl = formItem.querySelector('.arco-form-item-label, .el-form-item__label, .ant-form-item-label, label');
          if (labelEl) label = labelEl.innerText || '';
        }
        if (!label) label = el.getAttribute('placeholder') || el.getAttribute('aria-label') || el.name || '';
        push(el, 'input', label);
      });

      // 3. 下拉/选择
      const selects = document.querySelectorAll('select, [role="combobox"], .arco-select, [class*="select"]');
      selects.forEach(el => {
        if (el.offsetWidth === 0 && el.offsetHeight === 0) return;
        let label = '';
        const formItem = el.closest('.arco-form-item, .el-form-item, .ant-form-item, [class*="form-item"]');
        if (formItem) {
          const labelEl = formItem.querySelector('.arco-form-item-label, .el-form-item__label, .ant-form-item-label, label');
          if (labelEl) label = labelEl.innerText || '';
        }
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


def _do_action(page, action, elements):
    """执行单个动作，返回 (是否成功, 结果说明)。失败抛 ExploreError。"""
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


def run_explore_loop(page, goal, max_rounds=10):
    """在 page 上执行自主探索循环，直到 AI 声明 done。

    返回 (success, actions, last_note)：
      - success: bool，是否达成目标
      - actions: list，真实执行过的动作序列（供 finalize 反推规范）
      - last_note: AI 最后一句说明（成功说明或失败卡点）
    """
    from .prompts import build_explorer_system_prompt

    system = build_explorer_system_prompt()
    history = []
    performed_actions = []  # 真实走通的完整动作序列

    explore_logger.info('[巡检探索] 目标={} 开始，最多 {} 轮', goal, max_rounds)

    for round_no in range(1, max_rounds + 1):
        state = observe_page(page)
        observe_text = _format_observe(state)
        history_text = _build_history_text(history)

        user = (
            f'目标：{goal}\n\n'
            f'—— 第 {round_no} 轮观察 ——\n'
            f'{observe_text}\n\n'
            f'—— 历史 ——\n{history_text}\n\n'
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
            return True, performed_actions, note

        actions = decision.get('actions') or []
        if not isinstance(actions, list):
            actions = []
        actions = actions[:_MAX_ACTIONS_PER_ROUND]

        round_result_parts = []
        round_ok = True
        for act in actions:
            # 执行前补上 ref 对应的元素文字，反推规范时能给出确定性元素名
            if act.get('action') in ('click', 'type') and act.get('ref') is not None:
                act['label'] = _ref_label(state.get('elements') or [], act.get('ref'))
            try:
                result_text = _do_action(page, act, state.get('elements') or [])
                performed_actions.append(act)
                round_result_parts.append(result_text)
                explore_logger.info('[巡检探索] 第 {} 轮执行 {} ref={} text={} → 成功',
                                    round_no, act.get('action'), act.get('ref'), act.get('text', ''))
            except ExploreError as e:
                round_ok = False
                round_result_parts.append(f'失败：{e}')
                explore_logger.warning('[巡检探索] 第 {} 轮执行 {} ref={} 失败：{}',
                                       round_no, act.get('action'), act.get('ref'), e)
            except Exception as e:  # noqa: BLE001
                round_ok = False
                round_result_parts.append(f'异常：{e}')
                explore_logger.error('[巡检探索] 第 {} 轮执行 {} 异常：{}',
                                     round_no, act.get('action'), e)

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
