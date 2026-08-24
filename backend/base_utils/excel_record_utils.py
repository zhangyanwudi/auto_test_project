import pandas as pd


class ExcelRecordUtils():
    DEFAULT_SHEET_NAME = "Sheet"

    def __init__(self):
        self.sheet_map = {}

    def setting_title(self, title_list, sheet_name=None):
        """设置标题"""
        sheet_name = self._get_sheet_name(sheet_name)
        self._setting_sheet_map(sheet_name)
        for title in title_list:
            self.sheet_map[sheet_name].setdefault(title, [])

    def clear_title_data(self, sheet_name=None):
        """清除标题数据"""
        sheet_name = self._get_sheet_name(sheet_name)
        for key in self.sheet_map[sheet_name].keys():
            self.sheet_map[sheet_name][key] = []

    def _setting_sheet_map(self, sheet_name):
        """设置多sheet"""
        if sheet_name not in self.sheet_map.keys():
            self.sheet_map[sheet_name] = {}

    def writer_content(self, sheet_name=None, **kwargs):
        """写入数据"""
        sheet_name = self._get_sheet_name(sheet_name)
        self._setting_sheet_map(sheet_name)
        for key, value in kwargs.items():
            if key in self.sheet_map[sheet_name].keys():
                # 如果值为 None 或空字符串，确保它能被追加
                if value is None or value == "":
                    self.sheet_map[sheet_name][key].append("")  # 追加一个空字符串
                else:
                    self.sheet_map[sheet_name][key].append(value)
            else:
                raise ValueError(f"【{sheet_name}】不存在该【{key}】字段")

    def save_excel(self, file_name, include_empty=False):
        """
        保存多sheet文件
        :params     include_empty     包含空数据     True-包含     False-不包含
        """
        writer = pd.ExcelWriter(file_name, engine='xlsxwriter')
        for key in self.sheet_map.keys():
            df = pd.DataFrame(self.sheet_map[key])
            # 不保存空的sheet的页面数据
            if not include_empty and df.empty:
                continue
            df.to_excel(writer, sheet_name=key, index=False)
        writer.close()

    def query_rows(self, sheet_name=None):
        """统计行数"""
        sheet_name = self._get_sheet_name(sheet_name)
        self._setting_sheet_map(sheet_name)
        df = pd.DataFrame(self.sheet_map[sheet_name])
        return df.shape[0]

    def query_column_nunique(self, colums_name, sheet_name=None):
        """统计指定列不重复数据"""
        sheet_name = self._get_sheet_name(sheet_name)
        self._setting_sheet_map(sheet_name)
        df = pd.DataFrame(self.sheet_map[sheet_name])
        return df[colums_name].nunique()

    def _get_sheet_name(self, sheet_name):
        """获取 sheet_name，若无则返回默认"""
        return sheet_name if sheet_name else self.DEFAULT_SHEET_NAME

    def get_map_data(self, sheet_name=None):
        """获取数据"""
        sheet_name = self._get_sheet_name(sheet_name)
        return self.sheet_map[sheet_name]


if __name__ == '__main__':
    excel_record = ExcelRecordUtils()
    excel_record.setting_title(title_list=["账户", "广告id", "素材id"])
    print(excel_record.query_column_nunique(colums_name="素材id"))
    # excel.save_excel(file_name="测试一下.xlsx")
