import json
import os

from base_utils.path_base import check_dirs, exists, get_path, joint_path, get_file_time, get_directory_file, remove


class PersistBase(object):

    def __init__(self, file_name, persist_dir=None, expiration_days=None) -> None:
        """
        缓存初始化
        :param file_name:       缓存文件名称
        :param persist_dir:     缓存目录
        :param expiration_days: 缓存文件过期天数  例：30
        """
        if not persist_dir:
            persist_dir = joint_path(get_path(__file__, index=1), "persist_data")
        check_dirs(persist_dir)
        self.persist_dir = persist_dir
        self.rel_path = os.path.normpath(os.path.join(persist_dir, f'{file_name}.json'))
        self._data = {}
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

    def keys(self):
        return self._data.keys()

    def get(self, key, default=None):
        return self._data.get(key, default)

    def put(self, key, value):
        self.put_only(key, value)
        self.flush()

    # def increment_only(self, key, value):
    #     if not self.contain(key):
    #         self.put_only()
    #     if isinstance(self._data[key], (int, float)) and isinstance(value, (int, float)):
    #         self._data[key] += value
    #     elif isinstance(self._data[key], str) and isinstance(value, str):
    #         self._data[key] += value
    #     else:
    #         raise TypeError("Incompatible types for incrementing")

    def contain(self, key):
        return key in self._data

    def put_only(self, key, value):
        self._data[key] = value

    def size(self):
        return len(self._data)

    def remove_only(self, key):
        if key in self._data:
            del self._data[key]

    def remove(self, key):
        self.remove_only(key)
        self.flush()

    def empty(self):
        self._data.clear()
        self.flush()

    def flush(self):
        with open(self.rel_path, 'w', encoding="utf-8") as stream:
            json.dump(self._data, stream, ensure_ascii=False)


if __name__=="__main__":
    persist_base=PersistBase("ip")
    print(persist_base.get("TH"))