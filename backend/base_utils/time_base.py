import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def get_timestamp_ms():
    """获取当前时间戳-毫秒"""
    return int(time.time() * 1000)


def get_timestamp_ss():
    """获取当前时间戳-秒"""
    return int(time.time())


def get_datetime():
    """获取当前日期"""
    return datetime.now()


def _date_template(template="YmdHMS"):
    """
    获取日期模板
    :param template: 模板格式
    :return:
    """
    template_dict = {
        "YmdHMSF3": "%Y-%m-%d %H:%M:%S:%f",
        "YmdHMS": "%Y-%m-%d %H:%M:%S",
        "Ymd": "%Y-%m-%d",
        "HMS": "%H:%M:%S",
        "Ymd0": "%Y%m%d",
        "YmdHMS0": "%Y%m%d%H%M%S",
        "Y": "%Y",
        "m": "%m",
        "d": "%d",
        "H": "%H",
        "M": "%M",
        "S": "%S",
        "年月日时分秒毫": "%Y年%m月%d日%H时%M分%S秒%f毫",
        "日时分秒毫": "%d日%H时%M分%S秒%f毫",
        "年月日时分秒": "%Y年%m月%d日 %H时%M分%S秒",
        "年月日": "%Y年%m月%d日",
        "年月": "%Y年%m月",
        "年": "%Y年",
        "月": "%m月",
        "日": "%d日",
        "时": "%H时",
        "分": "%M分",
        "秒": "%S秒"
    }
    if template in template_dict.keys():
        return template_dict[template]
    return template_dict["YmdHMS"]


def get_date(template="YmdHMS"):
    """
    获取时间
    :return:
    """
    return get_datetime().strftime(_date_template(template))


def get_before_date(days, template="YmdHMS"):
    """
    获取之前几日日期
    :param days:   几天  支持往前 如：4   支持往后 如 -4
    :param template: 日期格式
    :return:
    """
    date_format = _date_template(template)
    return (get_datetime() - timedelta(days=days)).strftime(date_format)


def to_utc(str_time):
    """
    将北京时间转成UTC时间
    :param str_time: 时间-字符型
    :return:
    """
    _time = datetime.strptime(str_time, _date_template())
    utc_time = _time.astimezone(timezone.utc)
    utc_time_str = utc_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    return utc_time_str


def to_beijing(str_time):
    """
    将UTC时间转成北京时间
    :param str_time: 时间-字符型
    :return:
    """
    utc_time = datetime.strptime(str_time, "%Y-%m-%dT%H:%M:%SZ")
    beijing_time = utc_time + timedelta(hours=8)
    beijing_time_str = beijing_time.strftime(_date_template())
    return beijing_time_str


def get_timezone(timezone_name):
    """
    计算时区偏移量（相对 UTC 的秒数）。
    使用标准库 zoneinfo，无需安装 pytz。
    """
    tz = ZoneInfo(timezone_name)
    now_utc = datetime.now(timezone.utc)
    off = tz.utcoffset(now_utc)
    if off is None:
        return 0
    return int(off.total_seconds())


def timezone_name(timezone_name):
    """
    返回指定名称的 tzinfo（ZoneInfo），供需要时区对象的调用方使用。
    """
    return ZoneInfo(timezone_name)


def timestamp_to_date(timestamp, template="YmdHMS"):
    """时间戳转成字符时间"""
    if len(str(int(timestamp))) > 10:
        timestamp = timestamp / 1000
    date = datetime.fromtimestamp(timestamp)
    if template == "YmdHMSF3":
        return date.strftime(_date_template(template))[:-3]
    return date.strftime(_date_template(template))


def time_str_to_date(specified_time_str, template="YmdHMS"):
    """将日期字符型转成时间型"""
    specified_time = datetime.strptime(specified_time_str, _date_template(template))
    return specified_time


def date_to_time_str(date_time, template="YmdHMS"):
    """将时间型转成字符型"""
    formatted_time = date_time.strftime(_date_template(template))
    return formatted_time


def get_before(days=0, hours=0, minutes=0,seconds=0, is_tmiestamp=False, template="YmdHMS"):
    """
    计算日期
    :param is_tmiestamp: 是否返回时间戳 True-返回时间戳  False-日期
    :param is_tmiestamp: 返回日期格式
    :return:
    """
    new_time = get_datetime()
    # 计算新的时间
    new_time += timedelta(days=days, hours=hours, minutes=minutes,seconds=seconds)
    if is_tmiestamp:
        return int(new_time.timestamp()*1000)
    return new_time.strftime(_date_template(template))


def format_iso8601(dt=None, tz_hours=8):
    """生成 ISO 8601 格式时间字符串，如 2026-01-27T11:51:10.000+0800"""
    if dt is None:
        # 创建指定时区的时间（默认东八区）
        tz = timezone(timedelta(hours=tz_hours))
        dt = datetime.now(tz)
    elif dt.tzinfo is None:
        # 如果 dt 无时区，添加指定时区
        tz = timezone(timedelta(hours=tz_hours))
        dt = dt.replace(tzinfo=tz)

    # 格式：年月日T时分秒.毫秒+时区
    # %f 是微秒(6位)，取前3位作为毫秒
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + dt.strftime("%f")[:3] + dt.strftime("%z")


if __name__ == '__main__':
    # print(get_before(days=-33,is_tmiestamp=True))
    # print(get_before(days=-15,is_tmiestamp=True))
    print(get_before(days=33))
    # print(timestamp_to_date(1763283119162))
    # print(get_date(template="Ymd")-get_before(days=-2,template="Ymd"))
