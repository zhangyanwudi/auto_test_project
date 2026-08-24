import json
from typing import Any, Union, Dict, List


class JsonModifier:
    """
    JSON 字段修改器
    支持嵌套路径（如 "user.profile.name"）和数组索引（如 "items.0.price"）
    """

    @staticmethod
    def set_value(json_data: Union[str, Dict, List], field_path: str, value: Any) -> Union[Dict, List]:
        """
        修改单个字段值

        Args:
            json_data: JSON 字符串或解析后的 dict/list
            field_path: 字段路径，支持点号分隔（如 "user.name" 或 "items.0.id"）
            value: 新值

        Returns:
            修改后的 dict 或 list

        Example:
            >>> JsonModifier.set_value('{"user": {"name": "张三"}}', 'user.name', '李四')
            {'user': {'name': '李四'}}
        """
        # 如果是字符串，先解析为 Python 对象
        if isinstance(json_data, str):
            data = json.loads(json_data).copy()
        else:
            data = json_data.copy() if isinstance(json_data, (dict, list)) else json_data.copy()

        # 解析路径（支持 user.name 或 items.0.price 格式）
        keys = field_path.split('.')

        # 递归或迭代修改嵌套值
        current = data
        for i, key in enumerate(keys[:-1]):
            # 判断 key 是否为数组索引
            if key.isdigit():
                idx = int(key)
                if not isinstance(current, list) or idx >= len(current):
                    raise IndexError(f"数组索引越界: {key}，当前路径: {'.'.join(keys[:i + 1])}")
                current = current[idx]
            else:
                if key not in current:
                    # 自动创建不存在的路径（默认为 dict）
                    current[key] = {} if not keys[i + 1].isdigit() else []
                current = current[key]

        # 设置最终值
        final_key = keys[-1]
        if final_key.isdigit():
            idx = int(final_key)
            if isinstance(current, list):
                while len(current) <= idx:
                    current.append(None)
                current[idx] = value
            else:
                raise TypeError(f"尝试使用索引 {idx} 访问非数组对象")
        else:
            current[final_key] = value

        return data

    @staticmethod
    def set_values(json_data: Union[str, Dict, List], updates: Dict[str, Any]) -> Union[Dict, List]:
        """
        批量修改多个字段

        Args:
            json_data: JSON 字符串或解析后的对象
            updates: 字段路径与新值的映射字典

        Example:
            >>> updates = {'user.name': '李四', 'user.age': 25, 'tags.0': 'VIP'}
            >>> JsonModifier.set_values(json_str, updates)
        """
        if isinstance(json_data, str):
            data = json.loads(json_data)
        else:
            data = json_data.copy() if isinstance(json_data, dict) else json_data

        for field_path, value in updates.items():
            data = JsonModifier.set_value(data, field_path, value)

        return data

    @staticmethod
    def to_json_str(data: Union[Dict, List], pretty: bool = False) -> str:
        """将 Python 对象转换为 JSON 字符串"""
        indent = 2 if pretty else None
        return json.dumps(data, ensure_ascii=False, indent=indent)

    @staticmethod
    def get_nested_value(data: dict, path: str, separator: str = ".") -> Any:
        """
        根据路径获取嵌套值
        路径格式: "reload.reload_logic.retry_intervals"
        """
        keys = path.split(separator)
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    @staticmethod
    def set_nested_value(data: dict, path: str, value: Any, separator: str = ".") -> dict:
        """
        根据路径设置嵌套值
        """
        keys = path.split(separator)
        current = data

        # 遍历到倒数第二个key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # 设置最终值
        current[keys[-1]] = value
        return data

    @staticmethod
    def update_by_pattern(
            data: dict,
            pattern_key: str,  # 如 "ad_unit_"
            target_path: str,  # 如 "reload.reload_logic.retry_intervals"
            new_value: Any,
            separator: str = "."
    ) -> dict:
        """
        根据模式匹配动态节点名并更新值
        """
        updated_count = 0

        for key in list(data.keys()):
            if key.startswith(pattern_key):
                old_value = JsonModifier.get_nested_value(data[key], target_path, separator)
                if old_value is not None:
                    JsonModifier.set_nested_value(data[key], target_path, new_value, separator)
                    updated_count += 1
                    print(f"✓ 更新 {key}.{target_path}: {old_value} -> {new_value}")
                else:
                    print(f"✗ {key} 中未找到路径: {target_path}")

        print(f"\n总计更新: {updated_count} 个节点")
        return data

    @staticmethod
    def update(data: dict, path_expr: str, new_value: Any) -> dict:
        """
        主入口方法
        路径格式:
        - ad_unit_1.reload.reload_logic.retry_intervals  -> 精确路径
        - ad_unit_1..retry_intervals                     -> 模糊匹配，修改 ad_unit_1 下所有 retry_intervals
        - ad_unit_*.reload.reload_logic.retry_intervals  -> 通配符匹配多个 ad_unit
        """
        updated_count = 0

        # 解析路径表达式
        if ".." in path_expr:
            # 模糊匹配模式: ad_unit_1..retry_intervals
            root_key, _, target_key = path_expr.partition("..")

            if root_key not in data:
                print(f"✗ 根节点 '{root_key}' 不存在")
                return data

            # 查找该根节点下所有 target_key 的路径
            all_paths = JsonModifier._find_all_paths(data[root_key], target_key)

            for sub_path in all_paths:
                full_path = f"{root_key}.{sub_path}"
                if JsonModifier._set_value_by_path(data, full_path, new_value):
                    updated_count += 1
                    print(f"✓ 更新: {full_path}")

        elif "*" in path_expr:
            # 通配符模式: ad_unit_*.reload.reload_logic.retry_intervals
            # 简化处理：找到所有匹配的根节点，然后按精确路径处理
            pattern = path_expr.split(".")[0]  # ad_unit_*
            prefix = pattern.replace("*", "")
            remaining_path = ".".join(path_expr.split(".")[1:])  # reload.reload_logic.retry_intervals

            for key in list(data.keys()):
                if key.startswith(prefix):
                    full_path = f"{key}.{remaining_path}"
                    if JsonModifier._set_value_by_path(data, full_path, new_value):
                        updated_count += 1
                        print(f"✓ 更新: {full_path}")

        else:
            # 精确路径模式
            if JsonModifier._set_value_by_path(data, path_expr, new_value):
                updated_count += 1
                print(f"✓ 更新: {path_expr}")
            else:
                print(f"✗ 路径不存在: {path_expr}")

        print(f"\n总计更新: {updated_count} 处")
        return data

    @staticmethod
    def _find_all_paths(data: Any, target_key: str, current_path: str = "") -> List[str]:
        """
        递归查找所有包含目标 key 的路径
        返回如: ["reload.reload_logic.retry_intervals", "reload.reload_logic.x.retry_intervals"]
        """
        paths = []

        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{current_path}.{key}" if current_path else key
                if key == target_key:
                    paths.append(new_path)
                # 继续递归查找，即使找到了也不停止（因为可能有多个）
                paths.extend(JsonModifier._find_all_paths(value, target_key, new_path))

        elif isinstance(data, list):
            for i, item in enumerate(data):
                new_path = f"{current_path}[{i}]"
                paths.extend(JsonModifier._find_all_paths(item, target_key, new_path))

        return paths

    @staticmethod
    def _set_value_by_path(data: dict, path: str, value: Any) -> bool:
        """根据精确路径设置值"""
        keys = path.replace("[", ".[").split(".")
        current = data

        try:
            for key in keys[:-1]:
                if key.startswith("[") and key.endswith("]"):
                    # 数组索引
                    idx = int(key[1:-1])
                    current = current[idx]
                else:
                    current = current[key]

            # 设置最终值
            last_key = keys[-1]
            if last_key.startswith("[") and last_key.endswith("]"):
                idx = int(last_key[1:-1])
                current[idx] = value
            else:
                current[last_key] = value
            return True

        except (KeyError, IndexError, TypeError):
            return False
# ==================== 使用示例 ====================

import json
from typing import Any, Dict, List, Set, Tuple


def get_key_structure(obj: Any, path: str = "") -> Set[str]:
    """
    递归获取JSON对象的所有key路径结构
    返回形如：{'root.name', 'root.address.city', 'root.hobbies[]'}
    """
    keys = set()

    if isinstance(obj, dict):
        for key, value in obj.items():
            current_path = f"{path}.{key}" if path else key
            keys.add(current_path)
            # 递归处理嵌套结构
            if isinstance(value, (dict, list)) and value:
                keys.update(get_key_structure(value, current_path))

    elif isinstance(obj, list):
        # 对于列表，我们检查第一个非空元素的结构（假设列表内结构一致）
        for i, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                list_path = f"{path}[]"
                keys.update(get_key_structure(item, list_path))
                break  # 只取第一个元素的结构作为代表

    return keys


def compare_json_keys(json1: Any, json2: Any) -> Dict[str, any]:
    """
    比对两个JSON结构的key是否一致

    Returns:
        dict: 包含比对结果的字典
    """
    keys1 = get_key_structure(json1, "root")
    keys2 = get_key_structure(json2, "root")

    only_in_1 = keys1 - keys2
    only_in_2 = keys2 - keys1
    common = keys1 & keys2

    return {
        "is_identical": keys1 == keys2,
        "only_in_first": sorted(only_in_1),
        "only_in_second": sorted(only_in_2),
        "common_keys": sorted(common),
        "total_keys_first": len(keys1),
        "total_keys_second": len(keys2)
    }



if __name__ == "__main__":
    # 数据
    json_data = {"ad_unit_1":{"reload":{"reload_action":"new_load_reset","reload_count":10,"reload_logic":{"retry_intervals":[2000,3000,4000,5000,6000,6000,6000,6000,6000,6000]},"reload_type":4}},"ad_unit_3":{"reload":{"reload_action":"new_load_reset","reload_count":10,"reload_logic":{"rp_reload_type":1,"rp_reload_value":{"reload_count":8,"reload_logic":{"retry_intervals":[2000,4000,6000,8000,10000,12000,14000,16000]},"reload_type":4}},"reload_time":5000,"reload_type":2}}}
    # # 示例 1: 基础嵌套修改
    # print("=== 示例 1: 基础嵌套修改 ===")

    # # 修改嵌套字段
    # result = JsonModifier.set_value(json_str, "user.name", "李四")
    # print(f"修改姓名: {JsonModifier.to_json_str(result, pretty=True)}")
    #
    # # 修改深层嵌套字段
    # result = JsonModifier.set_value(result, "user.profile.email", "lisi@new.com")
    # print(f"修改邮箱: {result['user']['profile']['email']}")
    #
    # # 修改数组元素（索引从 0 开始）
    # result = JsonModifier.set_value(result, "tags.0", "VIP用户")
    # print(f"修改数组第1个元素: {result['tags']}")
    #
    # # 示例 2: 批量修改
    # print("\n=== 示例 2: 批量修改 ===")
    # batch_updates = {
    #     "user.age": 25,
    #     "user.profile.phone": "13800138000",
    #     "tags.1": "老客戶"
    # }
    # result = JsonModifier.set_values(json_str, batch_updates)
    # print(JsonModifier.to_json_str(result, pretty=True))
    #
    # # 示例 3: 处理纯数组 JSON
    # print("\n=== 示例 3: 处理数组 ===")
    # array_json = '[{"id": 1, "name": "商品1"}, {"id": 2, "name": "商品2"}]'
    # result = JsonModifier.set_value(array_json, "0.name", "新商品1")
    # print(f"修改数组第1个对象的name: {JsonModifier.to_json_str(result)}")
    #
    # # 示例 4: 自动创建不存在的路径
    # print("\n=== 示例 4: 自动创建路径 ===")
    # simple_json = '{"user": {}}'
    # result = JsonModifier.set_value(simple_json, "user.settings.theme", "dark")
    # print(JsonModifier.to_json_str(result, pretty=True))

    JsonModifier.set_nested_value()
