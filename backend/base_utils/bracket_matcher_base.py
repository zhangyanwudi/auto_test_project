class BracketMatcherUtils:
    def __init__(self,max_splice_num=100):
        """
        :param max_splice_num:  用于控制最大拼接次数，默认100
        """
        self.buffer = ""      # 用于存放内容拼接
        self.stack = []       # 用于存放匹配
        self.splice_num = 0     # 当前拼接次数
        self.is_bracket_status=False   # 是否在拼接中状态，True 正在拼接中，False 不在拼接中
        self.max_splice_num=max_splice_num

    def is_balanced(self, s):
        """检查是否完整"""
        # 存放配置值
        stack=[]
        pairs = {'(': ')', '[': ']', '{': '}'}
        for char in s:
            if char in pairs:
                stack.append(char)
            elif char in pairs.values():
                stack.pop()
        if not stack:
            return True
        return False

    def clear_data(self):
        """清除数据"""
        self.buffer = ""
        self.splice_num = 0
        self.is_bracket_status=False

    def process_line(self, line):
        """
        拼接内容处理
        :param line:        内容
        :return:
        """
        self.buffer += line
        self.splice_num += 1

        if self.splice_num > self.max_splice_num:
            # 拼接次数超过限制，重置数据
            self.clear_data()
            return False

        if self.is_balanced(self.buffer):
            # 数据平衡，返回并重置缓冲区
            result = self.buffer
            self.clear_data()
            return result
        return False

    def setting_max_split_num(self,max_split_num):
        """设置最大拼接次数"""
        self.max_splice_num=max_split_num

    def split_num_content(self,split_content):
        """按次数拼接内容"""
        # 初始化数据
        self.is_bracket_status=True
        self.buffer += split_content
        self.splice_num += 1
        if self.splice_num > self.max_splice_num:
            # 达到指定次数，返回数据
            result = self.buffer
            self.clear_data()
            return result
        return False


if __name__ == '__main__':
    brate=BracketMatcherUtils()
    brate.setting_max_split_num(2)
    contents=["1","3","5","6"]
    for content in contents:
        result=brate.split_num_content(content)
        if result:
            print(result)