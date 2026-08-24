"""简单 JSON 缓存，替代原 PersistBase。"""
import json
import os

from django.conf import settings


class GitConfigCache:
    """按 key 存 dict 到单文件，与 read_git_config 中 cache_data 用法兼容。"""

    def __init__(self, file_name='git_cache_data'):
        base = os.path.join(settings.BASE_DIR, 'data', 'git_config_cache')
        os.makedirs(base, exist_ok=True)
        self.persist_dir = base
        self._store_path = os.path.join(base, f'{file_name}.json')

    def get(self, key, default=None):
        # 可能被上游清理缓存目录，这里兜底重建
        os.makedirs(self.persist_dir, exist_ok=True)
        if not os.path.exists(self._store_path):
            return default
        try:
            with open(self._store_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get(key, default)
        except Exception:
            return default

    def put(self, key, value):
        # 可能被上游清理缓存目录，这里兜底重建
        os.makedirs(self.persist_dir, exist_ok=True)
        data = {}
        if os.path.exists(self._store_path):
            try:
                with open(self._store_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[key] = value
        with open(self._store_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
