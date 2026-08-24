import json
from base_utils.time_base import get_date


def analysis_json(indict, pre=None, is_sort=False, dict_key=None, dict_value=None):
    """
    解析json字符串
    :param indict: 字典列表
    :param pre: 拼接值
    :return: 返回解析值
    结果输出
     for i in generator(value):
        json_value[".".join(i[0:-1])]=i[-1]
    print(json.dumps(json_value))
    """
    pre = pre[:] if pre else []
    stack = [(pre, indict)]
    while stack:
        pre, node = stack.pop()
        if isinstance(node, dict):
            if not node:
                yield pre + ['{}']
            for key, value in node.items():
                if isinstance(value, (dict, list, tuple)):
                    stack.append((pre + [key], value))
                else:
                    yield pre + [key, value]
        elif isinstance(node, list):
            if not node:
                yield pre + ['[]']
            else:
                # 对列表进行排序
                if is_sort:
                    node = list_sorted(node, dict_key=dict_key, dict_value=dict_value)
                for i, v in enumerate(node):
                    if isinstance(v, (dict, list, tuple)):
                        stack.append((pre + [str(i)], v))
                    else:
                        yield pre + [str(i), v]
        elif isinstance(node, tuple):
            if not node:
                yield pre + ['()']
            else:
                for v in node:
                    if isinstance(v, (dict, list, tuple)):
                        stack.append((pre, v))
                    else:
                        yield pre + [str(v)]
        else:
            yield pre + [node]


def analysis_json_by_list(indict, pre=None, is_sort=False, dict_key=None, dict_value=None):
    """
    解析json字符串
    :param indict: 字典列表
    :param pre: 拼接值
    :return: 返回解析值
    结果输出
     for i in generator(value):
        json_value[".".join(i[0:-1])]=i[-1]
    print(json.dumps(json_value))
    """
    pre = pre[:] if pre else []
    stack = [(pre, indict)]
    while stack:
        pre, node = stack.pop()
        if isinstance(node, dict):
            if not node:
                yield pre + ['{}']
            for key, value in node.items():
                if isinstance(value, (dict, list, tuple)):
                    stack.append((pre + [key], value))
                else:
                    yield pre + [key, value]
        elif isinstance(node, list):
            if not node:
                yield pre + ['[]']
            else:
                # 对列表进行排序
                if is_sort:
                    node = list_sorted(node, dict_key=dict_key, dict_value=dict_value)
                for i, v in enumerate(node):
                    if isinstance(v, (dict, list, tuple)):
                        stack.append((pre + ['[' + str(i) + ']'], v))
                    else:
                        yield pre + ['[' + str(i) + ']', v]
        elif isinstance(node, tuple):
            if not node:
                yield pre + ['()']
            else:
                for v in node:
                    if isinstance(v, (dict, list, tuple)):
                        stack.append((pre, v))
                    else:
                        yield pre + [str(v)]
        else:
            yield pre + [node]


def analysis_json_by_later(indict, pre=None, is_sort=False, dict_key=None, dict_value=None):
    """
    解析 JSON 结构，将嵌套结构扁平化为点分键路径

    :param indict: 输入的字典或列表
    :param pre: 前缀路径（内部递归使用）
    :param is_sort: 是否对列表进行排序
    :param dict_key: 排序时使用的字典键
    :param dict_value: 排序时使用的字典值
    :return: 生成器，产出 [path_parts..., value] 格式的列表
    """
    pre = pre[:] if pre else []
    stack = [(pre, indict)]

    while stack:
        current_path, node = stack.pop()

        if isinstance(node, dict):
            if not node:
                yield current_path + ['{}']
                continue

            for key, value in node.items():
                new_path = current_path + [key]
                # 优化：最后一级是基础类型列表时，不再展开
                if isinstance(value, list) and value and not isinstance(value[0], (dict, list)):
                    yield new_path + [value]
                elif isinstance(value, (dict, list)):
                    stack.append((new_path, value))
                else:
                    yield new_path + [value]

        elif isinstance(node, list):
            if not node:
                yield current_path + ['[]']
                continue

            # 对列表进行排序
            if is_sort:
                node = list_sorted(node, dict_key=dict_key, dict_value=dict_value)

            for idx, item in enumerate(node):
                idx_path = current_path + [f'[{idx}]']
                # 优化：最后一级是基础类型列表时，不再展开
                if isinstance(item, list) and item and not isinstance(item[0], (dict, list)):
                    yield idx_path + [item]
                elif isinstance(item, (dict, list)):
                    stack.append((idx_path, item))
                else:
                    yield idx_path + [item]

        else:
            yield current_path + [node]


def montage_json(json_content, format_json_type="default", format_symbol=".", is_sort=False, dict_key=None, dict_value=None):
    """
    拼接json
    :param json_content:        json内容
    :param format_symbol:          拼接格式
    :param is_sord:          排序     True-排序

    :return:
    """
    # 定义变量
    montage_dict = {}
    # 提取公共参数，避免重复
    common_params = {
        "indict": json_content,
        "dict_key": dict_key,
        "dict_value": dict_value,
        "is_sort": is_sort  # 修正拼写
    }
    # 定义方法
    parsers = {
        "list": analysis_json_by_list,
        "later": analysis_json_by_later,
        "default": analysis_json  # 使用 "default" 替代 else 更清晰
    }
    # 获取方法
    parser_func = parsers.get(format_json_type)
    for i in parser_func(**common_params):
        montage_dict[format_symbol.join(i[:-1])] = i[-1]
    if is_sort:
        return dict_sorted(montage_dict)
    return montage_dict


def diff_dict(dict1, dict2):
    """
    比对字典是否相同
    :param dict1:
    :param dict2:
    :return:
    """
    if dict1 == dict2:
        return True
    return False


def diff_json(json1, json2, dict_value=None):
    """
    比对json是否相同
    :param json1:
    :param json2:
    :return:
    """
    return diff_dict(montage_json(json1, is_sord=True, dict_value=dict_value),
                     montage_json(json2, is_sord=True, dict_value=dict_value))


def list_sorted(lst, dict_key=None, dict_value=None):
    """对列表内容排序"""
    if all(isinstance(item, dict) for item in lst):
        # 对列表中的字典进行排序，重装到列表中
        tmp_lst = []
        for item in lst:
            sorted_item = dict(sorted(item.items()))
            tmp_lst.append(sorted_item)
        lst = tmp_lst
        return lst
    elif all(isinstance(item, (int, str, float)) for item in lst):
        # 对列表为字符、数字排序
        return sorted(lst, key=lambda x: x)
    else:
        print("列表中元素类型不相同，不进行排序")
        print(lst)
        return lst


def write_to_file(file_path, content, mode='a', is_end_line=False):
    """
    将内容写入文件
    :param file_path: 文件路径
    :param content: 要写入的内容
    :param mode: 打开文件的模式，默认是追加模式 ('a')
    """
    with open(file_path, mode, encoding='utf-8') as file:
        file.write(content)  # 每次写入后换行
        if is_end_line:
            file.write("\n")  # 每次写入后换行


def read_json(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.loads(file.read())
    except Exception as e:
        raise ValueError("读取json配置异常")


def read_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            # 读取文件并按行分割，过滤掉空行和每行首尾空格
            return file.read()
    except Exception as e:
        raise ValueError("读取文件异常")

def read_file_by_rb(file_path):
    try:
        with open(file_path, 'rb') as file:
            # 读取文件并按行分割，过滤掉空行和每行首尾空格
            return file.read()
    except Exception as e:
        raise ValueError("读取文件异常")


def send_email():
    """发送邮件"""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication
    smtp_server = 'smtp.qiye.aliyun.com'  # 替换为你的邮件服务器
    smtp_port = 465  # 一般使用587端口
    from_email = 'zhangyan02195@hungrystudio.com'
    password = 'ZHANGyan521'
    # 创建邮件对象
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = "346999037@qq.com"
    msg['Subject'] = f"【{get_date('YmdHMS')}】applovin广告数据抓取"
    # 添加邮件正文
    msg.attach(MIMEText(f"系统自动发送。。。", 'plain', "utf-8"))
    # 附加文件
    with open("/Users/admin/Desktop/ZnYan/auto_test_utils/update_file/applovin数据抓取.xlsx", 'rb') as file:
        part = MIMEApplication(file.read(), Name="applovin数据抓取.xlsx")
        part['Content-Disposition'] = f'attachment; filename="applovin数据抓取.xlsx"'
        msg.attach(part)
    # 发送邮件
    with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
        server.login(from_email, password)  # 登录邮箱
        server.send_message(msg)  # 发送邮件


def dict_sorted(data_dict, sort_status=False):
    """对字典排序"""
    return dict(sorted(data_dict.items(), reverse=sort_status))


if __name__ == '__main__':
    pass
