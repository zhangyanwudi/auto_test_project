# config=utf-8
import sys
from pathlib import Path
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))
from base_utils.logger_base import setting_logger
from base_utils.time_base import get_date, get_timestamp_ms, get_before
import time, os,subprocess
from base_utils.path_base import check_dirs, get_path,joint_path
from base_utils.common import write_to_file
import re,json

logger = setting_logger(tag="adb 命令")


def check_device(method):
    def wrapper(self, *args, **kwargs):
        if self.device is None:
            self.opt_device()  # 调用opt_device方法
        return method(self, *args, **kwargs)  # 继续执行原方法

    return wrapper


class AdbBase(object):
    """
    app操作
    """

    def __init__(self, device=None):
        self.device = device
        # 用于存放日志消息
        self.logcat_queue = []

    def opt_device(self):
        """选择devices"""
        devices = self.get_all_devices()
        if len(devices) > 1:
            for idx, dev in enumerate(devices):
                print(f'{idx}-{dev}')
            # 输入选择的设备编号
            while True:
                idx = input('选择设备: ')
                idx = int(idx)
                if idx >= len(devices) or idx < 0:
                    print("选择不在范围内，重新选择！！！")
                    continue
                self.device = devices[idx]
                return devices[idx]
        elif len(devices) == 1:
            self.device = devices[0]
            return devices[0]
        raise ValueError("没有连接的手机！")

    @check_device
    def power(self):
        """点亮屏幕"""
        self.appShell(cmd=f"adb -s {self.device} shell input keyevent 26")

    def get_all_devices(self):
        """获取全部设备"""
        result = self.appShell(cmd="adb devices")
        # result=appShell(cmd="adb devices")
        if result == "":
            raise Exception("不能正常执行adb命令，请检查！！！")
        result = result.strip().split('\n')[1:]
        result = [i.split('\t')[0] for i in result]
        if len(result) == 0:
            # raise Exception("电脑未连接设备信息，无法进行正常测试。。")
            return []
        return result

    @check_device
    def get_brand(self):
        """获取手机厂商"""
        return self.appShell(cmd=f"adb -d -s {self.device} shell getprop ro.product.brand")

    @check_device
    def get_model(self):
        """获取手机型号"""
        return self.appShell(cmd=f"adb -s {self.device} -d shell getprop ro.product.model")

    @check_device
    def get_system_build(self):
        """获取系统版本"""
        return self.appShell(cmd=f"adb -s {self.device} shell getprop ro.build.version.release")

    def batch_devices_install_app(self, package_path):
        """
        批量设备安装app
        :param package_path:        安装包路径
        :return:
        """
        cmd = f"adb devices | tail -n +2 | cut -sf 1 | xargs -I {{}} adb -s {{}} install -r {package_path}"
        return self.appShell(cmd=cmd)

    @check_device
    def get_package_names(self):
        """获取包名"""
        packages_list = self.appShell(cmd=f"adb -s {self.device} shell pm list packages")
        return packages_list.replace("package:","").split("\n")

    def is_include_package_name(self,package_name):
        """是否包含包名"""
        packages_list=self.get_package_names()
        if package_name in packages_list:
            return True
        return False

    def appShell(self, cmd):
        """执行手机命令"""
        content = os.popen(cmd)
        return content.read().strip()

    def get_connect_device_status(self):
        cmd="adb devices"
        result=self.appShell(cmd)
        for line in result.strip().split('\n')[1:]:
            if line.strip():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == self.device and parts[1] == 'device':
                    return True
        return False

    def app_swipe_up(self):
        """滑动显示解锁"""
        size = self.get_print_size()
        w = int(size.split("x")[0])
        h = int(size.split("x")[1])
        return self.appShell(cmd=f"adb -s {self.device} shell input swipe {w / 2} {h * 0.9} {w / 2} {h * 0.1}")

    def _screen_awaken(self):
        """唤醒屏幕"""
        ScreenStatus = self.get_power_info(key="mWakefulness=").split("=")[1]
        # 判断是否为熄屏   Asleep为熄屏
        if ScreenStatus == "Asleep":
            self.power()
            time.sleep(1)
            return True
        return False

    def _in_screen_page(self):
        """
        进入手机应用页面
        :return:  True-在手机应用页面  False-不在手机应用页面
        """
        PageStatu = self.get_power_info(key="mUserActivityTimeoutOverrideFromWindowManager=").split("=")[1]
        # -1 已进入应用界面
        if PageStatu != "-1":
            self.app_swipe_up()
            time.sleep(1)
            if self.get_lock_statu() != False:
                return False
        return True

    def get_lock_statu(self):
        """
        获取是否锁屏
        :return: true-有密码  false-没有密码
        """
        LockStatus = self.get_lock_info(key="secure")
        if LockStatus == "true":
            print("屏幕有锁屏密码，请取消后进行操作！！！")
            return True
        return False

    def get_lock_info(self, key=None):
        """返回屏幕锁屏信息"""
        if key == None:
            return self.appShell(cmd=f"adb -s {self.device} shell dumpsys window")
        return self.appShell(cmd=f"adb -s {self.device} shell dumpsys window |grep '{key}'").split("=")[1]

    def get_power_info(self, key=None):
        """获取屏幕状态信息"""
        if key == None:
            return self.appShell(cmd=f"adb -s {self.device} shell dumpsys power")
        return self.appShell(cmd=f"adb -s {self.device} shell dumpsys power | grep '{key}'")

    def get_print_size(self):
        """获取屏幕大小"""
        cmd = f"adb -s {self.device} shell wm size"
        return self.appShell(cmd=cmd).split("Physical size: ")[1]

    def get_ip(self):
        """获取设备ip"""
        cmd = f"adb -s {self.device} shell ifconfig | grep Mask"
        return str(self.appShell(cmd=cmd)).split("inet addr:")[1].split(" ")[0]

    @check_device
    def get_app_verison(self,package_name):
        """获取App版本号（app为配置中的app）"""
        cmd = f"adb -s {self.device} shell pm dump {package_name} | grep 'versionName'"
        return self.appShell(cmd=cmd).split("=")[1]

    def push_sms(self, phone_number, sms_content):
        """
        发送短信
        :param phone_number: 发送目的号码
        :param sms_content: 短信内容
        :return:
        """
        cmd = f"adb -s {self.device} shell am start -a android.intent.action.SENDTO -d sms:{phone_number} --es sms_body '{sms_content}' --ez exit_on_sent true "
        return self.appShell(cmd=cmd)

    def get_imei(self):
        """
        获取imei
        :return:
        """
        cmd = f"adb -s {self.device} shell dumpsys iphonesubinfo"
        value = self.appShell(cmd=cmd)
        if value != "":
            return value
        cmd = f"adb -s {self.device} shell getprop gsm.baseband.imei"
        return self.appShell(cmd=cmd)

    def get_mac(self):
        """
        获取手机MAC地址
        :return:  mac地址
        """
        cmd = f"adb -s {self.device} shell ip addr show wlan0"
        mac = self.appShell(cmd=cmd).split("link/ether ")[1].split(" ")[0]
        return mac

    def get_all_model(self, devices_list):
        """
        获取多个手机型号
        :param devices_list:
        :return:
        """
        model_list = []
        for device in devices_list:
            self.device = device
            model_list.append(self.get_model())
        return model_list

    def get_all_brand(self, devices_list):
        """
        获取多个手机品牌
        :param devices_list:
        :return:
        """
        brand_list = []
        for device in devices_list:
            self.device = device
            brand_list.append(self.get_brand())
        return brand_list

    @check_device
    def stop_app(self, package):
        """
        停止app应用不清除数据
        :param package: app包名
        :return:
        """
        cmd = f"adb -s {self.device} shell am force-stop {package}"
        self.appShell(cmd=cmd)

    @check_device
    def clear_app_data(self, package_name):
        """
        清除app应用数据
        :param package:
        :return:
        """
        cmd = f"adb -s {self.device} shell pm clear {package_name}"
        self.appShell(cmd=cmd)

    @check_device
    def uninstall_app(self, package):
        """
        卸载app
        :param package:
        :return:
        """
        cmd = f"adb -s {self.device} shell pm list {package}"
        self.appShell(cmd=cmd)

    @check_device
    def screencap(self, fPath=None, fName="screen"):
        """
        进行adb 截图
        :param fPath: 电脑上路径
        :return:
        """
        output_name = f"{fName}_{get_timestamp_ms()}.png"
        cmd = f"adb -s {self.device} shell screencap /sdcard/{output_name}"
        self.appShell(cmd=cmd)
        "/* 电脑路径不为空，表示需要将文件传回电脑 */"
        if fPath:
            check_dirs(fPath)
            logger(f"将手机【/sdcard/{output_name}】传到电脑【{fPath}】", filename="app_auto")
            self.pull(fPath=fPath, sPath="/sdcard/", sName=output_name)

    @check_device
    def pull(self, fPath, sPath, sName):
        """
        将手机文件传到电脑
        :param fPath: 电脑上路径
        :param sPath: 手机系统路径
        :param sName: 手机系统文件名称（带扩展名）
        :return:
        """
        cmd = f"adb -s {self.device} pull {sPath}{sName} {fPath}"
        logger.debug(f"执行命令：【{cmd}】")
        self.appShell(cmd=cmd)

    def unlock_phone(self):
        """
        解锁手机
        :return:
        """
        self._screen_awaken()
        if not self._in_screen_page():
            raise Exception("手机可能设有密码，请取消后再操作！！！")
        return True

    @check_device
    def export_crash_log(self, file_path=None, file_name="crash1.log"):
        """
        导出手机崩溃日志
        :param fPath: 电脑上路径
        :param fName: 文件名称
        :return:
        """
        if not file_path:
            file_path = get_path(file_path=__file__, index=1)
        check_dirs(file_path)
        cmd = f"adb -s {self.device} shell dumpsys dropbox --print >{file_path}/{file_name}"
        self.appShell(cmd)


    @check_device
    def get_package_info(self,package_name):
        """包信息管理"""
        cmd = f"adb -s {self.device} shell dumpsys package {package_name}"
        print(self.appShell(cmd))

    @check_device
    def input_text(self, content, is_clear_data=False, clear_second=1):
        """录入内容"""
        if is_clear_data:
            self.clear_input_text(clear_second)
        # 做个空格转义，空格录入失败
        content = content.replace(" ", "%s")
        cmd = f"adb -s {self.device} shell input text '{content}'"
        self.appShell(cmd)

    def clear_input_text(self, clear_second=1):
        """清空录入内容"""
        end_time = get_before(seconds=clear_second, is_tmiestamp=True)
        while True:
            cmd = f"adb -s {self.device} shell input keyevent KEYCODE_DEL"
            self.appShell(cmd)
            if get_timestamp_ms() > end_time:
                break

    @check_device
    def adb_kill_server(self):
        """kill server"""
        cmd=f"adb -s {self.device} kill-server"
        self.appShell(cmd)

    @check_device
    def adb_start_server(self):
        """start server"""
        cmd = f"adb -s {self.device} start-server"
        self.appShell(cmd)

    @check_device
    def query_cpu_meny_info(self, package_name):
        cmd = f"adb -s {self.device} shell top -m 10 -d 1 | grep {package_name}"
        self.appShell(cmd)

    @check_device
    def query_cpu_abi(self):
        """获取cpu框架"""
        cmd=f"adb -s {self.device} shell getprop ro.product.cpu.abi"
        return self.appShell(cmd)

    @check_device
    def output_logcat(self, keyword=None,log_level=None):
        """
        :params         keyword         关键词
         :params         log_level         日志级别         如：I
        """
        # 修改后的正则表达式构建（支持多个关键词用|分隔）
        def _build_pattern(keyword: str):
            parts = [kw.strip() for kw in keyword.split('|') if kw.strip()]
            return re.compile('|'.join(map(re.escape,parts)), re.IGNORECASE) if parts else None
        pattern=_build_pattern(keyword)

        command = ['adb', '-s', self.device, 'logcat', '-v', 'time']
        # 如果日志级别有值
        if log_level:
            command.append(f'*:{log_level}')

        try:
            while True:
                process = None
                try:
                    # Start logcat process
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        encoding='utf-8',  # 指定实际编码
                        errors='replace',  # 自动替换无效字节
                        # universal_newlines=True  # Text mode
                        text=True
                    )

                    # 输出日志流，遇到空中断
                    for line in iter(process.stdout.readline, ''):
                        try:
                            line = line.strip()
                            # 过滤关键词
                            if not pattern or pattern.search(line):
                                self.logcat_queue.append(line)
                                # print(f"捕获日志: {line}")  # 调试用输出
                        except UnicodeDecodeError:
                            continue  # 跳过编码异常行

                    # Process terminated unexpectedly
                    if process.poll() is None:
                        process.terminate()
                        process.wait(2)

                except (subprocess.SubprocessError, OSError) as e:
                    print(f"进程错误: {str(e)}")
                finally:
                    if process:
                        try:
                            if process.poll() is None:
                                print(2)
                                process.terminate()
                                process.wait(2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        except:
                            pass

                print("日志流中断，5秒后重连...")
                time.sleep(5)

        except KeyboardInterrupt:
            print("\n日志采集已安全终止")
        except Exception as e:
            print(f"未处理异常: {str(e)}")
            print(line)
        finally:
            if process:
                process.kill()
            print("日志采集完全停止")

    def output_logcat_old(self, keyword=None,package_name=None,log_level=None):
        """
        :params         keyword         关键词
         :params         log_level         日志级别         如：I
        """
        # 修改后的正则表达式构建（支持多个关键词用|分隔）
        def _build_pattern(keyword: str):
            parts = [kw.strip() for kw in keyword.split('|') if kw.strip()]
            return re.compile('|'.join(map(re.escape,parts)), re.IGNORECASE) if parts else None
        pattern=_build_pattern(keyword)

        command = ['adb', '-s', self.device, 'logcat', '-v', 'time']
        # 如果日志级别有值
        if log_level:
            command.append(f'*:{log_level}')

        try:
            while True:
                process = None
                try:
                    # Start logcat process
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        encoding='utf-8',  # 指定实际编码
                        errors='replace',  # 自动替换无效字节
                        # universal_newlines=True  # Text mode
                        text=True
                    )

                    # 输出日志流，遇到空中断
                    for line in iter(process.stdout.readline, ''):
                        try:
                            line = line.strip()
                            # 过滤关键词
                            if not pattern or pattern.search(line):
                                self.logcat_queue.append(line)
                                # print(f"捕获日志: {line}")  # 调试用输出
                        except UnicodeDecodeError:
                            continue  # 跳过编码异常行

                    # Process terminated unexpectedly
                    if process.poll() is None:
                        print(1)
                        process.terminate()
                        process.wait(2)

                except (subprocess.SubprocessError, OSError) as e:
                    print(f"进程错误: {str(e)}")
                finally:
                    if process:
                        try:
                            if process.poll() is None:
                                print(2)
                                process.terminate()
                                process.wait(2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        except:
                            pass

                print("日志流中断，5秒后重连...")
                time.sleep(5)

        except KeyboardInterrupt:
            print("\n日志采集已安全终止")
        except Exception as e:
            print(f"未处理异常: {str(e)}")
            print(line)
        finally:
            if process:
                process.kill()
            print("日志采集完全停止")


"""

"""


def strat_phone(device):
    """
    启动手机
    :param device: 启动手机设备号
    """
    # 检查手机是否连接
    app_os = AdbBase(device=device)
    # 唤醒屏目
    app_os._screen_awaken()
    # 是否进入应用页面
    if not app_os._in_screen_page():
        raise Exception("手机设有密码，请取消后再执行")


def get_desired_caps(device):
    """
    获取appium desired_caps
    {
      "deviceName": "Xiaomi Redmi Note 7 Pro",
      "platformName": "Android",
      "appPackage": "com.normandyone.booster.cn",
      "platformVersion": "10",
      "automationName": "Appium",
      "autoAcceptAlerts": "True",
      "noReset:true": "True",
      "unicodeKeyboard":"True",
      "resetKeyboard":"True",
      "appActivity": "com.ihs.adsdemo.SplashEnterActivity"
    }
    """
    desired_caps = {}
    app_os = AdbBase(device=device)
    # com.kuaishou.nebula/com.yxcorp.gifshow.HomeActivity
    appPackage, appActivity = app_os.get_package()
    desired_caps["deviceName"] = app_os.get_brand() + " " + app_os.get_model()  # 设备名称
    desired_caps["platformName"] = "Android"  # 设备系统
    desired_caps["appPackage"] = appPackage  # 获取包名
    desired_caps["appActivity"] = appActivity  # 获取activity启动
    desired_caps["platformVersion"] = app_os.get_system_build()  # 获取版本号
    # desired_caps['unicodeKeyboard'] = 'True'  # 支持unicode输入法
    desired_caps["automationName"] = "Appium"  # 引入Appium，用于定位toast
    # desired_caps["automationName"] = "UiAutomator2"  # 引入Appium，用于定位toast  uiautomator2
    desired_caps["autoAcceptAlerts"] = 'true'
    desired_caps["noReset"] = 'true'  # 模拟用户非首次启动 false  true
    desired_caps["newCommandTimeout"] = 50  # 在假定客户端退出并结束会话之前，Appium将等待来自客户端的新命令（以秒为单位）
    desired_caps['settings[waitForIdleTimeout]'] = 100  # 设置进行多久等待继续运行之后的代码，100是1秒
    desired_caps['skipServerInstallation'] = False  # 是否跳过安装appium settings   True-跳过
    desired_caps['skipDeviceInitialization'] = False  # 是否跳过安装io.Appium.uiautomator2.server  True-跳过
    # desired_caps['resetKeyboard'] = 'true'  # 重置键盘
    # desired_caps['app'] = r'E://app-debug.apk'  # 测试app
    logger(f"获取desired_caps内容：【{desired_caps}】", filename="app_auto")
    return desired_caps




if __name__ == '__main__':
    adb_base = AdbBase()
    # print(adb_base.query_cpu_abi())
    # adb_base.clear_app_data("com.block.juggle")       # 方块
    # adb_base.clear_app_data("com.wood.block.sudoku.puzzle.bm")  #木块
    # adb_base.clear_app_data("com.mathbrain.sudoku")     # 数独
    # adb_base.clear_app_data("com.nebula.mahjongtile")  # 麻将
    # adb_base.clear_app_data("com.nebula.offlinegames")  # 星云包体
    # adb_base.clear_app_data("com.wonderful.sandcrush")  # 沙块
    adb_base.clear_app_data("com.hungrystudio.mahjong")  # 方块麻将
    # adb_base.clear_app_data("com.wonderful.mahjong")  # 国风麻将
    # adb_base.clear_app_data("com.nebula.blockpuzzle")  # 3D block


    # adb_base.output_logcat(keyword="klog|hot.rct")

    # 超高
    # adb_base.input_text(content="AURA-BlockBlast-US-S25-Silent-CPP-250121",is_clear_data=True,clear_second=2)
    # 高
    # adb_base.input_text(content="metaweb_int",is_clear_data=True,clear_second=2)
    # 中
    # adb_base.input_text(content="luckygames1_int",is_clear_data=True,clear_second=2)
    # 低
    # adb_base.input_text(content="4G",is_clear_data=True,clear_second=2)
