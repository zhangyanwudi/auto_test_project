"""历史兼容：新代码请使用 base_utils.path_base（read_git_config 已改用 path_base）。"""
import os
import shutil
from pathlib import Path


def joint_path(*parts):
    """拼接并规范化路径。"""
    clean = [str(p) for p in parts if p is not None and str(p) != '']
    if not clean:
        return ''
    return os.path.normpath(os.path.join(*clean))


def exists(path):
    return os.path.exists(path)


def get_folder_name(file_name, is_extension=False):
    """file_name 为文件名；is_extension=False 时去掉扩展名。"""
    base = os.path.basename(file_name)
    if is_extension:
        return base
    return Path(base).stem


def rmtree_directory(path):
    """删除目录树（存在则删）。"""
    if path and exists(path):
        shutil.rmtree(path, ignore_errors=True)


def get_directory_file(path, exclude_names=None, folder_only=False, include_names=None):
    """
    列出目录下名称。
    - folder_only: 仅子目录
    - 否则为文件；include_names=['.json'] 仅 json；['.'] 表示需含扩展名的文件（basename 中含 '.'）
    """
    exclude_names = list(exclude_names or [])
    if not path or not os.path.isdir(path):
        return []
    out = []
    for name in sorted(os.listdir(path)):
        if name in exclude_names:
            continue
        full = joint_path(path, name)
        if folder_only:
            if os.path.isdir(full):
                out.append(name)
            continue
        if not os.path.isfile(full):
            continue
        if include_names:
            if include_names == ['.'] or (len(include_names) == 1 and include_names[0] == '.'):
                if '.' not in name:
                    continue
            elif any(x == '.json' or x.endswith('.json') for x in include_names):
                if not name.endswith('.json'):
                    continue
            else:
                if not any(name.endswith(ext) if ext.startswith('.') else (ext in name) for ext in include_names):
                    continue
        out.append(name)
    return out
