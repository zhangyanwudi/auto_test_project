import base64, hashlib, hmac, time, json, requests
from base_utils.logger_base import setting_logger
from base_utils.config_base import get_config

logger=setting_logger()
class MessageType:
    MSGTYPE_TEXT = "text"
    MSGTYPE_LINK = "link"
    MSGTYPE_MARKDOWN = "markdown"
    MSGTYPE_ACTIONCARD = "actionCard"
    MSGTYPE_FEEDCARD = "feedCard"
    MSGTYPE_IMAGE = "image"


class RobotMessage():
    def __init__(self, webhook_url, secret):
        self.timestamp, self.signature = self._get_signature(secret)
        self.webhook_url = f"{webhook_url}&timestamp={self.timestamp}&sign={self.signature}"

    def _get_signature(self, secret):
        """加签"""
        # 当前时间戳
        timestamp = str(int(time.time() * 1000))
        # 生成待签名字符串
        string_to_sign = f"{timestamp}\n{secret}"
        # 计算 HMAC-SHA256 签名
        hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha256).digest()
        # 对签名进行 Base64 编码
        signature = base64.b64encode(hmac_code).decode('utf-8')
        return timestamp, signature


    def _request_message(self, message):
        """发送消息"""
        # 发送 POST 请求
        response = requests.post(self.webhook_url, data=json.dumps(message),
                                 headers={'Content-Type': 'application/json'})
        # 打印响应
        if response.json()["errcode"] == 0:
            logger.debug("消息发送成功")
            return True
        logger.debug(f"消息发送失败：{response['msg']}")
        return False


    def send_actioncard_message(self,title,text_message,link_title,image_url):
        """
        发送actioncard消息
        :params     title               标题
        :params     text_message        内容消息
        :params     link_title        链接标题
        :params     image_url        图片链接
        """
        # 构建消息体
        message = {
            "msgtype": MessageType.MSGTYPE_ACTIONCARD,
            "actionCard": {
                "title": title,
                "text": text_message,
                "btns": [
                    {
                        "title": link_title,
                        "actionURL": f"dingtalk://dingtalkclient/page/link?url={image_url}&pc_slide=false"  # 替换为您的图片链接
                    }
                ]
            }
        }
        return self._request_message(message)

    def send_text_message(self,text_message,at_user_ids:list=None):
        """
        发送文本消息
        :params     at_user_ids          钉钉用户id列表
        :params     text_message        内容消息
        """
        message = {
            "msgtype": MessageType.MSGTYPE_TEXT,
            "text": {
                "content": text_message
            }
        }
        if at_user_ids:
            message.setdefault("at",{"atUserIds": at_user_ids,"isAtAll": False})
        return self._request_message(message)


if __name__ == "__main__":
    webhook_url = get_config('dingtalk', 'robot_webhook_url', '')
    robot_secret = get_config('dingtalk', 'robot_secret', '')
    robot_msg = RobotMessage(webhook_url, secret=robot_secret)
    robot_msg.send_text_message(text_message="XXXX需求出现异常，请及时排查")