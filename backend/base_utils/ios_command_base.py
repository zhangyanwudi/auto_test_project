import re,subprocess

import cv2
import numpy as np
import subprocess,copy
from PIL import Image
import pygetwindow as gw
import time
from base_utils.bracket_matcher_base import BracketMatcherUtils

class IosCommandBase():
    def __init__(self):
        # 初始化拼接
        self.bracket=BracketMatcherUtils()
        # ios日志列表
        self.ios_log_queue=[]


    def output_log(self,keyword=None,is_HS_data=False):
        # 修改后的正则表达式构建（支持多个关键词用|分隔）
        if keyword:
            # 分割关键词并过滤空值
            keywords = [kw.strip() for kw in keyword.split('|') if kw.strip()]
            if keywords:
                regex_str = '|'.join(map(re.escape, keywords))  # 转义每个关键词
                pattern = re.compile(regex_str)
            else:
                pattern = None
        else:
            pattern = None

        # 初始化拼接状态
        splice_log_status=False

        while True:
            process = None
            try:
                process = subprocess.Popen(
                    ['idevicesyslog'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )

                # 输出日志流，遇到空中断
                for line in iter(process.stdout.readline, ''):
                    try:
                        line = line.strip()
                        # 过滤埋点数据
                        if not is_HS_data:
                            if "BCThinkingManager trackName:trackProperties:" in line:
                                continue
                        # 判断不在拼接状态中且不在关键词中的跳过
                        if not splice_log_status and not pattern.search(line):
                            continue
                        # 判断在拼接状态中且包含关键词的
                        if splice_log_status and pattern.search(line):
                            # 中断拼接状态
                            splice_log_status = False
                            # print(self.bracket.buffer)
                            self.ios_log_queue.append(self.bracket.buffer)
                            self.bracket.clear_data()
                            continue

                        line_result=self.bracket.process_line(line)

                        if line_result:
                            splice_log_status = False
                            # print(f"捕获日志: {line_result}")  # 调试用输出
                            self.ios_log_queue.append(line_result)
                        else:
                            splice_log_status=True
                    except UnicodeDecodeError:
                        continue  # 跳过编码异常行

                # Process terminated unexpectedly
                if process.poll() is None:
                    process.terminate()
                    process.wait(2)

            except KeyboardInterrupt:
                print("\n停止日志捕获...")
                process.terminate()
            except Exception as e:
                print(f"错误发生: {str(e)}")
                process.terminate()

    def check_ios_connected(self):
        """
        检查是否连接iOS设置
        :return:   True-有连接    False-无连接
        """
        result = subprocess.run(['idevice_id', '-l'], capture_output=True, text=True)
        return len(result.stdout.strip()) > 0



if __name__ == '__main__':
    ios_command=IosCommandBase()
    ios_command.output_log("NORMAL")
