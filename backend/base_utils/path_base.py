import json
import os, shutil, sys


def check_dir(path_name):
    """
    检查路径是否存在，不存在则创建
    :param path_name:
    :return:
    """
    if not exists(path_name):
        os.mkdir(path_name)


def check_dirs(path_name):
    """
    检查目录是否存在，不存在路径中所有目录
    :param path_name:
    :return:
    """
    if not exists(path_name):
        os.makedirs(path_name)


def check_file(file_path):
    """
    检查文件是否存在
    :param file_path:       文件路径
    :return:
    """
    if not exists(file_path):
        return False
    return True


def check_is_file(file_path):
    """
    判断是否为文件
    """
    return os.path.isfile(file_path)


def exists(file_path):
    """
    判断文件是否存在
    :param file_path:
    :return:
    """
    return os.path.exists(file_path)


def remove(file_path):
    """移除文件"""
    if exists(file_path):
        os.remove(file_path)


def rmtree_directory(file_path):
    """移除目录（不存在则忽略，删除失败不抛）。"""
    if exists(file_path):
        shutil.rmtree(file_path, ignore_errors=True)


def get_path(file_path=__file__, index=0):
    """获取文件所在目录"""
    if getattr(sys, 'frozen', False):
        path = os.path.dirname(sys.executable)
    else:
        path = os.path.dirname(file_path)
    path_list = str(path).split("/")
    path_len = len(path_list)
    if index >= path_len - 1:
        return "/"
    else:
        return "/".join(path_list[0:path_len - index])


def get_parent_path(file_path=__file__):
    """获取文件所在上上层目录"""
    return os.path.dirname(os.path.dirname(file_path))


def joint_path(*parts):
    """拼接路径；支持多段，空值跳过，结果经 normpath 规范化。"""
    clean = [str(p) for p in parts if p is not None and str(p) != '']
    if not clean:
        return ''
    return os.path.normpath(os.path.join(*clean))


def get_folder_name(file_path, is_extension=True):
    """
    获取文件或目录名称
    :param file_path: 目录或文件目录
    :param is_extension: 是否显示扩展名，   True-默认显示    False-不显示
    :return:
    """
    if not is_extension and "." in str(file_path):
        return str(os.path.basename(file_path)).rpartition(".")[0]
    return os.path.basename(file_path)


def join_parent(path1, path2):
    """拼接父级目录下的子目录"""
    return joint_path(get_parent_path(path1), path2)


def get_directory_file(path, folder_only=False, file_type=None, exclude_names: list = None, include_names: list = None,
                       is_join_path=False, filter_dot_prefix=True, exclude_exact=False, files_only=False):
    """
    获取指定目录下的文件和文件夹，根据条件进行筛选，排除指定文件和文件夹，按名称模糊匹配

    Args:
        path (str): 指定目录的路径
        folder_only (bool): 是否仅显示文件夹，默认为 False，显示所有文件和文件夹
        file_type (list): 指定文件类型，仅显示该类型文件，默认为 None，显示所有类型文件
        exclude_names (list): 需要排除的文件或文件夹列表，默认为 None，不排除任何文件或文件夹
        include_names (list): 文件名称包含的字符串；['.'] 表示仅保留 basename 中含「.」的普通文件（通常即有扩展名）
        is_join_path：是否拼接路径，默认不拼接，True-拼接
        filter_dot_prefix: 为 True 时排除以 . 与 __ 开头的项（默认，与历史行为一致）
        exclude_exact: 为 True 时 exclude_names 按完整名称匹配，否则为子串匹配
        files_only: 为 True 且非 folder_only 时，仅保留文件（不含子目录）

    Returns:
        list: 符合条件的文件和文件夹列表（名称排序）
    """
    if not path or not os.path.isdir(path):
        return []
    items = os.listdir(path)
    # 仅显示文件夹
    if folder_only:
        items = [item for item in items if os.path.isdir(os.path.join(path, item))]
    elif files_only:
        items = [item for item in items if os.path.isfile(os.path.join(path, item))]
    # 仅显示特定类型文件
    if file_type:
        items = [item for item in items if
                 os.path.isfile(os.path.join(path, item)) and any(item.endswith(ft) for ft in file_type)]
    # 排除指定文件或文件夹
    if exclude_names:
        if exclude_exact:
            items = [item for item in items if item not in exclude_names]
        else:
            items = [item for item in items if not any(exclude in item for exclude in exclude_names)]
    # 按名称模糊匹配（与 apis/operate_tool/path_utils 语义对齐的分支）
    if include_names:
        if include_names == ['.'] or (len(include_names) == 1 and include_names[0] == '.'):
            items = [item for item in items if '.' in item and os.path.isfile(os.path.join(path, item))]
        elif any((x == '.json' or (isinstance(x, str) and x.endswith('.json'))) for x in include_names):
            items = [item for item in items if item.endswith('.json') and os.path.isfile(os.path.join(path, item))]
        else:
            items = [item for item in items if any(include_name in item for include_name in include_names)]
    if filter_dot_prefix:
        items = [item for item in items if not item.startswith('.') and not item.startswith('__')]
    items = sorted(items)
    if is_join_path:
        items = [joint_path(path, item) for item in items]
    return items


def setting_environ_path(path_name, env_key='PATH'):
    """将目录设置为环境目录"""
    paths = os.environ.get(env_key, '')
    if path_name not in paths:
        os.environ[env_key] = path_name + os.pathsep + paths
        print(f"设置环境路径：【{path_name}】成功")
        return
    print(f"已设置环境路径：{path_name}")


def get_environ_path(env_key='PATH'):
    """获取环境目录"""
    return os.getenv(env_key)


def copy_dir(old_dir, new_dir):
    """复制目录"""
    # 如果目标目录已存在，删除目标目录
    if exists(new_dir):
        shutil.rmtree(new_dir)  # 小心，这会删除已存在的目录及其所有内容
    # 复制文件或文件夹到目标目录
    shutil.copytree(old_dir, new_dir)


def copy_file_to_dir(old_path, new_dir, new_name=None):
    """
    复制文件到目录
    :param old_path:        文件地址
    :param new_dir:         复制到目录
    :param new_name:        修改新的文件名称，要带扩展名
    :return:
    """
    # 复制文件或文件夹到目标目录
    shutil.copy(old_path, new_dir)
    if new_name:
        rename(old_name_path=joint_path(new_dir, get_folder_name(old_path)),
               new_name_path=joint_path(new_dir, new_name))


def rename(old_name_path, new_name_path=None, new_name=None):
    """重命名"""
    if not new_name_path and not new_name:
        raise ValueError(r"需提供新文件名称或新文件路径！")
    if new_name:
        # 获取目录
        new_dir = get_path(old_name_path)
        new_name_path = joint_path(new_dir, new_name)
    os.rename(old_name_path, new_name_path)
    return new_name_path

def get_file_time(file_path):
    """
    获取文件修改时间
    :param file_path:       文件路径
    :return:        时间戳
    """
    return os.path.getmtime(file_path)*1000

def recursion_dir(path,pre=None):
    """
    递归目录
    :return:
    """
    pre = pre if pre else []
    stack = [(pre, path)]
    while stack:
        pre, path = stack.pop()
        # 获取目录
        dirs=get_directory_file(path, folder_only=True)
        if dirs:
            # 有目录
            for dir in dirs:
                # 拼接下级路径
                next_path=joint_path(path,dir)
                # 拼接目录层级
                new_pre = pre+[dir]
                stack.append((new_pre,next_path))
        else:
            # 没有目录则获取文件
            files = get_directory_file(path, include_names=["."])
            if files:
                files.sort(reverse=True)  # 保持原排序逻辑
                for file in files:
                    new_pre=pre + [file]
                    yield new_pre


def recursion_get_file(path,split_label="--"):
    """递归获取目录下的文件"""
    files_result=[]
    file_lists = recursion_dir(path)
    for file_list in file_lists:
        files_result.append(f"{split_label}".join(file_list))
    return json.dumps(files_result,ensure_ascii=False)

if __name__ == "__main__":
    # print(get_directory_file("/Users/zhangyan/Desktop/ZnYan/135/tool_ad_creative_client/dist/未命名文件夹"))
    # print(get_path("/Users/zhangyan/Desktop/新产品立项/华南15期/Chat5/Chat5_K白包物料/图标/圆角/16.png"))
    print(recursion_get_file("/Users/admin/Desktop/ZnYan/hsabtest_config/ios_blcokblast/V102"))
    # print(get_directory_file(path=path, names=["icon", "图"]))
