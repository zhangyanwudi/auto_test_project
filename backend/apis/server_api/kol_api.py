# -*- coding: utf-8 -*-
import json
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Optional, Tuple
from base_utils.time_base import get_before_date
from base_utils.api_base import my_get, my_post
from base_utils.logger_base import logger
from enum import Enum, IntEnum


@dataclass
class TokenInfo:
    """get_user_token 接口的成功返回结构。"""
    token: str = ""  # 新签发的 token
    claims: dict = field(default_factory=dict)  # token 解析出的 JWT 载荷
    user: dict = field(default_factory=dict)  # 用户信息（id/username/full_name 等）


class KolEnum:
    """基建枚举"""

    class Channel(str, Enum):
        """渠道"""
        Social_youtube = "Social_youtube"
        Social_tiktok = "Social_tiktok"

    class PersonID(str, Enum):
        """达人ID"""
        ZnYan_kol = "M915BFH9KV"
        ZnYan = "1215BBPJ21"

    class Domain(str, Enum):
        """set_auth 注入登录态的目标站点域名。"""
        KOL_TEST = "https://marketing-test.youxi123.com"
        KOL_DEV1 = "https://marketing-dev1.youxi123.com"
        MI_TEST = "https://mi-test.youxi123.com"

    class KeyWordType(str, Enum):
        """
        活动管理    single--单关键词   compound--多关键词
        """
        SINGLE = 'single'
        COMPOUND = 'compound'

    class VideoTab(str, Enum):
        """视频审核tab"""
        PENDING = 'pending'
        CONFIRMIGN = 'confirming'
        COMPLETED = 'completed'

    class SettleTab(str, Enum):
        """结算明细审核tab"""
        PENDING = 'TODO'
        COMPLETED = 'DONE'

    class TaskSource(str, Enum):
        """建联-圈选方式"""
        Selected = "selected"  # 达人圈选
        Direct = "direct"  # 邮箱直联


class KolsysApi(KolEnum):
    # 用户邮箱
    def __init__(self,
                 is_debug: bool = False
                 ):
        self.is_debug = is_debug
        # 默认测试环境
        self.default_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjbGllbnRfaXAiOiIzOS45Ni4yMjIuMjUiLCJjcmVhdGVkX2F0IjoxNzg3MTMxOTg1LCJlbWFpbCI6InpoYW5neWFuMDIxOTVAaHVuZ3J5c3R1ZGlvLmNvbSIsImZ1bGxfbmFtZSI6IuW8oOWyqSIsInVzZXJfaWQiOiI2YTg1NzI0NzNlNmJjMjAxNTdjOTJhZmIiLCJ1c2VybmFtZSI6InpoYW5neWFuMDIxOTUiLCJ3b3JrY29kZSI6IjAwMTIxNyJ9.R7byMV8nOdJTt8gaWbsx5zf_eMXU1Q_f_TVNarrCqG0"
        self.mi_url = "https://iam-test.youxi123.com"
        self.kol_url = "https://marketing-test.youxi123.com"
        self.kolline_url = "https://kollink-test.afafb.com"
        if not self.is_debug:
            self.default_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjbGllbnRfaXAiOiIzOS4xNTUuMTcyLjM0IiwiY3JlYXRlZF9hdCI6MTc4OTkwNjA2NiwiZW1haWwiOiJ6aGFuZ3lhbjAyMTk1QGh1bmdyeXN0dWRpby5jb20iLCJmdWxsX25hbWUiOiLlvKDlsqkiLCJpc3MiOiJpYW0tbWkueW91eGkxMjMuY29tIiwidXNlcl9pZCI6IjZhODU3NGVhNWI1NTI4NjdkNGU1OGRhZCIsInVzZXJuYW1lIjoiemhhbmd5YW4wMjE5NSIsIndvcmtjb2RlIjoiMDAxMjE3In0.JUxuozq_6x2n4ZqytczLIhZmctGzmqEnfIBrzwNcFRY"
            self.mi_url = "https://iam-mi.youxi123.com"
            self.kol_url = "https://marketing.youxi123.com"
            self.kolline_url = "https://kol-link.youxi123.com"
        self.headers = {"Authorization": f"Bearer {self.default_token}"}

    def _update_headers(self):
        """更新headers"""
        self.headers = {"Authorization": f"Bearer {self.default_token}"}

    def get_user_token(self,
                       user_email: str,
                       is_set_cache: bool = False,
                       domains=None,
                       ):
        """
        获取用户token
        :param user_email:      用户邮箱
        :param is_set_cache:    是否设置浏览器缓存   True-设置，False-不设置
        :param domains:         要设置缓存的域名列表（每个须在 KolEnum.Domain 内），
                                支持单个字符串或多个字符串列表；为空/None 时设置 Domain 枚举中的全部域名
        :return:
        """
        url = self.mi_url + "/api/iam/users/token"
        params = {"email": user_email}
        logger.info(f"获取用户 token，email=【{user_email}】")
        status, resp = my_get(url, headers=self.headers, params=params)
        print(resp)
        if not status:
            return status, resp
        #
        code_status = resp.get("status").get("code")
        if code_status != 0:
            return False, f"接口code错误，code_status:{code_status}"
        data = resp.get("data")
        # 更新token
        self.default_token = data.get("token")
        self._update_headers()
        # 输出用户信息
        info = TokenInfo(
            token=self.default_token,
            claims=data.get("claims") or {},
            user=data.get("user") or {},
        )
        print(f"token:{info.token}")
        print(f"claims:{info.claims}")
        print(f"user:{info.user}")
        if is_set_cache:
            self._set_user_cache(user_email, data, domains=domains)
        return True, info

    def _build_mi_web_user_info(self, user: dict) -> dict:
        """组装 mi_web_user_Info（含固定特权位），并用接口返回的用户信息覆盖 id/username 等字段。"""
        return {
            "id": user.get("id"),
            "username": user.get("username"),
            "email": user.get("email"),
            "workcode": user.get("workcode"),
            "full_name": user.get("full_name"),
            "avatar": "",
            "sso_id": "1322625860778633",
            "privileges": {
                "ADS_CREATE:ALL": True,
                "ASA_REPORT:EXPORT_REPORT": True,
                "ASSET_BENCHMARK:EXPORT_REPORT": True,
                "ASSET_REPORT:EXPORT_REPORT": True,
                "BOARD_BENCHMARK:UPDATE_BOARD_BENCHMARK": True,
                "BOARD_TEMPLATE:CREATE_PUBLIC_TEMPLATE": True,
                "KOL_VIDEO_EFFECT:EXPORT_REPORT": True,
                "ROI_REPORT:EXPORT_REPORT": True,
            },
        }

    def _set_user_cache(self, user_email: str, data: dict, domains=None):
        """把 token 接口返回的登录态注入浏览器 localStorage（is_set_cache=True 时调用）。

        :param user_email: 用户邮箱（仅用于日志）
        :param data:       token 接口返回的 data 字段
        :param domains:    要设置的域名列表；为空时设置 Domain 枚举中的全部域名
        """
        from base_utils.push_auth import set_auth
        user = data.get("user") or {}
        # 归一化传入的域名列表：支持单个字符串或多个字符串列表；过滤空值并去重
        if domains is None:
            targets = [d.value for d in self.Domain]
        elif isinstance(domains, str):
            targets = [domains]
        else:
            targets = list(domains)

        valid_domain_values = {d.value for d in self.Domain}
        targets = [t for t in targets if t and t in valid_domain_values]
        # 去掉重复域名，同时保持顺序
        seen = set()
        uniq_targets = []
        for t in targets:
            if t not in seen:
                seen.add(t)
                uniq_targets.append(t)
        targets = uniq_targets
        # 未指定任何有效域名时，回退为全部枚举域名
        if not targets:
            targets = [d.value for d in self.Domain]

        try:
            for target in targets:
                # Domain 枚举存的是完整 URL（https://...），push_auth 内部按 host 匹配标签页，
                # 这里统一转为纯 host（如 marketing-test.youxi123.com）传入
                host = urlparse(target).netloc or target
                mi_web_user_info = self._build_mi_web_user_info(user)
                set_auth(
                    domain=host,
                    cache_type="localStorage",
                    values={
                        "kolUserName": user.get("username"),
                        "kolTicket": user.get("id"),
                        "kol_token": self.default_token,
                        "kolEmail": user.get("email"),
                        "kolFullName": user.get("full_name"),
                        "mi_web_user_Info": mi_web_user_info,
                        # 前端对 mi_web_user_token 用 JSON.stringify 存 / JSON.parse 读，
                        # 因此这里也必须存成「带引号的 JSON 字符串」，否则前端 parse 失败导致未登录
                        "mi_web_user_token": json.dumps(self.default_token),
                    },
                )
            logger.info(f"【{user_email}】缓存设置成功！域名：{targets}")
        except Exception as e:
            logger.error(f"设置缓存异常，{e}")

    # ── 以下为「纯函数扩展」：不影响原有方法，供 Playwright 巡检执行器注入登录态使用 ──

    def _build_auth_payload(self, data: dict) -> dict:
        """把 token 接口返回的 data 组装成要注入的 localStorage 内容（纯函数，不碰浏览器）。

        返回的 7 个 key 与前端登录态存储严格一致，其中 mi_web_user_token 必须存成
        「带引号的 JSON 字符串」（前端用 JSON.parse 读），否则会解析失败导致未登录。
        """
        user = data.get("user") or {}
        mi_web_user_info = {
            "id": user.get("id"),
            "username": user.get("username"),
            "email": user.get("email"),
            "workcode": user.get("workcode"),
            "full_name": user.get("full_name"),
            "avatar": "",
            "sso_id": "1322625860778633",
            "privileges": {
                "ADS_CREATE:ALL": True,
                "ASA_REPORT:EXPORT_REPORT": True,
                "ASSET_BENCHMARK:EXPORT_REPORT": True,
                "ASSET_REPORT:EXPORT_REPORT": True,
                "BOARD_BENCHMARK:UPDATE_BOARD_BENCHMARK": True,
                "BOARD_TEMPLATE:CREATE_PUBLIC_TEMPLATE": True,
                "KOL_VIDEO_EFFECT:EXPORT_REPORT": True,
                "ROI_REPORT:EXPORT_REPORT": True,
            },
        }
        return {
            "kolUserName": user.get("username"),
            "kolTicket": user.get("id"),
            "kol_token": self.default_token,
            "kolEmail": user.get("email"),
            "kolFullName": user.get("full_name"),
            "mi_web_user_Info": mi_web_user_info,
            "mi_web_user_token": json.dumps(self.default_token),
        }

    def create_order(self, res_id: str, media_source_list: list[str], price: int = 100):
        """
        创建订单
        :param res_id:              达人ID
        :param media_source_list:       渠道   Social_tiktok   Social_youtube
        :param price:       价格
        :return:
        """

        def _build_price_infos(media_source_list, price):
            """
            按 media_source_list 替换 price_infos 中的 media_source 值

            :param media_source_list: 媒体来源列表，如 ['Social_youtube', 'Social_youtube']
            :return: price_infos JSON 字符串
            """
            price_infos = [
                {
                    "media_source": media_source_list,
                    "price": 100,
                    "remark": ""
                }
            ]
            return json.dumps(price_infos, ensure_ascii=False)

        url = self.kol_url + "/kol/resource/order/create"
        payload = {
            "res_id": res_id,
            "price_infos": _build_price_infos(media_source_list, price),
            "activity_code": "CPN20261010092"
        }
        status, resp = my_post(url, headers=self.headers, data=json.dumps(payload))
        if not status:
            return status, resp
        print(resp)
        # 成功返回数据示例      {'code': 0, 'data': {'order_id': '1215BBPJ21-26100036'}, 'message': 'ok'}
        order_id = resp.get("data").get("order_id")
        return order_id

    def create_order_to_approval(self):
        """创建订单信息并提审"""
        url = self.kol_url + "/kol/api/orders/approval/create"
        """
        {"order_id":"1215BBPJ21-26100046","checks":[{"extra":"1","extra_ref":"1791884203431","kol_type":"","media_source":"Social_tiktok","video_type":"TT-直播-强商单","product_id":"BC","count":1,"max_count":100,"price":10,"max_cost":1000,"cost":10,"id":0,"cooperation_date":"2026-05","executor":"张岩","picture_links":"[{\\"url\\":\\"http://hwadmarket.youxi123.com/kol/resource/zhangyan02195/da2q0tg4533c73bghcog.png?Expires=4940742262&Signature=SpbifKKapWHv1iStBanFNxkfHXM%3D&UCloudPublicKey=TOKEN_bdf4d05e-8402-4ba5-b771-5b3561e1423a\\"},{\\"url\\":\\"http://hwadmarket.youxi123.com/kol/resource/zhangyan02195/da3eepivca1c73dp2no0.png?Expires=4940825958&Signature=OhUP%2BCjUOb5JroCzmzEiCbVOP0w%3D&UCloudPublicKey=TOKEN_bdf4d05e-8402-4ba5-b771-5b3561e1423a\\"}]","remark":"","region":"RU","nicknames":[{"label":"zy","value":92332438,"media_picture_links":"[\\"http://hwadmarket.youxi123.com/kol/resource/zhangyan02195/da2q0tg4533c73bghcog.png?Expires=4940742262\\u0026Signature=SpbifKKapWHv1iStBanFNxkfHXM%3D\\u0026UCloudPublicKey=TOKEN_bdf4d05e-8402-4ba5-b771-5b3561e1423a\\",\\"http://hwadmarket.youxi123.com/kol/resource/zhangyan02195/da3eepivca1c73dp2no0.png?Expires=4940825958\\u0026Signature=OhUP%2BCjUOb5JroCzmzEiCbVOP0w%3D\\u0026UCloudPublicKey=TOKEN_bdf4d05e-8402-4ba5-b771-5b3561e1423a\\"]"}],"media_info":"{\\"media_name\\":\\"zy\\",\\"media_id\\":92332438}","media_id":92332438,"media_name":""}],"expert_tag_ids":[16],"discount_tag_id":73,"audience_region":"RU"}
        """

    def get_jp_regions(self, is_show_resp: bool = False):
        """
        获取日本--省
        :param is_show_resp:
        :return:
        """
        url = self.kol_url + "/kol/api/geo/regions"
        params = {
            "country": "JP"
        }
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp
        if is_show_resp:
            print(json.dumps(resp))
        return status, resp

    def get_jp_cities(self, regions_id: int, is_show_resp: bool = False):
        """
        获取日本--市
        :param is_show_resp:
        :param regions_id:      省id
        :return:
        """
        url = self.kol_url + "/kol/api/geo/cities"
        params = {
            "country": "JP",
            "region": regions_id
        }
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp
        if is_show_resp:
            print(json.dumps(resp))
        return status, resp

    def update_video(self, performance_id, video_link, sparkcode=''):
        """
        上传履约视频
        :param performance_id:
        :param video_link:
        :param sparkcode:
        :return:
        """
        url = self.kol_url + "/kol/api/videos/performance"
        payload = {"performance_id": 923261148, "publish_time": "2026-10-16",
                   "video_link": "https://www.tiktok.com/@tahia.touch/video/7696817135573552406",
                   "sparkcode": "#03ZQOY89388APKUhpDMxapfWX1lVc/GzwOd856py2h6WTgQ2dMGjOlM3xbAxfwk=",
                   "confirm_overissue": False}

    def get_performances_order_details(self, order_id):
        """
        获取履约订单详情
        :param order_id:
        :return:
        """
        url = self.kol_url + f"/kol/api/performances/orders/{order_id}"
        status, resp = my_get(url, headers=self.headers)
        if not status:
            return status, resp
        order_info = resp.get("order")
        # print(json.dumps(order_info,indent=2))
        return status, order_info

    def query_kolsys_daren_list_data(self, count: int = 10):
        """查询达人管理列表数据"""
        url = self.kol_url + "/kol/resource/query"
        payload = {"page": 1, "count": count, "kol_regions": [], "regions": [], "languages": [], "media_sources": [],
                   "genders": [], "kol_types": [], "users": [], "creators": [], "res_id": "", "kol_name": "",
                   "expert_tag_ids": [], "discount_tag_ids": [], "contact": "", "media_name": "", "range": [],
                   "order_start_date": "", "order_end_date": ""}
        status, resp = my_post(url, headers=self.headers, data=json.dumps(payload))

        if not status:
            return status, resp
        code = resp.get("code")

        if code != 0:
            logger.error(f"接口状态码错误：{resp}")
            return False, resp

        users_info = resp.get("data").get("resources", [])
        return status, users_info

    def query_kolsys_order_list_data(self, count: int = 10):
        """查询订单管理列表数据"""
        url = self.kol_url + "/kol/resource/order/list"
        payload = {"kol_regions": [], "regions": [], "languages": [], "kol_types": [], "users": [], "res_id": "",
                   "kol_name": "", "contact": "", "media_name": "", "contract_id": "", "order_id": "", "status": [],
                   "dateRange": ["", ""], "start_date": "", "end_date": "", "business_status": [],
                   "contract_filter": "", "product_ids": [], "expert_tag_ids": [], "discount_tag_ids": [],
                   "activity_name": "", "page": 1, "count": count}
        status, resp = my_post(url, headers=self.headers, data=json.dumps(payload))

        if not status:
            return status, resp
        code = resp.get("code")

        if code != 0:
            logger.error(f"接口状态码错误：{resp}")
            return False, resp

        orders = resp.get("data").get("orders", [])
        # logger.info(json.dumps(orders))

        return status, orders

    def query_kolsys_contract_list_data(self, count: int = 10):
        """查询合同列表数据"""
        url = self.kol_url + "/kol/api/contracts/list"
        params = {"page": 1, "page_size": count}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp
        # logger.debug(json.dumps(resp,indent=2))
        items = resp.get("items", [])
        return status, items

    def query_kolsys_performances_list_data(self, count: int = 10):
        """获取履约列表数据"""
        url = self.kol_url + "/kol/api/performances/list"
        params = {"page": 1, "page_size": count}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp
        # logger.debug(json.dumps(resp))
        items = resp.get("items", [])
        print(len(items))
        return status, items

    def query_kolsys_video_list_data(self, count: int = 10):
        """查询视频管理列表数据"""
        url = self.kol_url + "/kol/api/videos/list"
        params = {"page": 1, "page_size": count}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp
        # logger.debug(json.dumps(resp,indent=2))

        items = resp.get("items", [])
        return status, items

    def query_kolsys_settle_detail_list_data(self, count: int = 10):
        """查询结算明细管理列表"""
        url = self.kol_url + "/kol/api/settle-detail/list"
        params = {"page": 1, "page_size": count}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp

        # logger.debug(json.dumps(resp))
        items = resp.get("items", [])
        return status, items

    def query_kolsys_payees_list_data(self, count: int = 10):
        """查询收款单位列表"""
        url = self.kol_url + "/kol/api/payees/list"
        params = {"page": 1, "page_size": count}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp
        # logger.debug(json.dumps(resp,indent=2))
        items = resp.get("items", [])
        return status, items

    def query_kolsys_activities_list_data(self, count: int = 10):
        """查询活动列表数据"""
        url = self.kol_url + "/kol/api/activities/list"
        params = {"page": 1, "page_size": count}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp

        # logger.debug(json.dumps(resp,indent=2))
        items = resp.get("data", {}).get("items", [])
        return status, items

    def query_kolsys_creatives_list_data(self, count: int = 10):
        """查询创意列表数据"""
        url = self.kol_url + "/kol/api/creatives/list"
        params = {"page": 1, "page_size": count}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp

        # logger.debug(json.dumps(resp,indent=2))
        items = resp.get("data", {}).get("items", [])
        return status, items

    def query_kilsys_hashtag_list_data(self, keyword_type, count: int = 10):
        """
        活动管理-hashtag
        :param keyword_type:      关键词
        """
        url = self.kol_url + "/kol/api/hashtag-configs"
        params = {"page": 1, "page_size": count, "keyword_type": keyword_type}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp

        # logger.debug(json.dumps(resp,indent=2))
        items = resp.get("items", [])
        return status, items

    def _build_order_reviews_payload(self, count: int = 10, **filters):
        """构建订单审核列表查询 payload（默认全量查询）。

        :param count:   分页大小
        :param filters: 需要覆盖的查询字段，仅传入的字段会覆盖默认值，
                        如 status=["TODO"]、kol_name="xx"、current_approver=[123] 等。
        """
        payload = {
            "users": [],
            "product_ids": [],
            "regions": [],
            "kol_regions": [],
            "kol_types": [],
            "res_id": "",
            "contact": "",
            "kol_name": "",
            "languages": [],
            "media_name": "",
            "current_approver": [],
            "activity_name": "",
            "order_status": [],
            "status": [],
            "page": 1,
            "count": count,
            "desc": True,
        }
        if filters:
            payload.update(filters)
        return payload

    def query_order_reviews_list_data_by_me(self, count: int = 10, **filters):
        """查询订单审核列表-我发起"""
        url = self.kol_url + "/kol/api/orders/approval/commits"
        payload = self._build_order_reviews_payload(count=count, **filters)
        status, resp = my_post(url, headers=self.headers, data=json.dumps(payload))
        if not status:
            return status, resp
        # logger.debug(json.dumps(resp,indent=2))
        approvals = resp.get("data", {}).get("approvals", [])
        return status, approvals

    def query_order_reviews_list_data_by_pending(self, count: int = 10, **filters):
        """查询订单审核列表-待审核"""
        url = self.kol_url + "/kol/api/orders/approval/pendings"
        payload = self._build_order_reviews_payload(count=count, **filters)
        status, resp = my_post(url, headers=self.headers, data=json.dumps(payload))
        if not status:
            return status, resp
        # logger.debug(json.dumps(resp,indent=2))
        approvals = resp.get("data", {}).get("approvals", [])
        return status, approvals

    def query_video_reviews_list_data(self, tab_type):
        """查询视频审核列表"""
        url = self.kol_url + "/kol/api/video-reviews/list"
        params = {"tab": tab_type, "page": 1, "page_size": 20}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp
        # logger.debug(json.dumps(resp))
        return status, resp

    def query_settle_detail_list_data(self, tab_type):
        """
        查询结算明细审核列表数据
        :param tab_type:     见SettleTab
        """
        url = self.kol_url + "/kol/api/settle-detail/approve/list"
        params = {"list_type": tab_type, "page": 1, "page_size": 20}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp
        # logger.debug(json.dumps(resp))
        return status, resp

    def query_kolline_daren_email_list_data(self,count: int = 10):
        """获取初次建联达人邮箱列表"""
        url = self.kolline_url + "/kollink/api/talents/email-candidates"
        params = {"page": 1, "page_size": count}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp

        code = resp.get("code", -1)
        if code != 0:
            return status, resp
        # logger.debug(json.dumps(resp, indent=2))
        email_list = resp.get("data", {}).get("list", [])
        return status, email_list

    def query_kolline_follow_up_email_list_data(self,count: int = 10):
        """获取follow_up邮箱列表"""
        url = self.kolline_url + "/kollink/api/email/send-detail-candidates"
        params = {"page": 1, "page_size": count}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp

        code = resp.get("code", -1)
        if code != 0:
            return status, resp
        # logger.debug(json.dumps(resp, indent=2))
        email_list = resp.get("data", {}).get("list", [])
        return status, email_list

    def query_email_send_record(self,count: int = 10):
        """查询建联邮件发送记录"""
        url = self.kolline_url + "/kollink/api/email/batches"
        params = {"page": 1, "page_size": count, "source": "send_record"}
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            return status, resp

        code = resp.get("code", -1)
        if code != 0:
            return status, resp
        # logger.debug(json.dumps(resp, indent=2))
        email_list = resp.get("data", {}).get("list", [])
        return status, email_list

    def query_data_analysis_by_daren_select(self, task_source,count: int = 10):
        """获取数据分析列表数据"""
        url = self.kolline_url + "/kollink/api/email/batches"
        "status=sending&status=partial_completed&status=completed&status=failed&date_start=2026-09-29&date_end=2026-10-28&page=1&page_size=10&task_source=selected"
        params = [
            ("status", "sending"),
            ("status", "partial_completed"),
            ("status", "completed"),
            ("status", "failed"),
            ("date_start", get_before_date(days=30, template="Ymd")),
            ("date_end", get_before_date(days=0, template="Ymd")),
            ("page", "1"),
            ("page_size", f"{count}"),
            ("task_source", task_source),
        ]
        status, resp = my_get(url, headers=self.headers, params=params)

        if not status:
            return status, resp
        code = resp.get("code", -1)
        if code != 0:
            return status, resp

        # logger.debug(json.dumps(resp, indent=2))
        send_record = resp.get("data", {}).get("list", [])
        return status, send_record


if __name__ == "__main__":
    kolsys_api = KolsysApi(is_debug=True)
    user_email = "xiaojiaqi@hungrystudio.com"  # 组员
    # user_email='liuli@hungrystudio.com'   # 组员
    user_email = "zhangyan02195@hungrystudio.com"  # 管理员
    # user_email = "guosiyi@hungrystudio.com"  #审核员
    # user_email='limengqi@hungrystudio.com'   #别的组长
    # user_email = "yekaiwulatai@hungrystudio.com"    #组长   dbbida8dupss73b6bht0
    # user_email='licongze@hungrystudio.com'
    # user_email='wangyaoying@hungrystudio.com'
    # user_email='liyajun@hungrystudio.com'
    # user_email='huangyunru@hungrystudio.com'  # 春兰
    kolsys_api.get_user_token(user_email, is_set_cache=False,
                              domains=[KolEnum.Domain.KOL_TEST])
    # kolsys_api.query_order_reviews_list_data(keyword_type=KolEnum.KeyWordType.SINGLE.value)
    kolsys_api.query_kolsys_performances_list_data()
    # kolsys_api.query_kol_users()
    # kolsys_api.create_order(res_id=KolEnum.PersonID.,media_source_list=[KolEnum.Channel.Social_tiktok.value])
    # kolsys_api.get_jp_regions()
    # kolsys_api.get_jp_cities(43)
    # print(get_before_date(days=0,template="Ymd"))
