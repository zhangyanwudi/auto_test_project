#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys


def supports_terminal_hyperlinks(stream=None):
    """当前输出流是否为交互式终端（可安全输出 OSC 8 链接）。"""
    stream = stream or sys.stdout
    return getattr(stream, 'isatty', lambda: False)()


def terminal_hyperlink(url, label=None, *, stream=None):
    """
    生成终端可点击超链接（OSC 8）。
    不支持时退回纯文本，避免乱码。
    """
    text = label if label is not None else url
    if not supports_terminal_hyperlinks(stream):
        return text
    safe_url = url.replace('\\', '\\\\')
    return f'\033]8;;{safe_url}\033\\{text}\033]8;;\033\\'
