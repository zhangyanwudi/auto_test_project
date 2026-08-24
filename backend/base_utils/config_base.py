"""
统一敏感配置读取入口。

所有敏感信息（腾讯云、钉钉、数据库、SSO 等）统一维护在
backend/config/page_config.json（该文件不入 git），按业务分组存放。
各业务代码通过 load_page_config() / get_config() 读取，不再硬编码密钥。

page_config.json 中既有非敏感配置（page_tile_name、sso_enabled，供公开接口
按需返回），也有敏感配置（tencent_cloud、dingtalk、database、youxi123_sso 等），
因此公开接口只能返回白名单字段，切勿整包返回。
"""
import json
from pathlib import Path

# 与 settings.py 同目录：backend/config/page_config.json
PAGE_CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config' / 'page_config.json'


def load_page_config():
    """读取 page_config.json 全部内容；文件不存在或格式错误时返回空 dict。"""
    try:
        with open(PAGE_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def get_config(section, key=None, default=None):
    """
    按业务分组读取配置。

    :param section: 业务分组名，如 'tencent_cloud' / 'dingtalk' / 'database' / 'youxi123_sso'
    :param key:     分组内的键；为 None 时返回整个分组 dict
    :param default: 未命中时的默认值
    """
    cfg = load_page_config()
    sec = cfg.get(section) if isinstance(cfg.get(section), dict) else {}
    if key is None:
        return sec if sec else (default if default is not None else {})
    return sec.get(key, default)
