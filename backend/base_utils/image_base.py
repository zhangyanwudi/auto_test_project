import json
from PIL import Image
from base_utils.path_base import *
from base_utils.config_base import get_config
import os, io, subprocess


class ImageBase():

    def __init__(self, secret_id=None, secret_key=None):
        _ocr = get_config('tencent_cloud', 'ocr') or {}
        self.secret_id = secret_id or os.environ.get('TENCENT_OCR_SECRET_ID') or _ocr.get('secret_id')
        self.secret_key = secret_key or os.environ.get('TENCENT_OCR_SECRET_KEY') or _ocr.get('secret_key')

    def image_text_orc(self, image_base64_content):
        """
        图片文字识别
        :param image_base64_content:        图片base64信息流
        :return:
        """
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
        from tencentcloud.ocr.v20181119 import ocr_client, models

        cred = credential.Credential(self.secret_id, self.secret_key)
        # 实例化一个http选项，可选的，没有特殊需求可以跳过
        httpProfile = HttpProfile()
        httpProfile.endpoint = "ocr.tencentcloudapi.com"
        # 实例化一个client选项，可选的，没有特殊需求可以跳过
        clientProfile = ClientProfile()
        clientProfile.httpProfile = httpProfile
        # 实例化要请求产品的client对象,clientProfile是可选的
        client = ocr_client.OcrClient(cred, "", clientProfile)
        req = models.GeneralAccurateOCRRequest()
        # 腾讯云要求纯 Base64，勿带 data:image/... 前缀
        params = {'ImageBase64': image_base64_content}
        req.from_json_string(json.dumps(params))

        # 返回的resp是一个GeneralAccurateOCRResponse的实例，与请求对象对应
        resp = client.GeneralAccurateOCR(req)
        return resp.to_json_string()

    def change_resize(self, height, width, input_path, output_path):
        """修改图片尺寸"""
        # 打开图片
        with Image.open(input_path) as img_obj:
            # 调整图片尺寸为28x28
            resized_img = img_obj.resize((width,height))
            # 保存调整后的图片
            resized_img.save(output_path)


    def batch_compress_image(self, image_input_dir, target_size_kb):
        """
        批量压缩图像大小
        :param image_input_dir:     图片目录
        :param target_size_kb:     图片质量（kb）
        :return:
        """
        image_files = get_directory_file(path=image_input_dir, file_type=[".png"], is_join_path=True)
        for image_file in image_files:
            self.compress_image(input_path=image_file, output_path=image_file, target_size_kb=target_size_kb)


    def png_to_jpeg(self, input_path,is_rm_old_file=False):
        """
        将图片png转成jpeg
        :param input_path:      图片路径
        :return:
        """
        file_name=get_folder_name(input_path,is_extension=False)
        output_dir=get_path(input_path)
        output_path=joint_path(output_dir,f"{file_name}.jpeg")
        # 打开一个现有的PNG图片
        png_image = Image.open(input_path)
        # 将图片转换为RGB模式 (JPEG不支持透明度，即alpha通道）
        rgb_image = png_image.convert('RGB')
        # 保存为JPEG格式
        rgb_image.save(output_path, format='JPEG')
        # 移除原有文件
        if is_rm_old_file:
            remove(input_path)
        return output_path

    def jpg_to_png(self,input_path,is_rm_old_file=False):
        """
        将jpg转成png
        :param input_path: 图片路径
        :return:
        """
        #
        file_name = get_folder_name(input_path, is_extension=False)
        output_dir = get_path(input_path)
        output_path = joint_path(output_dir, f"{file_name}.png")
        # 打开一个现有的JPG图片
        jpg_image = Image.open(input_path)
        # # 将图像转换为P模式（调色板模式)
        # jpg_image = jpg_image.convert('P', palette=Image.ADAPTIVE)
        # 设置初始压缩级别
        compress_level = 9  # PNG格式的压缩级别从0（无压缩）到9
        while True:
            # 保存为PNG格式
            jpg_image.save(output_path, format='PNG',compress_level=compress_level)
            if self.query_size_kb(output_path)<1024 or compress_level == 0:
                break
            compress_level -= 1  # 尝试更高的压缩级别
        if is_rm_old_file:
            remove(input_path)
        return output_path

    def batch_jpg_to_png(self,input_files,is_rm_old_file=False):
        """
        批量转换文件
        :param input_files:       输入文件列表
        :param is_rm_old_file:      是否删除原有文件
        :return:
        """
        for input_file in input_files:
            self.jpg_to_png(input_path=input_file,is_rm_old_file=is_rm_old_file)


    def query_resize(self,input_path):
        """查询图片尺寸大小"""
        # 打开一个图片文件
        image = Image.open(input_path)  # 可以是任何支持的图片格式
        # 获取图片的尺寸
        width, height = image.size
        return height,width

    def query_size_kb(self,input_path):
        """查询图片大小"""
        # 获取图片文件大小
        file_size = os.path.getsize(input_path)
        # 将字节转换为更友好的单位，例如 KB、MB
        file_size_kb = file_size / 1024  # 转换为KB
        # print(round(file_size_kb,2))
        return round(file_size_kb,2)

    def _open_image(self, image_path):
        """打开图片"""
        # 打开图片
        with Image.open(image_path) as img_obj:
            return img_obj

    def compress_png_pngquant(self,input_path, output_path, quality="30-50"):
        """
        使用 pngquant 压缩 PNG 图片
        需要安装：brew install pngquant
        :param input_path: 原始 PNG 图片路径
        :param output_path: 压缩后 PNG 保存路径
        :param quality: 压缩质量范围，默认为 65-80
        """
        # 判断输出文件是否存在
        if exists(output_path):
            remove(output_path)
        try:
            # 调用 pngquant 命令行进行压缩
            subprocess.run(
                ["pngquant", "--quality", quality, "--output", output_path, input_path],
                check=True,
            )
            print(f"图片已使用 pngquant 压缩并保存到 {output_path}")
        except FileNotFoundError:
            print("请确保已安装 pngquant 并将其添加到系统 PATH 中")
        except subprocess.CalledProcessError:
            print("pngquant 压缩过程中出现错误")


    def compress_image(self,input_path, output_path,target_size_kb):
        """图片压缩"""
        if ".png" in input_path:
            self.compress_png_pngquant(input_path, output_path)
        else:
            img = Image.open(input_path)
            quality = 95  # 初始压缩质量
            while True:
                # 将图像保存到内存中
                output_io = io.BytesIO()
                img.save(output_io, 'JPEG', quality=quality)
                size_kb = len(output_io.getvalue()) / 1024

                if size_kb <= target_size_kb or quality <= 10:
                    break
                quality -= 5  # 每次减少5的压缩质量

            # 将图像保存到输出路径
            with open(output_path, 'wb') as f:
                f.write(output_io.getvalue())


    def batch_change_resize(self,image_dir):
        """
        批量修改
        :param image_dir:
        :return:
        """
        for index,image_path in enumerate(get_directory_file(path=image_dir,file_type=[".png"],is_join_path=True)):
            self.change_resize(
                height=1920, width=1080,
                input_path=image_path,output_path=image_path
            )

if __name__ == "__main__":
    img_base = ImageBase()
    from base_utils.common import read_file_by_rb
    from base_utils.secrecy_base import base64_en
    text=read_file_by_rb("QQ20260408-160317.png")
    print(img_base.image_text_orc(base64_en(text)))