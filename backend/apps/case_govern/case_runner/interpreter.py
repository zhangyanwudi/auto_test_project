# -*- coding: utf-8 -*-
"""
指令解释器：把操作 JSON 的每个 step 翻译成 Playwright 动作执行。

每个 step 执行前后通过 StepLogger 记录日志（步骤序号/节点/类型/目标/结果/耗时）。
"""
import re


class StepExecutionError(Exception):
    """步骤执行失败。"""


def _wait_ms_spec(step):
    """从 wait 步骤里解析等待时长（毫秒）；支持 wait(selector) 或 wait(N秒)。

    selector 可能是「等待元素出现」的 css/text，也可能是 AI 误把纯数字/N秒
    放进了 selector 字段（如 {"selector": 2000}），这里统一按值判断：
    纯数字或含「秒」的视为固定时长，其余才当作元素选择器返回 None。
    """
    sel = step.get('selector')
    if sel is not None:
        s = str(sel).strip()
        # 纯数字或含「秒/s」的写法 → 固定时长
        if re.fullmatch(r'\d+', s) or re.search(r'秒|[a-z]s?\b', s):
            if re.fullmatch(r'\d+', s):
                return int(s)
            m = re.search(r'(\d+)\s*(?:秒|s)?', s)
            return int(m.group(1)) * 1000 if m else 3000
        return None  # 否则视为等待元素
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


def _locate_form_input(page, sel, timeout=10000):
    """按表单字段 label 定位输入控件（适配 Arco/Element/Ant 等表单项结构）。

    巡检里用户用「筛选框条件（如 达人昵称）」描述要填的输入框，但这类
    筛选框 placeholder 多为「请输入」等通用文案、不唯一，直接用 placeholder
    定位会误伤其它输入框。这里把字段名当作 label 文本，在表单项内找到
    对应的 input/textarea 返回；找不到时返回 None，由调用方回退到 css 定位。
    """
    if not _looks_like_text(sel):
        return None
    name = sel[5:] if sel.startswith('text=') else sel
    if not name:
        return None
    item = page.locator(
        '.arco-form-item, .el-form-item, .ant-form-item, [class*="form-item"]'
    ).filter(has=page.get_by_text(name, exact=True))
    # 等表单项异步渲染出现（goto 后立即 type 时，筛选栏可能尚未挂载）
    try:
        item.first.wait_for(state='attached', timeout=timeout)
    except Exception:
        return None
    control = item.first.locator('input, textarea')
    return control if control.count() else None


def _type(page, selector, text):
    sel = _resolve_selector(selector)
    # 优先按字段 label 定位输入框（筛选框 placeholder 常为「请输入」，不唯一）
    loc = _locate_form_input(page, sel)
    if loc is not None:
        loc.fill(str(text), timeout=10000)
        return
    page.locator(sel).fill(str(text), timeout=10000)


def _wait(page, step):
    ms = _wait_ms_spec(step)
    if ms is not None:
        page.wait_for_timeout(ms)
    else:
        page.locator(step.get('selector')).wait_for(state='visible', timeout=10000)


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
        # 若给的是字段名（如 达人昵称），先尝试按 label 找到对应输入框/表单项，再按元素存在断言
        loc = _locate_form_input(page, sel) if _looks_like_text(sel) else None
        target = loc if loc is not None else page.locator(sel)
        if not target.count():
            raise StepExecutionError(f'元素不存在：{sel}')
    else:
        raise StepExecutionError(f'未知断言 mode：{mode}')
