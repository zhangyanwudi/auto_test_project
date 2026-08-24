import json,base64,hashlib

def base64_en(encoded_content,is_file=False):
    """base64加密"""
    if is_file:
        content=encoded_content
    else:
        if isinstance(encoded_content, (dict, list)):
            # JSON 对象/列表 -> JSON 字符串
            content = json.dumps(encoded_content, ensure_ascii=False).encode('utf-8')
        elif isinstance(encoded_content, str):
            # 字符串直接编码
            content = encoded_content.encode('utf-8')
        elif isinstance(encoded_content, bytes):
            # 字节直接编码
            content = encoded_content
        else:
            raise TypeError(f"不支持的数据类型: {type(encoded_content)}")
    encoded_bytes = base64.b64encode(content)
    encoded_str = encoded_bytes.decode('utf-8')
    return encoded_str


def base64_de(encoded_str):
    """base64解密"""
    encoded_bytes = encoded_str.encode('utf-8')
    decoded_bytes = base64.b64decode(encoded_bytes)
    decoded_str = decoded_bytes.decode('utf-8')
    dict_obj = json.loads(decoded_str)
    return dict_obj

def md5_en(value,en_type="upper"):
    """
    生成md5
    :param value:       加密内容
    :en_type:       加密格式     upper-大写    lower-小写
    :return:
    """
    val = hashlib.md5()
    val.update(str(value).encode("utf-8"))
    if en_type=="lower":
        return val.hexdigest().lower()
    return val.hexdigest().upper()

def encode_to_url(content):
    """编码函数（加密）"""
    from urllib import parse
    # 使用 urllib.parse.quote 进行 URL 编码（基于 UTF-8）
    return parse.quote(content, encoding='utf-8')

# URL
def decode_from_url(encoded_content):
    """解码函数（解密）"""
    from urllib import parse
    # 使用 urllib.parse.unquote 进行 URL 解码
    return parse.unquote(encoded_content, encoding='utf-8')






if __name__=="__main__":
    from base_utils.common import read_file_by_rb

    read_file_by_rb("QQ20260408-160317.png")
    print(base64_en(read_file_by_rb("QQ20260408-160317.png"),is_file=True))