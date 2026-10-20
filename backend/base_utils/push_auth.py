#!/usr/bin/env python3
"""
push_auth.py — 向浏览器「推送」（写入）指定域名、指定 key 的缓存内容。

与 get_auth.py 对称：get_auth 负责「读」，本脚本负责「写」。
支持修改浏览器里的三类「缓存」内容（用 --type 指定）:

  cookie          — 写入 / 覆盖 Cookie（key = Cookie 名称）            [默认]
  localStorage    — 写入 / 覆盖 localStorage 中的 key
  sessionStorage  — 写入 / 覆盖 sessionStorage 中的 key（仅当前标签页可见）

写入方式:
  1. AppleScript 执行 JS — localStorage / sessionStorage 的默认方式 [免重启、免调试端口]
     前提：浏览器开启「查看 > 开发者 > 允许 Apple 事件中的 JavaScript」
  2. CDP (Chrome DevTools Protocol) — 通过 Chrome 远程调试端口实时写入（Cookie 默认 / storage 可用 via_cdp）
       - Cookie         → Network.setCookie
       - localStorage   → Runtime.evaluate(localStorage.setItem)
       - sessionStorage → Runtime.evaluate(sessionStorage.setItem)
  3. Chrome Cookie DB — 直接写 Chrome 本地 Cookie 数据库（仅支持 cookie）
     注意：需要先「完全退出浏览器」，写入后重新打开才生效。

── CLI 用法 ──────────────────────────────────────────────
  python3 push_auth.py -k userToken -v NEW_VALUE                 # 写默认域名的 userToken Cookie
  python3 push_auth.py -d other.example.com -k sessionId -v xxx  # 指定域名
  python3 push_auth.py -k accessToken -v NEW_VALUE --type localStorage
  python3 push_auth.py -k userToken -v NEW_VALUE --type cookie --secure --http-only
  python3 push_auth.py -k userToken --value-file token.txt       # 从文件读取 value
  echo "NEW_VALUE" | python3 push_auth.py -k userToken           # 从 stdin 读取 value
  python3 push_auth.py -k userToken -v NEW_VALUE --db            # 直接写 Cookie DB（需先退出 Chrome）

── 模块引入用法 ──────────────────────────────────────────
  from push_auth import push_value, set_cookie, set_local_storage

  push_value("abtest.youxi123.com", "userToken", "NEW_VALUE")
  set_cookie("abtest.youxi123.com", "userToken", "NEW_VALUE")
  set_local_storage("abtest.youxi123.com", "accessToken", "NEW_VALUE")

依赖:
  pycryptodome    # 仅 --db 直接写 Cookie DB 时需要（加密 Cookie 值）
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import shutil
import tempfile
import http.client
import urllib.parse
from typing import Optional

# ── 可选依赖：pycryptodome（仅 --db 写 Cookie DB 时需要）──
try:
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Hash import SHA1
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

try:
    from urllib.request import urlopen
    from urllib.error import URLError
except ImportError:
    from urllib2 import urlopen, URLError  # Python 2 兼容


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

DEFAULT_DOMAIN = "abtest.youxi123.com"

# 浏览器在 AppleScript 中的应用名（用于「执行 JS」写入 storage）
# 改为 Google Chrome 后生效；若要切回 GptBrowser，改成 "GPT Chrome"
BROWSER_APP_NAME = "Google Chrome"

CHROME_CDP_PORT = 9222

# Chrome / Chromium Cookie 数据库路径（与 get_auth.py 保持一致）
CHROME_COOKIE_PATHS = [
    os.path.expanduser("~/Library/Application Support/GptBrowser/Default/Cookies"),
    os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Cookies"),
    os.path.expanduser("~/Library/Application Support/Google/Chrome/Profile */Cookies"),
    os.path.expanduser("~/Library/Application Support/Chromium/Default/Cookies"),
]

# 支持的缓存类型
CACHE_TYPES = ("cookie", "localStorage", "sessionStorage")

# 公开 API —— 供 `from push_auth import ...` 引入调用
__all__ = [
    "set_auth",
    "push_values",
    "push_value",
    "set_cookie",
    "set_local_storage",
    "set_session_storage",
    "set_local_storage_applescript",
    "set_session_storage_applescript",
]


# ═══════════════════════════════════════════════════════════════
# 公开 API — 可直接通过 from push_auth import ... 引入使用
# ═══════════════════════════════════════════════════════════════

def push_value(
    domain: str = DEFAULT_DOMAIN,
    key: str = "userToken",
    value: str = "",
    *,
    cache_type: str = "cookie",
    path: str = "/",
    secure: bool = False,
    http_only: bool = False,
    via_db: bool = False,
    via_cdp: bool = False,
    via_applescript: bool = False,
) -> bool:
    """把 value 写入指定域名的指定 key。

    参数:
        domain:     目标域名，默认 "abtest.youxi123.com"
        key:        要写入的 key（Cookie 名称 / localStorage key / sessionStorage key）
        value:      要写入的新值
        cache_type: 缓存类型，cookie / localStorage / sessionStorage，默认 cookie
        path:       仅 cookie 有效，Cookie 路径，默认 "/"
        secure:     仅 cookie 有效，是否 Secure
        http_only:  仅 cookie 有效，是否 HttpOnly
        via_db:     是否直接写浏览器 Cookie DB（仅 cookie 有效，需先退出浏览器）
        via_cdp:    强制走 CDP（storage 默认走 AppleScript，设 True 则用 CDP）
        via_applescript: 强制走 AppleScript（storage 专用；cookie 不支持）

    返回:
        写入是否成功（True/False）。
    """
    key = _normalize_key(key)

    if cache_type == "cookie":
        if via_db:
            return _set_cookie_via_db(domain, key, value, path=path)
        return _set_cookie_via_cdp(domain, key, value,
                                   path=path, secure=secure, http_only=http_only)

    if cache_type == "localStorage":
        if via_cdp:
            return _set_storage_via_cdp(domain, key, value, session=False)
        return _set_storage_applescript(domain, key, value, session=False)

    if cache_type == "sessionStorage":
        if via_cdp:
            return _set_storage_via_cdp(domain, key, value, session=True)
        return _set_storage_applescript(domain, key, value, session=True)

    print(f"[!] 不支持的缓存类型: {cache_type}（可选: {', '.join(CACHE_TYPES)}）", file=sys.stderr)
    return False


def set_auth(
    domain: str = DEFAULT_DOMAIN,
    values: Optional[dict] = None,
    *,
    cache_type: str = "cookie",
    **kwargs,
) -> dict:
    """一次调用设置同一域名下的多个 key / 多个值。

    参数:
        domain:     目标域名，默认 "abtest.youxi123.com"
        values:     要写入的 key → value 字典，如 {"userToken": "xxx", "sessionId": "yyy"}
        cache_type: 缓存类型，cookie / localStorage / sessionStorage，默认 cookie
        **kwargs:   透传给底层写入（path / secure / http_only / via_db 等）

    返回:
        {"<key>": True/False, ...}，key 顺序与 values 一致；values 为空返回 {}。

    示例:
        # 一次设置多个 Cookie
        set_auth("abtest.youxi123.com", {"userToken": "T1", "sessionId": "S1"})

        # 一次设置多个 localStorage
        set_auth("abtest.youxi123.com",
                 {"accessToken": "A1", "refreshToken": "R1"},
                 cache_type="localStorage")
    """
    values = values or {}
    return {
        key: push_value(domain, key, _coerce_value(value), cache_type=cache_type, **kwargs)
        for key, value in values.items()
    }


def push_values(
    domain: str = DEFAULT_DOMAIN,
    values: Optional[dict] = None,
    *,
    cache_type: str = "cookie",
    **kwargs,
) -> dict:
    """批量写入同域名下的多个 key / 多个值，是 set_auth 的别名（返回各 key 结果）。

    与 set_auth 完全等价，保留以贴合 get_auth 中 get_token / get_tokens 的命名习惯。
    """
    return set_auth(domain, values, cache_type=cache_type, **kwargs)


def set_cookie(
    domain: str = DEFAULT_DOMAIN,
    name: str = "userToken",
    value: str = "",
    *,
    path: str = "/",
    secure: bool = False,
    http_only: bool = False,
    via_db: bool = False,
) -> bool:
    """写入 / 覆盖指定域名的一个 Cookie。push_value 的 cookie 快捷方式。"""
    return push_value(domain, name, value, cache_type="cookie",
                      path=path, secure=secure, http_only=http_only, via_db=via_db)


def set_local_storage(
    domain: str = DEFAULT_DOMAIN,
    key: str = "",
    value: str = "",
    *,
    via_cdp: bool = False,
    via_applescript: bool = False,
) -> bool:
    """写入 / 覆盖指定域名 localStorage 中的一个 key。

    默认走 AppleScript（免重启、免调试端口）；设 via_cdp=True 走 CDP。
    """
    return push_value(domain, key, value, cache_type="localStorage",
                      via_cdp=via_cdp, via_applescript=via_applescript)


def set_session_storage(
    domain: str = DEFAULT_DOMAIN,
    key: str = "",
    value: str = "",
    *,
    via_cdp: bool = False,
    via_applescript: bool = False,
) -> bool:
    """写入 / 覆盖指定域名 sessionStorage 中的一个 key。

    默认走 AppleScript（免重启、免调试端口）；设 via_cdp=True 走 CDP。
    """
    return push_value(domain, key, value, cache_type="sessionStorage",
                      via_cdp=via_cdp, via_applescript=via_applescript)


def set_local_storage_applescript(
    domain: str = DEFAULT_DOMAIN,
    key: str = "",
    value: str = "",
) -> bool:
    """通过 AppleScript 执行 JS 写入 localStorage（免重启、免调试端口）。"""
    return _set_storage_applescript(domain, key, value, session=False)


def set_session_storage_applescript(
    domain: str = DEFAULT_DOMAIN,
    key: str = "",
    value: str = "",
) -> bool:
    """通过 AppleScript 执行 JS 写入 sessionStorage（免重启、免调试端口）。"""
    return _set_storage_applescript(domain, key, value, session=True)


# ═══════════════════════════════════════════════════════════════
# 内部实现: key 归一化
# ═══════════════════════════════════════════════════════════════

def _normalize_key(key: str) -> str:
    """归一化 key：兼容 get_auth.py 的 "authorization:" 写法。

    "authorization:" → "authorization"，方便对称使用。
    """
    if key.endswith(":"):
        return key[:-1]
    return key


def _coerce_value(value) -> str:
    """把写入值统一转成字符串。

    - dict / list / bool / None → json.dumps（产生双引号 JSON，避免 AppleScript 单引号转义灾难）
    - 其他类型 → str(value)

    注意：不能用 str(dict)，因为它产生单引号的 Python 字面量，
    含单引号，AppleScript 字符串无法正确转义，会导致写入失败。
    """
    if isinstance(value, (dict, list, tuple, bool)) or value is None:
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        return value
    return str(value)


# ═══════════════════════════════════════════════════════════════
# 内部实现: CDP — Cookie 写入
# ═══════════════════════════════════════════════════════════════

def _cdp_list_pages() -> list[dict]:
    """获取 Chrome 远程调试的页面列表。"""
    try:
        resp = urlopen(f"http://127.0.0.1:{CHROME_CDP_PORT}/json", timeout=3)
        return json.loads(resp.read())
    except Exception:
        return []


def _cdp_send(page_id: str, method: str, params: Optional[dict] = None) -> dict:
    """向指定 page 发送 CDP 命令（HTTP 短连接方式，命令为同步请求）。"""
    payload = json.dumps({"id": 1, "method": method, "params": params or {}})
    conn = http.client.HTTPConnection("127.0.0.1", CHROME_CDP_PORT, timeout=5)
    conn.request("POST", f"/devtools/page/{page_id}", payload,
                 {"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return data


def _cdp_any_page_id() -> Optional[str]:
    """返回任意一个 page target 的 id（用于发送 CDP 命令）。"""
    for p in _cdp_list_pages():
        if p.get("type") == "page" and p.get("id"):
            return p["id"]
    return None


def _cdp_find_page_id(domain: str) -> Optional[str]:
    """优先返回 url 中含目标域名的 page id；找不到则返回任意 page id。"""
    pages = _cdp_list_pages()
    for p in pages:
        if p.get("type") == "page" and p.get("id") and domain in (p.get("url", "")):
            return p["id"]
    for p in pages:
        if p.get("type") == "page" and p.get("id"):
            return p["id"]
    return None


def _set_cookie_via_cdp(domain: str, name: str, value: str,
                        *, path: str = "/", secure: bool = False,
                        http_only: bool = False) -> bool:
    """通过 CDP Network.setCookie 写入 Cookie。"""
    page_id = _cdp_any_page_id()
    if page_id is None:
        print(f"[!] 未检测到 Chrome 远程调试端口 {CHROME_CDP_PORT}", file=sys.stderr)
        print(f"[!] 请用以下方式启动 Chrome:", file=sys.stderr)
        print(f"    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome "
              f"--remote-debugging-port={CHROME_CDP_PORT}", file=sys.stderr)
        return False

    params = {
        "name": name,
        "value": value,
        "url": f"https://{domain}{path if path.startswith('/') else '/' + path}",
        "path": path,
        "secure": secure,
        "httpOnly": http_only,
    }
    data = _cdp_send(page_id, "Network.setCookie", params)
    result = data.get("result", {})
    ok = bool(result.get("success", False))

    if ok:
        print(f"[+] Cookie 已写入: {name} @ {domain}{path}")
    else:
        print(f"[!] Cookie 写入失败: {data}", file=sys.stderr)
    return ok


def _get_cookie_via_cdp(domain: str, name: str) -> Optional[str]:
    """通过 CDP 读回指定 Cookie，用于写入后验证。"""
    page_id = _cdp_any_page_id()
    if page_id is None:
        return None
    data = _cdp_send(page_id, "Network.getCookies")
    cookies = data.get("result", {}).get("cookies", [])
    for c in cookies:
        if domain in c.get("domain", "") and c.get("name") == name:
            return c.get("value", "")
    return None


# ═══════════════════════════════════════════════════════════════
# 内部实现: CDP — localStorage / sessionStorage 写入
# ═══════════════════════════════════════════════════════════════

def _cdp_new_tab(url: str) -> Optional[dict]:
    """通过 /json/new 端点创建新标签页（新版 Chrome 需 PUT）。"""
    quoted = urllib.parse.quote(url, safe=":/")
    for method in ("PUT", "GET"):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", CHROME_CDP_PORT, timeout=5)
            conn.request(method, f"/json/new?{quoted}")
            resp = conn.getresponse()
            body = resp.read().decode()
            conn.close()
            if resp.status == 200:
                return json.loads(body)
        except Exception:
            continue
    return None


def _set_storage_via_cdp(domain: str, key: str, value: str, *, session: bool = False) -> bool:
    """通过 CDP 在目标域名页面上执行 JS 写入 localStorage / sessionStorage。

    说明:
      - localStorage 写入需要该 origin 已有打开的页面（否则无法定位 origin）。
        找不到时尝试自动新开一个标签页打开目标域名，再执行写入。
      - sessionStorage 是「标签页级」的，写入后仅在该标签页内有效。
    """
    storage_kind = "sessionStorage" if session else "localStorage"

    # 1. 优先找已打开目标域名的 page
    page_id = _cdp_find_page_id(domain)
    if page_id is None:
        print(f"[!] 未检测到 Chrome 远程调试端口 {CHROME_CDP_PORT}", file=sys.stderr)
        print(f"[!] 请以 --remote-debugging-port={CHROME_CDP_PORT} 启动 Chrome", file=sys.stderr)
        return False

    # 确认该 page 是否真的在目标 origin 上；不在则尝试新开标签页
    target_url = f"https://{domain}/"
    pages = _cdp_list_pages()
    page_on_domain = any(
        p.get("id") == page_id and domain in (p.get("url", ""))
        for p in pages
    )
    if not page_on_domain:
        print(f"[*] 未找到已打开 {domain} 的标签页，尝试自动新开...")
        new_tab = _cdp_new_tab(target_url)
        if new_tab and new_tab.get("id"):
            page_id = new_tab["id"]
            print(f"[*] 已新开标签页，等待页面加载...")
            import time
            time.sleep(2)
        else:
            print(f"[!] 无法打开目标域名 {domain}，请先手动在浏览器中打开该网站后再试",
                  file=sys.stderr)
            return False

    # 2. 在目标 page 上执行 JS 写入并读回验证
    expr = (
        f"{storage_kind}.setItem({json.dumps(key)}, {json.dumps(value)}); "
        f"{storage_kind}.getItem({json.dumps(key)})"
    )
    data = _cdp_send(page_id, "Runtime.evaluate",
                     {"expression": expr, "returnByValue": True, "awaitPromise": True})

    result = data.get("result", {})
    if result.get("exceptionDetails"):
        err = result["exceptionDetails"].get("text", "")
        print(f"[!] {storage_kind} 写入出错: {err}", file=sys.stderr)
        return False

    written = result.get("result", {}).get("value")
    if written == value:
        print(f"[+] {storage_kind} 已写入: {key} @ {domain}")
        return True

    print(f"[!] {storage_kind} 写入未生效（读回值: {written!r}）", file=sys.stderr)
    return False


# ═══════════════════════════════════════════════════════════════
# 内部实现: AppleScript — localStorage / sessionStorage 写入（免重启）
# ═══════════════════════════════════════════════════════════════

def _applescript_run(script: str) -> str:
    """执行一段 AppleScript，返回 stdout（失败时返回空串）。"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace").strip()
        return ""
    except Exception:
        return ""


def _applescript_js(js: str, *, activate: bool = False) -> str:
    """通过 AppleScript 在浏览器激活标签页执行 JS，返回执行结果字符串。

    JS 将被嵌入 AppleScript 的双引号字符串（javascript "..."）中，
    因此 JS 里的反斜杠、双引号、单引号都需要转义，顺序不可调换：
      1) 反斜杠 → 双反斜杠
      2) 双引号 → \\"   3) 单引号 → \\'
    """
    safe = js.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
    lines = [
        f'tell application "{BROWSER_APP_NAME}"',
    ]
    if activate:
        lines.append("activate")
    lines += [
        f"execute active tab of front window javascript \"{safe}\"",
        "end tell",
    ]
    return _applescript_run("\n".join(lines))


def _applescript_get_tab_url() -> str:
    """获取当前激活标签页的 URL。"""
    script = (
        f'tell application "{BROWSER_APP_NAME}" '
        f'to get URL of active tab of front window'
    )
    return _applescript_run(script)


def _set_storage_applescript(domain: str, key: str, value: str, *, session: bool = False) -> bool:
    """通过 AppleScript 执行 JS 写入 localStorage / sessionStorage。

    工作流:
      1. 检查当前激活标签页是否在目标域名（origin）上；
         不在则遍历窗口标签，激活第一个匹配目标域名的标签页。
      2. 在该标签页执行 setItem 并读回验证。
      3. 若未找到目标域名标签页，返回 False（并提示需手动打开目标域名页面）。

    注意: 需要浏览器已开启「查看 > 开发者 > 允许 Apple 事件中的 JavaScript」。
    """
    storage_kind = "sessionStorage" if session else "localStorage"

    # 1. 当前激活标签页是否在目标域名上？
    current_url = _applescript_get_tab_url()
    if domain not in current_url:
        # 2. 遍历所有标签页，找到目标域名的标签页并激活
        found = _applescript_activate_tab(domain)
        if not found:
            print(f"[!] 未找到已打开 {domain} 的标签页，请先在浏览器中打开该网站后重试",
                  file=sys.stderr)
            return False

    # 3. 执行写入 + 读回验证
    expr = (
        f"{storage_kind}.setItem({json.dumps(key)}, {json.dumps(value)}); "
        f"{storage_kind}.getItem({json.dumps(key)})"
    )
    written = _applescript_js(expr)

    if written == value:
        print(f"[+] {storage_kind} 已写入: {key} @ {domain}（AppleScript）")
        return True

    if written == "missing value":
        print(f"[!] AppleScript 执行未返回结果，请确认已开启「允许 Apple 事件中的 JavaScript」",
              file=sys.stderr)
        return False

    print(f"[!] {storage_kind} 写入未生效（读回值: {written!r}）", file=sys.stderr)
    return False


def _applescript_activate_tab(domain: str) -> bool:
    """遍历浏览器所有窗口的所有标签页，激活第一个 URL 含 domain 的标签页。

    返回是否找到并激活。

    注意：AppleScript 里 `repeat with t in tabs of w` 得到的是引用，
    不能直接 `index of t` / `URL of t` 取值（会报 -10006），
    必须用 `tab i of w` 这种按下标索引的写法。
    """
    script = (
        f'tell application "{BROWSER_APP_NAME}"\n'
        "set found to false\n"
        "repeat with w in windows\n"
        "  set tabCount to count of tabs of w\n"
        "  repeat with i from 1 to tabCount\n"
        "    set t to tab i of w\n"
        f'    if "{domain}" is in (URL of t) then\n'
        "      set active tab index of w to i\n"
        "      set index of w to 1\n"
        "      set found to true\n"
        "      exit repeat\n"
        "    end if\n"
        "  end repeat\n"
        "  if found then exit repeat\n"
        "end repeat\n"
        'if found then\n'
        '  return "found"\n'
        'else\n'
        '  return "notfound"\n'
        'end if\n'
        "end tell"
    )
    result = _applescript_run(script)
    return result == "found"


# ═══════════════════════════════════════════════════════════════
# 内部实现: Chrome Cookie DB 直接写入（仅 cookie，需先退出 Chrome）
# ═══════════════════════════════════════════════════════════════

def _check_crypto():
    if not _CRYPTO_AVAILABLE:
        print("[!] 需要 pycryptodome 库来加密 Chrome Cookie", file=sys.stderr)
        print("[!] 请运行: pip3 install pycryptodome", file=sys.stderr)
    return _CRYPTO_AVAILABLE


def _find_chrome_cookie_db() -> Optional[str]:
    import glob
    for pattern in CHROME_COOKIE_PATHS:
        for path in sorted(glob.glob(pattern)):
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                return path
    return None


def _get_chrome_password() -> Optional[str]:
    """从 macOS Keychain 获取 Chrome 存储的密码（用于 PBKDF2 推导 AES 密钥）。"""
    keychain_path = os.path.expanduser("~/Library/Keychains/login.keychain-db")
    for service in ["Chrome Safe Storage", "Chromium Safe Storage"]:
        for account in ["Chrome", "Chromium"]:
            try:
                result = subprocess.run(
                    ["security", "find-generic-password", "-w",
                     "-a", account, "-s", service, keychain_path],
                    capture_output=True, timeout=10,
                )
                if result.returncode == 0 and result.stdout:
                    return result.stdout.decode("utf-8").strip()
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass
    return None


def _derive_aes_key(password: str) -> bytes:
    """v10 格式：PBKDF2-HMAC-SHA1 推导 16 字节 AES 密钥（与 get_auth.py 对称）。"""
    return PBKDF2(
        password.encode("utf-8"),
        b"saltysalt",
        dkLen=16,
        count=1003,
        hmac_hash_module=SHA1,
    )


def _encrypt_v10(value: str, key: bytes) -> bytes:
    """加密为 Chrome v10 格式（"v10" + AES-128-CBC，固定 IV 为 16 个空格）。"""
    plain = pad(value.encode("utf-8"), AES.block_size)
    fixed_iv = b" " * 16
    cipher = AES.new(key, AES.MODE_CBC, iv=fixed_iv)
    return b"v10" + cipher.encrypt(plain)


def _set_cookie_via_db(domain: str, name: str, value: str, *, path: str = "/") -> bool:
    """直接写 Chrome Cookie 数据库（更新已存在的同名 Cookie 的加密值）。

    注意:
      - 必须在 Chrome 完全退出后使用，否则写入会被内存缓存覆盖 / DB 被锁定。
      - 只更新已存在的 Cookie；若该 Cookie 不存在请改用 CDP 方式。
    """
    if not _check_crypto():
        return False

    db_path = _find_chrome_cookie_db()
    if db_path is None:
        print("[!] 未找到 Chrome Cookie 数据库", file=sys.stderr)
        return False

    password = _get_chrome_password()
    if password is None:
        print("[!] 无法从 Keychain 获取 Chrome 密码", file=sys.stderr)
        return False

    key = _derive_aes_key(password)
    encrypted = _encrypt_v10(value, key)

    tmp_dir = tempfile.mkdtemp()
    tmp_db = os.path.join(tmp_dir, "Cookies")
    shutil.copy2(db_path, tmp_db)

    updated = 0
    try:
        conn = sqlite3.connect(tmp_db)
        cur = conn.cursor()
        cur.execute(
            "UPDATE cookies SET encrypted_value = ?, value = ? "
            "WHERE host_key LIKE ? AND name = ?",
            (encrypted, value, f"%{domain}%", name),
        )
        updated = cur.rowcount
        conn.commit()
        conn.close()

        if updated > 0:
            # 写回原位置
            shutil.copy2(tmp_db, db_path)
            print(f"[+] Cookie DB 已更新: {name} @ {domain}（{updated} 条，请重新打开 Chrome 生效）")
            return True
        else:
            print(f"[!] Cookie DB 中未找到 {name} @ {domain}，请改用 CDP 方式", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[!] 写入 Cookie DB 出错: {e}", file=sys.stderr)
        return False
    finally:
        try:
            os.unlink(tmp_db)
            os.rmdir(tmp_dir)
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════

def _resolve_value(args) -> str:
    """按优先级解析 value：-v/--value > --value-file > stdin。"""
    if args.value is not None:
        return args.value
    if args.value_file:
        try:
            with open(args.value_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError as e:
            print(f"[!] 读取 value 文件失败: {e}", file=sys.stderr)
            sys.exit(1)
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    print("[!] 需要提供要写入的值：-v/--value、--value-file，或通过 stdin 传入", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description=f"向浏览器写入指定域名 (默认: {DEFAULT_DOMAIN})、指定 key 的缓存内容",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例:
  %(prog)s -k userToken -v NEW_VALUE                # 写默认域名的 userToken Cookie
  %(prog)s -d {DEFAULT_DOMAIN} -k sessionId -v xxx  # 指定域名
  %(prog)s -k accessToken -v NEW_VALUE --type localStorage
  %(prog)s -k userToken -v NEW_VALUE --type cookie --secure --http-only
  %(prog)s -k userToken --value-file token.txt      # 从文件读取 value
  echo "NEW_VALUE" | %(prog)s -k userToken          # 从 stdin 读取 value
  %(prog)s -k userToken -v NEW_VALUE --db           # 直接写 Cookie DB（需先退出 Chrome）
        """,
    )
    parser.add_argument("-d", "--domain", default=DEFAULT_DOMAIN,
                        help=f"目标域名 (默认: {DEFAULT_DOMAIN})")
    parser.add_argument("-k", "--key", default="userToken",
                        help="要写入的 key（默认: userToken）。"
                             "cookie 时为 Cookie 名称；localStorage/sessionStorage 时为对应 key")
    parser.add_argument("-v", "--value", default=None,
                        help="要写入的新值")
    parser.add_argument("--value-file", default=None,
                        help="从文件读取要写入的新值")
    parser.add_argument("--type", "--cache-type", dest="cache_type",
                        default="cookie", choices=CACHE_TYPES,
                        help=f"缓存类型 (默认: cookie，可选: {', '.join(CACHE_TYPES)})")
    parser.add_argument("--path", default="/",
                        help="Cookie 路径 (默认: /，仅 cookie 有效)")
    parser.add_argument("--secure", action="store_true",
                        help="标记为 Secure Cookie（仅 cookie 有效）")
    parser.add_argument("--http-only", action="store_true",
                        help="标记为 HttpOnly Cookie（仅 cookie 有效）")
    parser.add_argument("--db", action="store_true",
                        help="直接写 Chrome Cookie DB（仅 cookie 有效，需先完全退出 Chrome）")
    parser.add_argument("--cdp", action="store_true",
                        help="强制走 CDP 写入（storage 默认走 AppleScript，设此参数改用 CDP）")
    parser.add_argument("--applescript", action="store_true",
                        help="强制走 AppleScript 写入（storage 默认即此方式，一般无需指定）")
    parser.add_argument("--no-verify", action="store_true",
                        help="写入后不回读验证")

    args = parser.parse_args()

    # --db 只对 cookie 有效
    if args.db and args.cache_type != "cookie":
        print("[!] --db 仅支持 --type cookie", file=sys.stderr)
        sys.exit(1)

    value = _resolve_value(args)
    key = _normalize_key(args.key)

    print(f"[*] 目标: {args.cache_type}  {key} @ {args.domain}")

    ok = push_value(
        args.domain, key, value,
        cache_type=args.cache_type,
        path=args.path,
        secure=args.secure,
        http_only=args.http_only,
        via_db=args.db,
        via_cdp=args.cdp,
        via_applescript=args.applescript,
    )

    if not ok:
        sys.exit(1)

    # ── 写后回读验证 ──
    if not args.no_verify and not args.db:
        if args.cache_type == "cookie":
            read_back = _get_cookie_via_cdp(args.domain, key)
        else:
            read_back = value  # localStorage/sessionStorage 已在写入时读回验证
        if args.cache_type == "cookie":
            if read_back == value:
                print(f"[✓] 验证通过：读回值一致")
            else:
                print(f"[!] 验证失败：读回值为 {read_back!r}", file=sys.stderr)
                sys.exit(1)

    print(f"[✓] 完成")


if __name__ == "__main__":
    main()
