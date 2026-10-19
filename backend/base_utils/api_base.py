# -- coding: utf-8 --
import requests, json, time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any
from jsonpath import jsonpath
from base_utils.logger_base import setting_logger

proxies = {'http': None, 'https': None}
logger = setting_logger("api")


class ResultControl(str, Enum):
    """result_control 参数的可选值：决定接口返回什么内容。

    用法（推荐，IDE 可自动补全）：
        my_get(url, result_control=ResultControl.RESP)
    也兼容旧的字符串写法（ResultControl.RESP 与 "resp" 等价）：
        my_get(url, result_control="resp")
    """
    RESULT = "result"    # 解析后的响应体数据（默认）
    COOKIES = "cookies"  # 响应 cookies
    HEADERS = "headers"  # 响应头
    HISTORY = "history"  # 重定向历史
    URL = "url"          # 最终请求地址
    RESP = "resp"        # 原始 requests.Response 对象


class ReturnFormat(str, Enum):
    """return_format 参数的可选值：决定响应体如何解析。

    用法（推荐，IDE 可自动补全）：
        my_get(url, return_format=ReturnFormat.TEXT)
    也兼容旧的字符串写法（ReturnFormat.TEXT 与 "text" 等价）。
    """
    JSON = "json"        # 解析为 JSON（默认）
    TEXT = "text"        # 返回纯文本


class ResultParseError(Exception):
    """接口返回体解析失败（JSON 解析异常）。"""


@dataclass
class ApiResult:
    """统一的接口返回封装：状态 + 原因 + 数据。

    所有请求方法（my_get / my_post / my_put / my_delete）统一返回本对象，包含：
    - status: 是否成功（HTTP < 400 且返回体解析成功）
    - reason: 失败原因（成功时为空字符串）
    - data:   成功时的返回数据（受 result_control 控制）

    兼容旧调用习惯：
    - bool(result)           等价于 result.status
    - ok, data = result      成功时解包出 (True, 数据)，失败时解包出 (False, 原因)
    - result.status / result.reason / result.data 可显式访问
    """

    status: bool
    data: Any = None
    reason: str = ""

    def __bool__(self) -> bool:
        return self.status

    def __iter__(self):
        # 成功返回 data，失败返回 reason，兼容旧的 (status, 数据/原因) 二元组解包
        second = self.data if self.status else self.reason
        return iter((self.status, second))

    @classmethod
    def success(cls, data):
        """构造成功结果。"""
        return cls(status=True, data=data, reason="")

    @classmethod
    def failure(cls, reason, data=None):
        """构造失败结果。"""
        return cls(status=False, data=data, reason=reason)

def get_header(act="json"):
    if act == "json":
        json_header = {
            'content-type': "application/json",
        }
        return json_header
    else:
        str_header = {
            'content-type': "application/x-www-form-urlencoded",
        }
        return str_header


def my_get(url, result_control=ResultControl.RESULT, return_format=ReturnFormat.JSON, **kwargs):
    """GET请求。

    :param url:            请求地址
    :param result_control: 返回内容控制，可选值见 ResultControl（result/cookies/headers/history/url/resp）
    :param return_format:  返回体解析格式，可选值见 ReturnFormat（json/text）
    :return: ApiResult（status/reason/data）
    """
    logger.debug(f"接口请求地址>>>>>>>【{url}】")
    try:
        resp = requests.request("GET", url, timeout=120, proxies=proxies, **kwargs)
    except Exception as e:
        logger.error(f"GET请求异常，异常原因：{e}")
        return ApiResult.failure(reason=f"GET请求异常：{e}")
    return my_return(resp=resp, result_control=result_control, return_format=return_format)


def my_post(url, result_control=ResultControl.RESULT, return_format=ReturnFormat.JSON, headers=None, **kwargs):
    """POST请求。

    :param url:            请求地址
    :param result_control: 返回内容控制，可选值见 ResultControl（result/cookies/headers/history/url/resp）
    :param return_format:  返回体解析格式，可选值见 ReturnFormat（json/text）
    :param headers:        请求头，None 表示使用默认空头
    :return: ApiResult（status/reason/data）
    """
    logger.debug(f"接口请求地址>>>>>>>【{url}】")
    headers = headers or {}
    try:
        resp = requests.request("POST", url, timeout=120, headers=headers, proxies=proxies, **kwargs)
    except Exception as e:
        logger.error(f"POST请求异常，异常原因：{e}")
        return ApiResult.failure(reason=f"POST请求异常：{e}")
    return my_return(resp=resp, result_control=result_control, return_format=return_format)


def my_put(url, result_control=ResultControl.RESULT, return_format=ReturnFormat.JSON, **kwargs):
    """PUT请求。

    :param url:            请求地址
    :param result_control: 返回内容控制，可选值见 ResultControl（result/cookies/headers/history/url/resp）
    :param return_format:  返回体解析格式，可选值见 ReturnFormat（json/text）
    :return: ApiResult（status/reason/data）
    """
    logger.debug(f"接口请求地址>>>>>>>【{url}】")
    try:
        resp = requests.request("PUT", url, timeout=120, proxies=proxies, **kwargs)
    except Exception as e:
        logger.error(f"PUT请求异常，异常原因：{e}")
        return ApiResult.failure(reason=f"PUT请求异常：{e}")
    return my_return(resp=resp, result_control=result_control, return_format=return_format)


def my_delete(url, result_control=ResultControl.RESULT, return_format=ReturnFormat.JSON, **kwargs):
    """DELETE请求。

    :param url:            请求地址
    :param result_control: 返回内容控制，可选值见 ResultControl（result/cookies/headers/history/url/resp）
    :param return_format:  返回体解析格式，可选值见 ReturnFormat（json/text）
    :return: ApiResult（status/reason/data）
    """
    logger.debug(f"接口请求地址>>>>>>>【{url}】")
    try:
        resp = requests.request("DELETE", url, timeout=120, proxies=proxies, **kwargs)
    except Exception as e:
        logger.error(f"DELETE请求异常，异常原因：{e}")
        return ApiResult.failure(reason=f"DELETE请求异常：{e}")
    return my_return(resp=resp, result_control=result_control, return_format=return_format)


def retry_request(retry_count=3, retry_codes=None, retry_text=None, retry_xpath=None,retry_time=10):
    """
    装饰器：对请求接口进行重试
    :param retry_count: 重试次数
    :param retry_codes: 需要重试的返回code列表
    :param retry_xpath: 定位返回xpath
    :param retry_text: 需要重试的返回内容
    :param retry_time: 重试时间间隔
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            count = 0
            while count < retry_count:
                try:
                    response = func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"重试发生异常，异常：{e}")
                    count += 1
                    continue
                if retry_codes and response.status_code in retry_codes:
                    count += 1
                    time.sleep(retry_time)
                    continue
                elif retry_text and jsonpath(response,retry_xpath)!=False and jsonpath(response,retry_xpath)[0] == retry_text:
                    count += 1
                    time.sleep(retry_time)
                    continue
                return response
            return None

        return wrapper

    return decorator


def my_return(resp, result_control=ResultControl.RESULT, return_format=ReturnFormat.JSON):
    """
    请求结果统一封装，返回 ApiResult（状态 + 原因 + 数据）。

    :param resp:            requests.Response 对象
    :param result_control:  返回内容控制，可选值见 ResultControl（result/cookies/headers/history/url/resp）
    :param return_format:   返回体解析格式，可选值见 ReturnFormat（json/text）
    :return: ApiResult，status 表示是否成功，失败时 reason 携带原因
    :raises ValueError:     result_control 不在支持列表时抛出
    """
    # 兼容旧代码直接传字符串（如 "resp"），统一归一化为字符串
    result_control = getattr(result_control, "value", result_control)
    return_format = getattr(return_format, "value", return_format)

    # HTTP 状态码 >= 400 视为请求失败
    if resp.status_code >= 400:
        reason = f"请求错误，状态码为:【{resp.status_code}】, 内容为:【{resp.text}】"
        logger.warning(reason)
        return ApiResult.failure(reason=reason)

    result_options = {
        "result": lambda r: process_result(r, return_format),
        "cookies": lambda r: r.cookies,
        "headers": lambda r: r.headers,
        "history": lambda r: r.history,
        "url": lambda r: r.url,
        "resp": lambda r: r,
    }

    if result_control not in result_options:
        raise ValueError(f"没有该配置【{result_control}】，请检查 result_control 取值")

    try:
        return_value = result_options[result_control](resp)
    except ResultParseError as e:
        # result_control="result" 时 JSON 解析失败，由 process_result 抛出
        logger.warning(str(e))
        return ApiResult.failure(reason=str(e))
    except Exception as e:
        reason = f"结果处理异常，异常原因：{e}"
        logger.error(reason)
        return ApiResult.failure(reason=reason)

    return ApiResult.success(return_value)


def process_result(resp, return_format=ReturnFormat.JSON):
    """
    按返回格式解析响应体，并返回解析结果。

    相对旧版改动：JSON 解析失败不再返回裸 False（会与「成功但值为 False」混淆），
    而是抛出 ResultParseError，由 my_return 统一捕获并封装为失败的 ApiResult。

    :param resp:         requests.Response 对象
    :param return_format: 返回体解析格式，可选值见 ReturnFormat（json/text）
    :return: 解析后的 dict / 文本
    :raises ResultParseError: JSON 解析失败
    :raises ValueError:       return_format 不在支持列表时抛出
    """
    return_format = getattr(return_format, "value", return_format)

    if return_format == "json":
        try:
            return resp.json()
        except json.JSONDecodeError:
            raise ResultParseError("接口返回体不是合法 JSON，请排查解析方式或改用 return_format='text'")
        except Exception as e:
            raise ResultParseError(f"接口返回体解析异常，异常原因：{e}")
    elif return_format == "text":
        return resp.text
    else:
        raise ValueError("Unsupported return_format. Please choose 'json' or 'text'.")
