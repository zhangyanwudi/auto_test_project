# -*- coding: utf-8 -*-
import json
from dataclasses import dataclass, field
from typing import Optional, Tuple
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
        Social_youtube="Social_youtube"
        Social_tiktok = "Social_tiktok"

    class PersonID(str, Enum):
        ZnYan_kol="M915BFH9KV"
        ZnYan = "1215BBPJ21"

    class Domain(str, Enum):
        """set_auth 注入登录态的目标站点域名。"""
        MARKETING_TEST = "https://marketing-test.youxi123.com"
        # MARKETING_DEV1 = "https://marketing-dev1.youxi123.com"
        # MI_TEST = "https://mi-test.youxi123.com"


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
        if not self.is_debug:
            self.default_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjbGllbnRfaXAiOiIzOS4xNTUuMTcyLjM0IiwiY3JlYXRlZF9hdCI6MTc4OTkwNjA2NiwiZW1haWwiOiJ6aGFuZ3lhbjAyMTk1QGh1bmdyeXN0dWRpby5jb20iLCJmdWxsX25hbWUiOiLlvKDlsqkiLCJpc3MiOiJpYW0tbWkueW91eGkxMjMuY29tIiwidXNlcl9pZCI6IjZhODU3NGVhNWI1NTI4NjdkNGU1OGRhZCIsInVzZXJuYW1lIjoiemhhbmd5YW4wMjE5NSIsIndvcmtjb2RlIjoiMDAxMjE3In0.JUxuozq_6x2n4ZqytczLIhZmctGzmqEnfIBrzwNcFRY"
            self.mi_url = "https://iam-mi.youxi123.com"
            self.kol_url = "https://marketing.youxi123.com/1"
        self.headers = {"Authorization": f"Bearer {self.default_token}"}

    def _update_headers(self):
        """更新headers"""
        self.headers = {"Authorization": f"Bearer {self.default_token}"}

    def get_user_token(self,
                       user_email: str,
                       is_set_cache: bool = False,
                       ):
        """
        获取用户token
        :param user_email:      用户邮箱
        :param is_set_cache:    是否设置浏览器缓存   True-设置，False-不设置
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
            self._set_user_cache(user_email, data)
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

    def _set_user_cache(self, user_email: str, data: dict):
        """把 token 接口返回的登录态注入浏览器 localStorage（is_set_cache=True 时调用）。

        :param user_email: 用户邮箱（仅用于日志）
        :param data:       token 接口返回的 data 字段
        """
        from base_utils.push_auth import set_auth
        user = data.get("user") or {}
        try:
            for domain in self.Domain:
                mi_web_user_info = self._build_mi_web_user_info(user)
                set_auth(
                    domain=domain.value,
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
            logger.info(f"【{user_email}】缓存设置成功！")
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

    def get_user_token_payload(self, user_email: str) -> dict:
        """获取用户 token 并返回 {domain, values}，供 Playwright 注入 localStorage（纯函数）。

        不调用 push_auth、不操作本机浏览器；原有 get_user_token(is_set_cache=True) 逻辑不受影响。

        返回:
            dict — {"domain": "https://marketing-test.youxi123.com", "values": {7 个 key}}
        """
        url = self.mi_url + "/api/iam/users/token"
        params = {"email": user_email}
        logger.info(f"获取用户 token payload，email=【{user_email}】")
        status, resp = my_get(url, headers=self.headers, params=params)
        if not status:
            raise RuntimeError(f"获取 token 请求失败：{resp}")
        code_status = resp.get("status").get("code")
        if code_status != 0:
            raise RuntimeError(f"接口 code 错误，code_status:{code_status}")
        data = resp.get("data")
        self.default_token = data.get("token")
        self._update_headers()
        return {
            "domain": "https://marketing-test.youxi123.com",
            "values": self._build_auth_payload(data),
        }

    def create_order(self, res_id:str,media_source_list:list[str], price:int=100):
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
            "price_infos": _build_price_infos(media_source_list,price),
            "activity_code": "CPN20261010092"
        }
        status,resp=my_post(url, headers=self.headers, data=json.dumps(payload))
        if not status:
            return status, resp
        print(resp)
        # 成功返回数据示例      {'code': 0, 'data': {'order_id': '1215BBPJ21-26100036'}, 'message': 'ok'}
        order_id=resp.get("data").get("order_id")
        return order_id

    def create_order_to_approval(self):
        """创建订单信息并提审"""
        url=self.kol_url + "/kol/api/orders/approval/create"
        """
        {"order_id":"1215BBPJ21-26100046","checks":[{"extra":"1","extra_ref":"1791884203431","kol_type":"","media_source":"Social_tiktok","video_type":"TT-直播-强商单","product_id":"BC","count":1,"max_count":100,"price":10,"max_cost":1000,"cost":10,"id":0,"cooperation_date":"2026-05","executor":"张岩","picture_links":"[{\\"url\\":\\"http://hwadmarket.youxi123.com/kol/resource/zhangyan02195/da2q0tg4533c73bghcog.png?Expires=4940742262&Signature=SpbifKKapWHv1iStBanFNxkfHXM%3D&UCloudPublicKey=TOKEN_bdf4d05e-8402-4ba5-b771-5b3561e1423a\\"},{\\"url\\":\\"http://hwadmarket.youxi123.com/kol/resource/zhangyan02195/da3eepivca1c73dp2no0.png?Expires=4940825958&Signature=OhUP%2BCjUOb5JroCzmzEiCbVOP0w%3D&UCloudPublicKey=TOKEN_bdf4d05e-8402-4ba5-b771-5b3561e1423a\\"}]","remark":"","region":"RU","nicknames":[{"label":"zy","value":92332438,"media_picture_links":"[\\"http://hwadmarket.youxi123.com/kol/resource/zhangyan02195/da2q0tg4533c73bghcog.png?Expires=4940742262\\u0026Signature=SpbifKKapWHv1iStBanFNxkfHXM%3D\\u0026UCloudPublicKey=TOKEN_bdf4d05e-8402-4ba5-b771-5b3561e1423a\\",\\"http://hwadmarket.youxi123.com/kol/resource/zhangyan02195/da3eepivca1c73dp2no0.png?Expires=4940825958\\u0026Signature=OhUP%2BCjUOb5JroCzmzEiCbVOP0w%3D\\u0026UCloudPublicKey=TOKEN_bdf4d05e-8402-4ba5-b771-5b3561e1423a\\"]"}],"media_info":"{\\"media_name\\":\\"zy\\",\\"media_id\\":92332438}","media_id":92332438,"media_name":""}],"expert_tag_ids":[16],"discount_tag_id":73,"audience_region":"RU"}
        """

    def get_jp_regions(self, is_show_resp:bool=False):
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

    def update_video(self,performance_id,video_link,sparkcode=''):
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

    def get_performances_order_details(self,order_id):
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

    def query_kol_users(self,count:int=10):
        """获取达人列表数据"""
        url = self.kol_url + "/kol/resource/query"
        payload = {"page":1,"count":count,"kol_regions":[],"regions":[],"languages":[],"media_sources":[],"genders":[],"kol_types":[],"users":[],"creators":[],"res_id":"","kol_name":"","expert_tag_ids":[],"discount_tag_ids":[],"contact":"","media_name":"","range":[],"order_start_date":"","order_end_date":""}
        status, resp = my_post(url, headers=self.headers, data=json.dumps(payload))

        if not status:
            return status, resp
        code = resp.get("code")

        if code != 0:
            return False, resp

        users_info=resp.get("data").get("resources")
        # print(json.dumps(users_info, indent=2))
        return status, users_info



if __name__ == "__main__":
    kolsys_api = KolsysApi(is_debug=True)
    # user_email = "xiaojiaqi@hungrystudio.com"    # 组员
    user_email='liuli@hungrystudio.com'   # 组员
    user_email = "zhangyan02195@hungrystudio.com"  # 管理员
    # user_email = "guosiyi@hungrystudio.com"  #审核员
    # user_email='limengqi@hungrystudio.com'   #别的组长
    # user_email = "yekaiwulatai@hungrystudio.com"    #组长
    # user_email='licongze@hungrystudio.com'
    # user_email='wangyaoying@hungrystudio.com'
    # user_email='liyajun@hungrystudio.com'
    kolsys_api.get_user_token(user_email, is_set_cache=True)
    # kolsys_api.get_performances_order_details(order_id="1215BBPJ21-26100046")
    # kolsys_api.query_kol_users()
    # kolsys_api.create_order(res_id=KolEnum.PersonID.,media_source_list=[KolEnum.Channel.Social_tiktok.value])
    # kolsys_api.get_jp_regions()
    # kolsys_api.get_jp_cities(43)
