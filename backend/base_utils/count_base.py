class NumberCounter:
    """统计数字出现次数的类"""

    def __init__(self):
        self.counts = {}

    def count(self, num):
        """
        统计入参数字出现的次数
        每次调用会将该数字的计数+1，并返回当前累计次数
        """
        if num in self.counts:
            self.counts[num] += 1
        else:
            self.counts[num] = 1

        return self.counts[num]

    def get_all_counts(self):
        """获取所有数字的统计结果"""
        return dict(sorted(self.counts.items()))

    def reset(self):
        """重置计数器"""
        self.counts = {}
