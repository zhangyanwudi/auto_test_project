# -*- coding: utf-8 -*-
"""
Case：达人管理 → 上传达人 → 单个上传

数据来自 page_patrol/examples/达人管理.example.json 的 operations.单个上传.data（可直接修改）。
通过统一入口执行：
  ./debug_task.sh page_patrol_task.py case --case 达人管理-上传达人-单个上传.py            # 执行
  ./debug_task.sh page_patrol_task.py case --case 达人管理-上传达人-单个上传.py --dry-run  # 只校验计划
"""
import copy

# 保存开关：人工确认表单操作无误后改为 True。False 时不点「保存」、不做保存后的校验，不会写入数据。
SAVE_ENABLED = True  # 保存已开启：点击「保存」并校验列表中出现本次唯一标识的达人名称

CASE_NAME = '达人管理-上传达人-单个上传'
JSON_PATH_IN_EXAMPLES = 'examples/达人管理.example.json'
TARGET = '达人管理--上传达人--单个上传'

# 上传成功并校验通过后，缓存唯一标识与达人类型，并调用下一个 case
CHAIN_NEXT = '订单履约-创建订单.py'
CACHE_NAME = 'page_patrol_cache'
CACHE_KEY = 'last_upload'


def build(data):
    """返回本次执行用的 JSON 副本：补上 run 参数，并按 SAVE_ENABLED 处理保存步骤。"""
    data = copy.deepcopy(data)
    data['run'] = {'target': TARGET, 'inputs': {}, 'filters': {}}
    op = data['pages']['上传达人']['operations']['单个上传']
    if not SAVE_ENABLED:
        # 关闭保存：去掉「保存」步骤与保存后的校验，只操作表单，不写入数据
        op['steps'] = [s for s in op['steps'] if not (s.get('action') == 'click' and s.get('label') == '保存')]
        op['verify'] = None
        op['verify_row'] = None
    return data
