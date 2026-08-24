#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热更测试 - AB 实验需求文档解析器

解析 AB 实验 Excel 需求文档，提取方案号用于配置比对。

Excel 文档结构（第 3 行为表头，第 4 行起为数据）：
  A列: 原始方案编号    → 右侧方案号（新方案）
  B列: 广告类型        → 激励/插屏 等
  C列: 方案概述        → 包含底板方案号（如 【底板】rv176685）
  D列: abtest         → AB 测试标识
  E列: 技术           → 技术说明
  F列: 方案细节        → 详细变更描述

解析规则：
  1. 右侧方案号 = A列「原始方案编号」
  2. 左侧方案号 = C列「方案概述」中提取的底板方案号：
     - 优先匹配 「【底板】」 后的 rv/fs 号
     - 其次匹配 「基于」 后的第一个 rv/fs 号
     - 兜底取 C 列中第一个 rv/fs 号
  3. 方案概述文本 = C列 + F列 合并（供人工参考修改范围）

用法：
  python3 scripts/parse_hot_update_file.py "文档路径" [行号]

示例：
  python3 scripts/parse_hot_update_file.py "AB实验第217期RV-策略平台热更.xlsx" 4
"""

import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 方案号正则：rv 或 fs 开头 + 纯数字
# 使用 lookbehind/lookahead 替代 \b，因为 Python3 Unicode 模式下 \b 与中文边界不匹配
SCHEME_PATTERN = re.compile(r'(?<![a-zA-Z])([rf][sv])(\d+)(?![a-zA-Z0-9])')

# 底板方案号提取规则（优先级从高到低）
BASE_SCHEME_RULES = [
    # 规则1：【底板】后面的方案号
    re.compile(r'【底板】[^\n]*?(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])'),
    # 规则2：「底板」后面的方案号
    re.compile(r'[（(]?底板[）)]?[^\n]*?(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])'),
    # 规则3：基于xxx（第一个 rv/fs 方案号）
    re.compile(r'基于[^\n]*?(?<![a-zA-Z])([rf][sv]\d+)(?![a-zA-Z0-9])'),
]

# 中文项目名称 → 内部标识的映射
PROJECT_NAME_ALIASES = {
    'gp_blockblast': 'GP方块',
    'gp_blockblast_rn': 'GP方块-rn',
    'gp_blockblast_orth': 'GP方块-AB',
    'gp_blockblast_ml': 'GP方块-互斥',
    'gp_taptile': 'GP-taptile',
    'gp_taptile_orth': 'GP-taptile-AB',
    'gp_mahjongblast': 'GP方块麻将',
    'gp_mahjongblast_orth': 'GP方块麻将-AB',
    'gp_mahjong_3he': 'GP国风麻将',
    'gp_sudoku': 'GP数独',
    'gp_mahjong': 'GP麻将',
    'gp_mahjong_rn': 'GP麻将-rn',
    'gp_mahjong_orth': 'GP麻将-AB',
    'gp_blockcrush': 'GP木块',
    'gp_blockcrush_rn': 'GP木块-rn',
    'gp_blockcrush_orth': 'GP木块-AB',
    'gp_blockcrush_me': 'GP木块-ME',
    'gp_blocknova': 'GPnova',
    'gp_sandcursh': 'GP沙块',
    'ios_blcokblast': 'IOS方块',
    'ios_blcokblast_ab3.5_orth': 'IOS方块-AB3.5',
    'ios_mahjong_3he': 'IOS国风麻将',
    'ios_blockcrush': 'IOS木块',
    'ios_mahjong': 'IOS麻将',
    'ios_sandcrush': 'IOS沙块',
    'ios_sudoku': 'IOS数独',
}

# 反向映射：中文名 → 内部标识
CN_TO_INTERNAL = {v: k for k, v in PROJECT_NAME_ALIASES.items()}


def resolve_project_name(name: str) -> str:
    """解析项目名，支持中文别名和内部标识。"""
    name = name.strip()
    if name in PROJECT_NAME_ALIASES:
        return name
    if name in CN_TO_INTERNAL:
        return CN_TO_INTERNAL[name]
    name_lower = name.lower()
    for internal, cn_name in PROJECT_NAME_ALIASES.items():
        if name_lower == cn_name.lower() or name_lower == internal.lower():
            return internal
    return name


def extract_scheme_numbers(text: str) -> List[str]:
    """
    从文本中提取所有 rv/fs 方案号。

    参数:
        text — 方案概述文本

    返回:
        list[str] — 方案号列表（如 ['rv176685', 'rv159610']），去重保持顺序
    """
    if not text:
        return []
    seen = set()
    result = []
    for match in SCHEME_PATTERN.finditer(text):
        scheme = match.group(0)
        if scheme not in seen:
            seen.add(scheme)
            result.append(scheme)
    return result


def extract_base_scheme(text: str) -> Optional[str]:
    """
    从方案概述文本中提取底板方案号。

    优先级：
    1. 【底板】rvxxxxx
    2. 「底板」rvxxxxx
    3. 基于rvxxxxx（第一个 rv/fs 方案号）
    4. 文本中第一个 rv/fs 方案号

    返回:
        str | None — 底板方案号
    """
    if not text:
        return None

    for rule in BASE_SCHEME_RULES:
        match = rule.search(text)
        if match:
            return match.group(1)

    # 兜底：取第一个 rv/fs 方案号
    all_schemes = extract_scheme_numbers(text)
    return all_schemes[0] if all_schemes else None


def parse_ab_excel(
    file_path: str,
    row_number: int = 4,
    sheet_name: str = 'All',
) -> Dict[str, Any]:
    """
    解析 AB 实验需求 Excel 文档。

    参数:
        file_path — Excel 文件路径
        row_number — 要解析的数据行号（1-based，默认第 4 行）
        sheet_name — Sheet 名称（默认 'All'）

    返回:
        dict — {
            "right_scheme": "rv217601",       # 原始方案编号（新方案）
            "left_scheme": "rv176685",        # 底板方案号
            "all_schemes_in_overview": [...], # 方案概述中所有方案号
            "ad_type": "激励",                 # 广告类型
            "overview_text": "...",           # 方案概述全文
            "detail_text": "...",             # 方案细节全文
            "row_number": 4,
            "source_file": "xxx.xlsx",
        }

    异常:
        FileNotFoundError — 文件不存在
        ValueError — 行号超出范围或格式不正确
    """
    import openpyxl

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    _, ext = os.path.splitext(file_path)
    if ext.lower() not in ('.xlsx', '.xls'):
        raise ValueError(f"不支持的文件格式: {ext}，仅支持 .xlsx / .xls")

    wb = openpyxl.load_workbook(file_path, data_only=True)

    # 选择 sheet
    if sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        ws = wb.active
        sheet_name = ws.title

    # 读取指定行（1-based → 0-based）
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    row_idx = row_number - 1  # 转为 0-based
    if row_idx < 0 or row_idx >= len(rows):
        raise ValueError(
            f"行号 {row_number} 超出范围（有效范围: 1-{len(rows)}），"
            f"Sheet: {sheet_name}"
        )

    row = rows[row_idx]

    # 检测表头行（第 3 行通常是表头）
    header_row_idx = 2  # 0-based，第 3 行
    headers = list(rows[header_row_idx]) if header_row_idx < len(rows) else []

    # 列映射（根据表头自动检测，或使用默认位置）
    col_map = _build_column_map(headers)

    # 提取各列数据
    raw_scheme = _safe_str(row[col_map.get('原始方案编号', 0)]) if len(row) > col_map.get('原始方案编号', 0) else ''
    ad_type = _safe_str(row[col_map.get('广告类型', 1)]) if len(row) > col_map.get('广告类型', 1) else ''
    overview_text = _safe_str(row[col_map.get('方案概述', 2)]) if len(row) > col_map.get('方案概述', 2) else ''
    detail_text = _safe_str(row[col_map.get('方案细节', 5)]) if len(row) > col_map.get('方案细节', 5) else ''
    abtest = _safe_str(row[col_map.get('abtest', 3)]) if len(row) > col_map.get('abtest', 3) else ''

    # 提取方案号
    right_scheme = raw_scheme.strip()  # 原始方案编号 → 右侧

    # 从方案概述中提取底板方案号
    left_scheme = extract_base_scheme(overview_text)

    # ��案概述中的所有方案号
    all_schemes = extract_scheme_numbers(overview_text)

    result = {
        "right_scheme": right_scheme,
        "left_scheme": left_scheme or '',
        "all_schemes_in_overview": all_schemes,
        "ad_type": ad_type,
        "overview_text": overview_text,
        "detail_text": detail_text,
        "abtest": abtest,
        "row_number": row_number,
        "sheet_name": sheet_name,
        "source_file": os.path.basename(file_path),
    }

    return result


def _build_column_map(headers: list) -> Dict[str, int]:
    """
    根据表头行构建列名→列索引的映射。

    表头可能包含这些列名：原始方案编号, 广告类型, 方案概述,
    abtest, 技术, 方案细节, 状态, 发起人, 备注, 上线地区, 数据依据
    """
    col_map = {}
    for i, h in enumerate(headers):
        h_clean = _safe_str(h).strip().replace('\n', '').replace(' ', '')
        if '原始方案编号' in h_clean:
            col_map['原始方案编号'] = i
        elif '广告类型' in h_clean:
            col_map['广告类型'] = i
        elif '方案概述' in h_clean:
            col_map['方案概述'] = i
        elif 'abtest' in h_clean.lower():
            col_map['abtest'] = i
        elif '技术' in h_clean:
            col_map['技术'] = i
        elif '方案细节' in h_clean:
            col_map['方案细节'] = i
        elif '状态' in h_clean:
            col_map['状态'] = i
        elif '发起人' in h_clean:
            col_map['发起人'] = i
        elif '备注' in h_clean:
            col_map['备注'] = i
    return col_map


def _safe_str(val: Any) -> str:
    """安全转换为字符串。"""
    if val is None:
        return ''
    return str(val)


# ============================================================
# 命令行入口
# ============================================================
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 parse_hot_update_file.py <Excel文件路径> [行号] [Sheet名]")
        print("示例: python3 parse_hot_update_file.py 'AB实验第217期RV-策略平台热更.xlsx' 4")
        sys.exit(1)

    file_path = sys.argv[1]
    row_num = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    sheet = sys.argv[3] if len(sys.argv) > 3 else 'All'

    try:
        result = parse_ab_excel(file_path, row_number=row_num, sheet_name=sheet)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
