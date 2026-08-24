# -- coding: utf-8 --
import requests, json, time
from functools import wraps
from jsonpath import jsonpath
from base_utils.logger_base import setting_logger

proxies = {'http': None, 'https': None}
logger=setting_logger("api")

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


def my_get(url, result_control="result", return_format="json", **kwargs):
    """GET请求"""
    logger.debug(f"接口请求地址>>>>>>>【{url}】")
    resp = requests.request("GET", url, timeout=120, proxies=proxies, **kwargs)
    return my_return(resp=resp, result_control=result_control, return_format=return_format)


def my_post(url, result_control="result", return_format="json",headers={}, **kwargs):
    """POST请求"""
    logger.debug(f"接口请求地址>>>>>>>【{url}】")
    resp = requests.request("POST", url, timeout=120,headers=headers, proxies=proxies, **kwargs)
    return my_return(resp=resp, result_control=result_control, return_format=return_format)


def my_put(url, result_control="result", return_format="json", **kwargs):
    """PUT请求"""
    logger.debug(f"接口请求地址>>>>>>>【{url}】")
    resp = requests.request("PUT", url, timeout=120, proxies=proxies, **kwargs)
    return my_return(resp=resp, result_control=result_control, return_format=return_format)

def my_delete(url, result_control="result", return_format="json", **kwargs):
    """DELETE请求"""
    logger.debug(f"接口请求地址>>>>>>>【{url}】")
    resp = requests.request("DELETE", url, timeout=120, proxies=proxies, **kwargs)
    return resp


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


def my_return(resp, result_control, return_format="json"):
    """
    请求结果
    :param resp:                    接口返回内容
    :param result_control:          接口返回要求
    :param return_format:           接口返回数据类型
    :return:
    :raises ValueError: If result_control is not recognized.
    """
    # Check if response status code indicates a client or server error.
    if resp.status_code >= 400:
        error_message = f"请求错误，状态码为:【{resp.status_code}】, 内容为:【{resp.text}】"
        logger.debug(error_message)
        return False

    # Dictionary to map result_control options to their respective response attributes.
    result_options = {
        "result": lambda r: process_result(r, return_format),
        "cookies": lambda r: r.cookies,
        "headers": lambda r: r.headers,
        "history": lambda r: r.history,
        "url": lambda r: r.url,
        "resp": lambda r: r
    }

    if result_control in result_options:
        return_value = result_options[result_control](resp)
        # log_message = f"【接口返回】{return_value}"
        # logger.debug(log_message)
        return return_value
    else:
        raise ValueError("没有该配置，请检查")


#
def process_result(resp, return_format="json"):
    """
    Process the 'result' from the response based on the requested format.
    :param resp: The response object from requests module.
    :param return_format: 'json' or 'text' for the output format.
    :return: Parsed response text or JSON.
    """
    if return_format == "json":
        try:
            result_json = resp.json()
            return result_json
        except json.JSONDecodeError:
            error_message = "接口解析异常，请进行排查选择对应的解析方式"
            logger.debug(error_message)
            return False
        except Exception as e:
            error_message = f"接口解析异常，请进行排查选择对应的解析方式，异常原因：{e}"
            logger.debug(error_message)
            return False
    elif return_format == "text":
        return resp.text
    else:
        raise ValueError("Unsupported return_format. Please choose 'json' or 'text'.")
