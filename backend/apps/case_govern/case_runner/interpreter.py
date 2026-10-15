# -*- coding: utf-8 -*-
"""
指令解释器：把操作 JSON 的每个 step 翻译成 Playwright 动作执行。

每个 step 执行前后通过 StepLogger 记录日志（步骤序号/节点/类型/目标/结果/耗时）。
"""
import re


class StepExecutionError(Exception):
    """步骤执行失败。"""


def _wait_ms_spec(step):
    """从 wait 步骤里解析等待时长（毫秒）；支持 wait(selector) 或 wait(N秒)。"""
    # 若有 selector 则等待元素
    if step.get('selector'):
        return None  # None 表示等待元素
    # 尝试从 text/ms 里解析
    for key in ('ms', 'text'):
        v = step.get(key)
        if v is None:
            continue
        if isinstance(v, (int, float)):
            return int(v)
        m = re.search(r'(\d+)\s*(?:秒|s)?', str(v))
        if m:
            return int(m.group(1)) * 1000
    return 3000  # 默认 3 秒


def execute_steps(page, steps, step_logger):
    """在给定 page 上逐步执行 steps，每步记录日志。

    返回 (是否全部通过, 错误信息或 None)。
    遇到断言失败/异常不会中断后续步骤的日志记录，但会标记失败并返回。
    """
    total = len(steps)
    has_failure = False
    first_error = None

    for i, step in enumerate(steps, start=1):
        action = step.get('action')
        target = step.get('selector') or step.get('url') or step.get('text') or ''
        step_logger.start_step(i, total, action, node_title=step.get('node_title', ''),
                               node_type=step.get('node_type', ''), target=target)

        try:
            _run_single(page, step)
            step_logger.end_step(True, '通过')
        except StepExecutionError as e:
            has_failure = True
            first_error = first_error or str(e)
            step_logger.end_step(False, str(e))
        except Exception as e:  # noqa: BLE001 兜底捕获
            has_failure = True
            first_error = first_error or str(e)
            step_logger.end_step(False, f'异常：{e}')

    return (not has_failure), first_error


def _run_single(page, step):
    """执行单个步骤，失败抛 StepExecutionError。"""
    action = step.get('action')
    if action == 'goto':
        url = step.get('url') or step.get('selector')
        if not url:
            raise StepExecutionError('goto 缺少 url')
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
    elif action == 'click':
        _click(page, step.get('selector'))
    elif action == 'type':
        _type(page, step.get('selector'), step.get('text', ''))
    elif action == 'wait':
        _wait(page, step)
    elif action == 'assert':
        _assert(page, step)
    elif action == 'screenshot':
        # 截图由 runner 统一处理，这里仅标记
        pass
    elif action == 'press':
        page.keyboard.press(step.get('key', 'Enter'))
    else:
        raise StepExecutionError(f'未知动作：{action}')


def _resolve_selector(selector):
    """把用户/节点的描述性 selector 规整为 Playwright 可用的 selector。"""
    s = (selector or '').strip()
    if not s:
        raise StepExecutionError('selector 为空')
    # 已是 css/xpath 风格的直接返回
    return s


def _click(page, selector):
    sel = _resolve_selector(selector)
    # 优先用 text= 按钮文字定位，其次直接 css
    locator = page.get_by_text(sel, exact=False).first if _looks_like_text(sel) else page.locator(sel)
    try:
        locator.click(timeout=10000)
    except Exception:
        # 兜底：尝试 css 定位
        page.locator(sel).click(timeout=10000)


def _looks_like_text(sel):
    """判断 selector 是否更像「按钮/链接文字」而非 css/xpath。"""
    return not re.search(r'[#\.\[\]=>:\*]', sel) and not sel.startswith('//')


def _type(page, selector, text):
    sel = _resolve_selector(selector)
    page.locator(sel).fill(str(text), timeout=10000)


def _wait(page, step):
    sel = step.get('selector')
    if sel:
        page.locator(sel).wait_for(state='visible', timeout=10000)
    else:
        ms = _wait_ms_spec(step)
        page.wait_for_timeout(ms)


def _assert(page, step):
    mode = step.get('mode', 'exists')
    sel = step.get('selector')
    text = step.get('text', '')
    if mode == 'contains':
        # 断言页面/容器文本包含指定文字
        body_text = page.locator(sel).inner_text() if sel and sel != 'body' else page.inner_text('body')
        if text and text not in body_text:
            raise StepExecutionError(f'未找到文本「{text}」')
    elif mode == 'has_data':
        # 断言列表/表格有数据（行数 > 0）
        count = page.locator(f'{sel} tr, {sel} [class*=item], {sel} [class*=row], {sel} tbody tr').count()
        if count == 0:
            # 兜底：直接数容器下第一层子元素
            count = page.locator(sel).locator('*').count()
        if count == 0:
            raise StepExecutionError('列表未加载出数据')
    elif mode == 'clickable':
        loc = page.locator(sel)
        if not loc.count():
            raise StepExecutionError(f'元素不存在：{sel}')
        if not loc.first.is_enabled():
            raise StepExecutionError(f'元素不可点击：{sel}')
    elif mode == 'exists':
        if not page.locator(sel).count():
            raise StepExecutionError(f'元素不存在：{sel}')
    else:
        raise StepExecutionError(f'未知断言 mode：{mode}')
