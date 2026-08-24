# !/usr/bin/env python3
"""
修复版AAB文件安装脚本
解决设备权限检查和安装失败问题
"""

import subprocess
import os
import sys,pathlib
from pathlib import Path
from path_base import get_folder_name,get_directory_file,exists,remove,joint_path
from adb_base import AdbBase


class AABInstaller:
    def __init__(self, aab_path, output_dir=None):
        self.aab_path = Path(aab_path)
        self.output_dir = Path(output_dir) if output_dir else self.aab_path.parent
        self.apks_path = joint_path(self.output_dir,f"{self.aab_path.stem}.apks")
        self.adb_utils=AdbBase()
        # ========== 签名信息 ==========
        self.key_path = joint_path(self.output_dir,"release.keystore")
        self.key_pwd="123456"

    def check_prerequisites(self):
        """检查前置条件"""
        print("🔍 检查前置条件...")

        if not self.aab_path.exists():
            raise FileNotFoundError(f"AAB文件不存在: {self.aab_path}")

        try:
            result = subprocess.run(['bundletool', 'version'],
                                    capture_output=True, text=True, check=True)
            print(f"✅ Bundletool版本: {result.stdout.strip()}")
        except subprocess.CalledProcessError:
            raise RuntimeError("bundletool命令不可用")

        try:
            result = subprocess.run(['adb', 'devices'],
                                    capture_output=True, text=True, check=True)
            devices = [line for line in result.stdout.split('\n')
                       if 'device' in line and 'offline' not in line]
            if len(devices) >= 1:
                print("✅ 检测到连接的Android设备")
                # 强制开启安装权限
                self.force_enable_installation_permissions()
            else:
                raise RuntimeError("未检测到连接的Android设备")
        except subprocess.CalledProcessError:
            raise RuntimeError("ADB命令不可用")

    def force_enable_installation_permissions(self):
        """强制开启设备安装权限"""
        print("🔓 强制开启设备安装权限...")

        # 检查当前权限状态
        check_cmd = ['adb', 'shell', 'settings', 'get', 'secure', 'install_non_market_apps']

        try:
            result = subprocess.run(check_cmd, capture_output=True, text=True, check=True)
            current_status = result.stdout.strip()

            if current_status == '0':
                print("⚠️  设备限制未知来源安装，正在强制开启...")
                # 开启未知来源安装权限
                enable_cmd = ['adb', 'shell', 'settings', 'put', 'secure', 'install_non_market_apps', '1']
                subprocess.run(enable_cmd, capture_output=True, check=True)
                print("✅ 已强制开启未知来源安装权限")
            else:
                print("✅ 设备已开启未知来源安装权限")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  无法检查设备权限状态: {e.stderr}")

        # 额外检查系统级权限设置
        try:
            # 检查开发者选项中的USB安装权限
            usb_install_cmd = ['adb', 'shell', 'settings', 'put', 'global', 'adb_enabled', '1']
            subprocess.run(usb_install_cmd, capture_output=True, check=True)
        except:
            pass


    def create_keystore(self):
        """生成签名"""
        # 如果文件已存在就先删掉，避免 keytool 交互式询问
        if exists(self.key_path):
            self.key_path.unlink()

        keytool_cmd = [
            "keytool", "-genkeypair",
            "-keystore", str(self.key_path),
            "-alias", "release",
            "-storepass", self.key_pwd,
            "-keypass", self.key_pwd,
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",  # 有效期 27 年，够用
            "-dname", f"CN=release, OU=AutoTest, O=ZnYan, L=SZ, S=GD, C=CN"
        ]
        try:
            result = subprocess.run(keytool_cmd, capture_output=True, text=True, check=True)
            print(f"✅ 签名文件生成成功")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ 签名文件生成失败: {e.stderr}")
            return False

    def build_apks(self):
        """构建APKS文件"""
        print(f"🛠️  开始构建APKS文件...")
        # 生成key
        if not exists(self.key_path):
            if not self.create_keystore():
                return False

        # 构建APKS文件
        cmd = [
            'bundletool', 'build-apks',
            f'--bundle={self.aab_path}',
            f'--output={self.apks_path}',
            '--overwrite',
            f'--ks={self.key_path}',
            f'--ks-pass=pass:{self.key_pwd}',
            f'--ks-key-alias=release',
            f'--key-pass=pass:{self.key_pwd}',
            '--mode=universal'
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✅ APKS文件构建成功: {self.apks_path}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ APKS构建失败: {e.stderr}")
            return False

    def install_apks(self):
        """安装APKS文件到设备"""
        cmd = [
            'bundletool', 'install-apks',
            f'--apks={self.apks_path}'
        ]

        # 获取是否安装状态
        is_update = self.check_package_name()

        if is_update:
            print(f"📱 开始覆盖安装APKS文件...")
            # 检查签名是否存在，不存在不能进行安装
            if not exists(self.key_path):
                print(f"❌ 签名文件不存在")
                return
        else:
            print(f"📱 开始安装APKS文件...")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True,encoding='utf-8')
            print("✅ 应用安装成功！")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ 安装失败: {e.stderr}")
            # # 清理可能存在的残留数据
            # self.clean_previous_installation()
            return False


    def clean_previous_installation(self):
        """清理之前安装的残留数据"""
        print("🧹 清理残留数据...")
        # 删除apks文件
        remove(self.apks_path)


    def install_aab_to_device(self):
        """完整安装流程"""
        print("🚀 开始AAB文件安装流程...")
        print(f"   AAB文件: {self.aab_path}")

        try:
            self.check_prerequisites()

            if not self.build_apks():
                return False

            if not self.install_apks():
                return False

            print("🎉 AAB文件安装完成！")
            return True
        except Exception as e:
            print(f"❌ 安装过程中发生错误: {e}")
            return False
        finally:
            self.clean_previous_installation()


    def extract_package_name(self):
        """提取包名"""
        file_name = get_folder_name(self.aab_path, is_extension=False)
        return file_name.split("_")[0]

    def check_package_name(self):
        """检查包名"""
        print("🔍 检查安装包是否已安装...")
        file_name=get_folder_name(self.aab_path,is_extension=False)
        return self.adb_utils.is_include_package_name(file_name.split("_")[0])

def main():
    if len(sys.argv) < 2:
        print("使用方法: python aab_installer_fixed.py <aab文件路径> [输出目录]")
        sys.exit(1)

    aab_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    installer = AABInstaller(aab_path, output_dir)

    try:
        success = installer.install_aab_to_device()
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"❌ 安装过程中发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
