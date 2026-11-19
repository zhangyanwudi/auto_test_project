# -*- coding: utf-8 -*-
"""
Case：订单履约 → 创建订单

两种入口：
  1. 链式：上传达人 case 成功并校验通过后自动调用（chained=True），
     昵称取上传时的唯一标识 {{user_name}}（从 persist 缓存 last_upload 读取）。
  2. 直接执行：必须传入 --order_type=koc 或 kol：
       koc → 昵称 ZnYan
       kol → 昵称 ZnYan-kol

订单数据（活动名称、平台、报价）来自 page_patrol/examples/订单履约.example.json 的
operations.创建订单.data，可直接修改。

命令：
  ./debug_task.sh page_patrol_task.py case --case 订单履约-创建订单.py --order_type=koc
  ./debug_task.sh page_patrol_task.py case --case 订单履约-创建订单.py --order_type=kol --dry-run

流程：筛选达人 → 行内「创建订单」→ 活动/平台/报价 → 右下角「创建订单」（生成草稿进入表单）
      → 循环 5 行（视频类型、产品类型、单支价格、合作年月、受众截图，行内「+」新增）→ 「提交审核」
"""
import copy

from base_utils.persist_base import PersistBase

# 提交开关：人工确认表单操作无误后改为 True。False 时不点击最终「提交审核」。
SAVE_ENABLED = True  # 人工确认后再打开（控制最终「提交审核」）

CASE_NAME = '订单履约-创建订单'
JSON_PATH_IN_EXAMPLES = 'examples/订单履约.example.json'
TARGET = '订单履约--创建订单'

# 与上传达人 case 共用的缓存（persist_base）
CACHE_NAME = 'page_patrol_cache'
CACHE_KEY_UPLOAD = 'last_upload'

# 本 case 最近一次提交成功的订单（只保留一个，新运行覆盖旧值）
CACHE_KEY_ORDER = 'last_order'

KOC_NICKNAME = 'ZnYan'
KOL_NICKNAME = 'ZnYan-kol'


def resolve_nickname(order_type=None, chained=False):
    """返回本次订单要筛选的达人昵称。"""
    if chained:
        info = PersistBase(CACHE_NAME).get(CACHE_KEY_UPLOAD)
        if not info or not info.get('nickname'):
            raise ValueError('缓存中没有上传达人的记录，请先执行「上传达人」case')
        return info['nickname']
    if order_type not in ('koc', 'kol'):
        raise ValueError('直接执行本 case 必须传入 --order_type=koc 或 --order_type=kol')
    return KOC_NICKNAME if order_type == 'koc' else KOL_NICKNAME


def build(data, order_type=None, chained=False):
    """返回本次执行用的 JSON 副本：补上 run 参数，并按 SAVE_ENABLED 处理最终提交步骤。"""
    nickname = resolve_nickname(order_type=order_type, chained=chained)
    data = copy.deepcopy(data)
    data['run'] = {'target': TARGET, 'inputs': {'达人昵称': nickname}, 'filters': {}}
    op = data['pages']['达人列表']['operations']['创建订单']
    if not SAVE_ENABLED:
        # 关闭提交：去掉最终「提交审核」点击与 verify_row。注意：前面的「创建订单」会生成订单草稿，保留它才能进入表单
        op['steps'] = [s for s in op['steps'] if not (s.get('action') == 'click' and s.get('label') == '提交审核')]
        op['verify_row'] = None
    return data


def expected(order_type=None, chained=False):
    """返回 (达人昵称, 期望的达人类型)。链式调用时取上传达人 case 缓存的昵称与达人类型。"""
    if chained:
        info = PersistBase(CACHE_NAME).get(CACHE_KEY_UPLOAD) or {}
        return info.get('nickname'), str(info.get('达人类型', '')).upper()
    return resolve_nickname(order_type=order_type), order_type.upper()


def _fill_order_id_filter(page, order_id):
    """在订单履约列表的筛选区填入「订单ID」。

    页面结构：左侧文字「订单ID」，右侧输入框 placeholder 为「请输入」（不与标签关联），
    因此不能按 placeholder / label 定位，改为「订单ID 文字 → 其后最近的可见输入框」。
    """
    # 逐级尝试：标签关联 → 紧随标签的输入框 → 表头同级筛选区首个可见输入框
    candidates = [
        page.get_by_label('订单ID', exact=True),
        page.locator('xpath=//*[normalize-space(.)="订单ID" and not(*[normalize-space(.)="订单ID"])]'
                     '/following::input[1]'),
    ]
    for loc in candidates:
        try:
            if loc.count() == 0:
                continue
            target = None
            for i in range(min(loc.count(), 10)):
                el = loc.nth(i)
                if el.is_visible() and el.is_editable():
                    target = el
                    break
            if target is None:
                continue
            target.click(timeout=5000)
            target.fill(str(order_id), timeout=10000)
            return
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError('订单列表页找不到「订单ID」筛选输入框')


def make_post_check(data, nickname, expect_type):
    """提交审核后的校验：

    1. 从「提交审核」请求的 POST body 里取 order_id
       （这里是提审时实际提交的订单，最贴近真实场景；该接口响应体不含 order_id）；
    2. 进入订单履约列表，按「订单ID」筛选，只校验筛选出来的这一行：
       订单状态=提审阶段、达人类型=期望类型、产品类型=本次提交的产品组合；
       （达人昵称不再校验，订单ID 已唯一确定记录）
    3. 通过后把订单ID写入缓存（键 last_order，覆盖旧值）。

    依赖 patrol_core.execute 通过 response_watch 捕获该请求，并以 captured 第二参数传入：
    captured[键] = {'request': 请求体 dict, 'response': 响应体 dict}。
    """
    products = {d['产品类型'] for d in data['pages']['达人列表']['operations']['创建订单']['data']['订单']}

    def _check(page, captured=None):
        from apps.case_govern.case_runner import explorer as ex

        # 1. 从提审请求的 POST body 取 order_id
        req = (captured or {}).get('提交审核') or {}
        body = req.get('request') or {}
        order_id = str(body.get('order_id') or '').strip()
        if not order_id:
            return False, f'未能从「提交审核」请求体中取到 order_id（请求体：{body}）', None
        print(f'✅ 从提审请求体取到订单ID：{order_id}')

        # 2. 进入订单履约列表，按订单ID筛选
        ex._click_by_label(page, '订单履约')
        page.wait_for_timeout(2500)
        try:
            _fill_order_id_filter(page, order_id)
        except Exception as e:  # noqa: BLE001
            return False, f'订单列表页找不到「订单ID」筛选框：{e}', None
        ex._click_by_label(page, '查询')
        page.wait_for_timeout(2500)

        heads = page.evaluate("() => [...document.querySelectorAll('thead th')].filter(e=>e.offsetParent).map(e=>e.innerText.trim())")
        rows = page.evaluate("() => [...document.querySelectorAll('tbody tr')].filter(e=>e.offsetParent).map(e=>[...e.querySelectorAll('td')].map(t=>t.innerText.trim()))")
        need = ['订单ID', '订单状态', '达人类型', '产品类型']
        if any(n not in heads for n in need):
            return False, f'订单列表表头缺少字段：{need}（实际：{heads}）', None
        col = {n: heads.index(n) for n in need}

        matched = [r for r in rows if len(r) == len(heads) and r[col['订单ID']] == order_id]
        if not matched:
            return False, f'按订单ID「{order_id}」筛选后未查到记录', None
        if len(matched) > 1:
            return False, f'按订单ID「{order_id}」筛选出 {len(matched)} 条记录，订单ID应唯一', None

        r = matched[0]
        status = r[col['订单状态']]
        if status != '提审阶段':
            return False, f'订单 {order_id} 状态为「{status}」，期望「提审阶段」', None
        if r[col['达人类型']] != expect_type:
            return False, f'订单 {order_id} 达人类型为「{r[col["达人类型"]]}」，期望「{expect_type}」', None
        got = {x.strip() for x in r[col['产品类型']].split(',') if x.strip()}
        if got != products:
            return False, f'订单 {order_id} 产品类型不符：期望 {sorted(products)}，实际 {sorted(got)}', None

        payload = {'order_id': order_id, 'nickname': nickname, 'order_type': expect_type,
                   'status': status, 'products': sorted(got)}
        PersistBase(CACHE_NAME).put(CACHE_KEY_ORDER, payload)
        return True, f'订单 {order_id} 校验通过（提审阶段 / {expect_type} / {len(got)} 个产品），已写入缓存 {CACHE_KEY_ORDER}', payload
    return _check


# 需要从接口响应中捕获的字段：{回调里用的键名: 请求 URL 片段}
RESPONSE_WATCH = {'提交审核': '/kol/api/orders/approval/create'}
