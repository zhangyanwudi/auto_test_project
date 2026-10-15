# -*- coding: utf-8 -*-
"""
巡检步骤日志：每步执行都记录「步骤序号 / 节点信息 / 类型 / 目标 / 结果 / 耗时」。

- 即时日志：通过 logger 输出到后端日志文件，方便实时排查
- 内存明细：收集到 StepRunResult 列表，供试运行报告展示

不做落库（按需求只写日志，不建表）。
"""
import time

try:
    from base_utils.logger_base import logger
except ImportError:  # 兜底，避免 logger 模块不可用
    import logging
    logger = logging.getLogger('case_runner')


class StepRunResult:
    """单个步骤的执行结果（内存明细）。"""

    def __init__(self, index, action, node_title, node_type, target, status, message, cost_ms):
        self.index = index
        self.action = action
        self.node_title = node_title
        self.node_type = node_type
        self.target = target
        self.status = status        # pass / fail
        self.message = message      # 失败原因或成功说明
        self.cost_ms = cost_ms

    def to_dict(self):
        return {
            'index': self.index,
            'action': self.action,
            'node_title': self.node_title,
            'node_type': self.node_type,
            'target': self.target,
            'status': self.status,
            'message': self.message,
            'cost_ms': self.cost_ms,
        }


class StepLogger:
    """巡检执行器内部的步骤日志收集器。"""

    def __init__(self, case_name=''):
        self.case_name = case_name
        self.steps = []          # list[StepRunResult]
        self._start_time = None
        self._current = None     # 当前正在执行的步骤元信息

    def start_step(self, index, total, action, node_title='', node_type='', target=''):
        """步骤开始：记录起始时间，打一条「开始」日志。"""
        self._start_time = time.time()
        self._current = (index, total, action, node_title, node_type, target)
        logger.info(
            '[巡检] 用例={} 步骤{}/{} 类型={} 节点={!r} 目标={!r} —— 开始',
            self.case_name, index, total, action, node_title, target,
        )

    def end_step(self, ok, message=''):
        """步骤结束：计算耗时，记录结果，打一条「结果」日志。"""
        cost_ms = int((time.time() - self._start_time) * 1000) if self._start_time else 0
        index, total, action, node_title, node_type, target = self._current
        status = 'pass' if ok else 'fail'
        logger.info(
            '[巡检] 用例={} 步骤{}/{} 类型={} 节点={!r} 目标={!r} 结果={} 耗时={}ms {}',
            self.case_name, index, total, action, node_title, target,
            '通过' if ok else '失败', cost_ms, message,
        )
        self.steps.append(StepRunResult(
            index=index, action=action, node_title=node_title, node_type=node_type,
            target=target, status=status, message=message, cost_ms=cost_ms,
        ))
        self._start_time = None
        self._current = None

    def summary(self):
        """返回 (通过数, 失败数, 总步骤数)。"""
        total = len(self.steps)
        passed = sum(1 for s in self.steps if s.status == 'pass')
        failed = total - passed
        return passed, failed, total

    def to_list(self):
        return [s.to_dict() for s in self.steps]
