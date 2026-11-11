# -*- coding: utf-8 -*-
"""
数据存储缓存层：内存 + 可选落盘 JSON。

设计目标：
  1. 存数据：接口执行后把产物暂存，供后续接口直接取用，避免重复请求；
  2. 安全取数：取数据时即使还没写入也不报错（get 带默认值）；
  3. 惰性获取：取不到时自动调用取数函数补齐并回填（get_or_fetch）；
  4. 空值过滤：可选跳过空值（None/空字符串/空容器），避免无意义数据入缓存；
  5. 两种模式：memory_only 纯内存（不建目录/不读历史文件/不写 json 文件）、
     落盘 JSON（默认，跨进程/重启保留，与历史行为一致）。

与历史 PersistBase 的关系：保留类名与全部方法签名（get/put/put_only/contain/
remove/remove_only/empty/flush/keys/size/persist_dir），故既有调用方无需改动；
新增 memory_only、skip_empty 与 get_or_fetch 能力。
"""
import json
import os
import threading

from base_utils.path_base import check_dirs, exists, get_path, joint_path, get_file_time, get_directory_file, remove


class PersistBase(object):

    def __init__(self, file_name=None, persist_dir=None, expiration_days=None, memory_only=False):
        """
        缓存初始化
        :param file_name:       缓存文件名称（不含 .json）；memory_only=True 时可不传
        :param persist_dir:     缓存目录；默认 backend/persist_data
        :param expiration_days: 落盘模式下清理超过 N 天的缓存文件，例：30；None 不清理
        :param memory_only:     True-仅内存缓存，不建目录、不读历史文件、不写 json 文件；
                                False-持久化到 json 文件（默认，与历史行为一致）
        """
        self._memory_only = bool(memory_only)
        self._data = {}
        # get_or_fetch 的「检查-取数-写回」非原子，用可重入锁保护 _data 的读写
        self._lock = threading.RLock()

        # 纯内存模式：跳过所有磁盘操作
        if self._memory_only:
            self.persist_dir = persist_dir
            self.rel_path = None
            return

        if not persist_dir:
            persist_dir = joint_path(get_path(__file__, index=1), "persist_data")
        check_dirs(persist_dir)
        self.persist_dir = persist_dir
        self.rel_path = os.path.normpath(os.path.join(persist_dir, f'{file_name}.json'))
        if exists(self.rel_path):
            with open(self.rel_path, encoding='utf-8') as stream:
                json_string = stream.read().strip()
                if len(json_string) > 0:
                    self._data.update(json.loads(json_string))
        # 清除过期文件（惰性依赖 time_base / pytz，避免无过期策略时强绑）
        if expiration_days:
            from base_utils.time_base import get_before, timestamp_to_date

            persist_file_paths = get_directory_file(persist_dir, is_join_path=True)
            for persist_file_path in persist_file_paths:
                if timestamp_to_date(get_file_time(persist_file_path)) < get_before(days=expiration_days):
                    remove(persist_file_path)

    @staticmethod
    def _is_empty_value(value) -> bool:
        """判断值是否为空：None、空字符串、空容器视为空；0、False 等有意义的值不算空。"""
        if value is None:
            return True
        if isinstance(value, str) and value == "":
            return True
        if isinstance(value, (list, tuple, dict, set)) and len(value) == 0:
            return True
        return False

    # ── 基础读写 ──

    def keys(self):
        """返回键列表快照（list，锁释放后仍安全）。"""
        with self._lock:
            return list(self._data.keys())

    def get(self, key, default=None):
        """取数据；不存在返回 default，绝不抛异常。"""
        with self._lock:
            return self._data.get(key, default)

    def put(self, key, value, skip_empty=False):
        """存数据并落盘（内存模式下等价于 put_only）。

        :param skip_empty: True-值为空（None/空字符串/空容器）时不存；False-照常存（默认）
        """
        if skip_empty and self._is_empty_value(value):
            return
        with self._lock:
            self._data[key] = value
            self.flush()

    def contain(self, key):
        """判断键是否已存在。"""
        with self._lock:
            return key in self._data

    def put_only(self, key, value, skip_empty=False):
        """只存内存，不落盘。

        :param skip_empty: True-值为空（None/空字符串/空容器）时不存；False-照常存（默认）
        """
        if skip_empty and self._is_empty_value(value):
            return
        with self._lock:
            self._data[key] = value

    def size(self):
        """返回已存键数量。"""
        with self._lock:
            return len(self._data)

    def remove_only(self, key):
        """只从内存删除，不落盘。"""
        with self._lock:
            self._data.pop(key, None)

    def remove(self, key):
        """删除并落盘。"""
        with self._lock:
            self._data.pop(key, None)
            self.flush()

    def empty(self):
        """清空并落盘。"""
        with self._lock:
            self._data.clear()
            self.flush()

    def flush(self):
        """落盘；内存模式或无文件路径时跳过。"""
        if self._memory_only or not self.rel_path:
            return
        with open(self.rel_path, 'w', encoding="utf-8") as stream:
            json.dump(self._data, stream, ensure_ascii=False)

    # ── 惰性获取 ──

    def get_or_fetch(self, key, fetcher=None, default=None, force=False):
        """
        取数据；缓存命中（且非 force）直接返回缓存值。
        否则触发 fetcher()：fetcher 内部自行完成取数并存（调用 self.put/put_only），
        本方法只负责「触发」，不做取值解包——因为每个接口取数位置/返回结构不同，
        统一在此解包不合适。

        :param key:     缓存键
        :param fetcher: 无参取数函数，内部自行 put 数据；其返回值被忽略。
                        可不传：此时仅尝试从缓存读取，未命中直接返回 default
        :param default: 触发后仍未取到（或未传 fetcher）时的兜底值
        :param force:   True 强制重新触发 fetcher（未传 fetcher 时忽略）
        :return:        缓存值或 default
        """
        if not force:
            with self._lock:
                if key in self._data:
                    return self._data[key]

        # 未提供 fetcher 时不做触发，直接返回 default
        if fetcher is None:
            return default

        # 只触发，不解包返回值；取值与存入均由 fetcher 内部完成
        fetcher()

        with self._lock:
            return self._data.get(key, default)


if __name__ == "__main__":
    # 落盘模式（默认）：写入并读取
    store = PersistBase("ip")
    store.put("TH", "1.2.3.4")
    print(store.get("TH"))  # 1.2.3.4

    # 纯内存模式：不建目录、不生成 json 文件
    mem = PersistBase(memory_only=True)
    mem.put("project_code", "CPN20261010092")
    print(mem.get("project_code", ""))  # CPN20261010092
