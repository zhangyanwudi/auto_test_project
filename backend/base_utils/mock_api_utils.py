# -*- coding: utf-8 -*-
"""
mock_api_utils.py — 基于 mitmproxy 的可配置 API Mock 代理工具

功能：
- 从配置文件（JSON）或代码动态加载拦截规则
- 支持多种 URL 匹配方式：contains、regex、exact
- 支持从 JSON 文件、内联字典、回调函数加载响应数据
- 支持后台线程启动 / 停止代理
- 兼容 mitmdump -s 方式作为 addon 脚本直接加载

使用方式：
    # 方式1: 从配置文件启动（后台运行）
    mock = MockApiServer("script/mock_config.json")
    mock.start()
    # ... 使用代理 ...
    mock.stop()

    # 方式2: 纯代码构建规则
    mock = MockApiServer(port=8080)
    mock.add_rule("ecpm.afafb.com", {"code": 200, "data": {"ecpm": 85.5}})
    mock.start(blocking=True)  # 前台阻塞运行

    # 方式3: 命令行作为 addon 脚本加载
    # mitmdump -s script/mock_api_utils.py

依赖：mitmproxy (>= 9.0)
"""

import json
import os
import re
import sys
import socket
import time
import asyncio
import threading
from pathlib import Path
from typing import Optional, Union, Callable, Any

from mitmproxy import http, options
from mitmproxy.master import Master
from mitmproxy.tools.dump import DumpMaster

# ---------- 尝试加载项目日志模块 ----------
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from base_utils.logger_base import setting_logger
    logger = setting_logger()
except Exception:
    import logging
    logger = logging.getLogger("mock_api")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(handler)


# ---------- 项目根目录（用于解析相对路径） ----------
_PROJECT_DIR = Path(__file__).resolve().parent.parent


def _resolve_path(file_path: str) -> Path:
    """解析路径：绝对路径直接返回，相对路径基于项目根目录"""
    p = Path(file_path)
    if p.is_absolute():
        return p
    return _PROJECT_DIR / p


def _load_json_file(file_path: str) -> Optional[dict]:
    """安全加载 JSON 文件，加载失败返回 None"""
    p = _resolve_path(file_path)
    if not p.exists():
        logger.warning(f"[MockApi] JSON 文件不存在: {p}")
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[MockApi] 加载 JSON 文件失败: {p}, 错误: {e}")
        return None


def _match_url(url: str, pattern: str, match_type: str) -> bool:
    """根据匹配类型判断 URL 是否命中规则"""
    if match_type == "exact":
        return url == pattern
    elif match_type == "regex":
        try:
            return bool(re.search(pattern, url))
        except re.error as e:
            logger.error(f"[MockApi] 正则表达式无效: {pattern}, 错误: {e}")
            return False
    else:  # 默认 contains
        return pattern in url


# ============================================================
# 核心 Addon 类
# ============================================================

class MockAddon:
    """
    mitmproxy addon，在 request 阶段拦截匹配的请求并返回 mock 响应。
    作为 Master 的 addon 注册使用。
    """

    def __init__(self, server: "MockApiServer"):
        self.server = server  # 持有对 MockApiServer 的弱引用以获取规则

    def request(self, flow: http.HTTPFlow) -> None:
        """拦截请求，匹配规则并返回 mock 响应"""
        url = flow.request.pretty_url
        rules = self.server.get_rules()

        for rule in rules:
            pattern = rule.get("url_pattern", "")
            match_type = rule.get("match_type", "contains")

            if not _match_url(url, pattern, match_type):
                continue

            # 命中规则，打印日志
            rule_name = rule.get("name", pattern)
            logger.info(f"[MockApi ✓] 拦截: {url} → 命中规则: {rule_name}")

            # 解析响应内容
            response_body = self._resolve_response_body(rule)
            if response_body is None:
                logger.warning(f"[MockApi] 规则 {rule_name} 无有效响应数据，跳过")
                continue

            # 构造状态码和头
            status_code = rule.get("status_code", 200)
            resp_headers = dict(rule.get("headers", {}))
            # 如果未显式指定 Content-Type，则根据响应体类型自动设置
            if "Content-Type" not in resp_headers and "content-type" not in resp_headers:
                if isinstance(response_body, (dict, list)):
                    resp_headers["Content-Type"] = "application/json; charset=utf-8"
                else:
                    resp_headers["Content-Type"] = "text/plain; charset=utf-8"
            resp_headers.setdefault("X-Mocked-By", "mitmproxy-mock-api")

            # 序列化 body
            if isinstance(response_body, (dict, list)):
                body = json.dumps(response_body, ensure_ascii=False).encode("utf-8")
            elif isinstance(response_body, str):
                body = response_body.encode("utf-8")
            elif isinstance(response_body, bytes):
                body = response_body
            else:
                body = str(response_body).encode("utf-8")

            # 构造并设置响应
            flow.response = http.Response.make(status_code, body, resp_headers)
            logger.info(f"[MockApi] 已返回 Mock 响应, status={status_code}, body_len={len(body)}")
            return  # 命中一条规则即返回

    def _query_database(self, rule: dict) -> Optional[Any]:
        """
        实时查询数据库获取响应数据。

        当规则中配置了 response_sql + response_db 时，此方法自动创建数据库连接、
        执行 SQL 并返回查询结果。查询失败时自动降级到 response_data。

        规则数据库字段:
            - response_sql: SQL 查询语句（必填）
            - response_db:  数据库连接配置 dict，字段: host, port, username, password, database, db_type
            - db_key:       自定义连接标识（可选，仅用于日志）

        参数:
            rule: 当前命中的规则字典

        返回:
            查询结果（list[dict] 格式），失败返回 None → 自动 fallback 到 response_data。
        """
        sql = rule.get("response_sql", "")
        response_db = rule.get("response_db")
        db_key = rule.get("db_key", "")

        if not sql:
            return None

        if not response_db:
            logger.warning("[MockApi] 规则指定了 response_sql 但未提供 response_db，"
                           "请通过 add_rule(..., response_db={host:..., port:..., ...}) 传入数据库连接信息")
            return None

        db_instance = None
        try:
            from base_utils.db_base import Database

            db_instance = Database(**response_db)
            if not db_instance.connected:
                logger.error(f"[MockApi] 数据库连接失败: {response_db.get('host')}:{response_db.get('port')}")
                return None

            label = f"[{db_key}] " if db_key else ""
            logger.info(f"[MockApi 📡] {label}实时查询: {response_db.get('db_type')} "
                        f"sql={sql[:120]}{'...' if len(sql) > 120 else ''}")

            result = db_instance.fetch_all(sql)

            # tuple → list[dict] 转为 JSON 可序列化格式
            if db_instance.conn and db_instance.conn.description:
                columns = [col[0] for col in db_instance.conn.description]
                serializable = [dict(zip(columns, row)) for row in result]
            else:
                serializable = result

            logger.info(f"[MockApi] 数据库查询成功, 返回 {len(serializable) if isinstance(serializable, list) else 1} 行")
            return serializable

        except Exception as e:
            logger.error(f"[MockApi] 数据库查询失败: {e}")
            return None
        finally:
            if db_instance is not None:
                try:
                    db_instance.close()
                except Exception:
                    pass

    def _resolve_response_body(self, rule: dict) -> Optional[Any]:
        """解析规则中的响应内容，优先级: response_file > response_sql > response_data > response_func"""
        # 1. 优先从 response_file 加载
        response_file = rule.get("response_file")
        if response_file:
            data = _load_json_file(response_file)
            if data is not None:
                return data

        # 2. 数据库实时查询（response_sql + db_key 或 response_db）
        response_sql = rule.get("response_sql")
        if response_sql:
            db_result = self._query_database(rule)
            if db_result is not None:
                return db_result
            # 查询失败时继续向下尝试 fallback

        # 3. 使用内联 response_data（数据库查询失败时的降级 fallback）
        response_data = rule.get("response_data")
        if response_data is not None:
            return response_data

        # 4. 尝试 response_func（回调函数，按名称查找）
        func_name = rule.get("response_func")
        if func_name:
            func = self.server.get_callback(func_name)
            if func:
                return func(rule)
            logger.warning(f"[MockApi] 未找到回调函数: {func_name}")

        return None


# ============================================================
# 主控类
# ============================================================

class MockApiServer:
    """
    Mock API 代理服务器。

    参数:
        config: 配置文件路径 (str) 或配置字典 (dict)，可选
        port: 代理监听端口，默认 8080
        host: 代理监听地址，默认 0.0.0.0

    用法示例::

            mock = MockApiServer(port=8080)
            mock.add_rule("api.example.com", {"code": 0, "msg": "ok"})
            mock.start()   # 后台运行
            ...
            mock.stop()
    """

    def __init__(
        self,
        config: Union[str, dict, None] = None,
        port: int = 8080,
        host: str = "0.0.0.0",
    ):
        self._host = host
        self._port = port
        self._rules: list[dict] = []
        self._callbacks: dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._master: Optional[Master] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running: bool = False  # 内部状态标记
        self._ready = threading.Event()  # 代理真正开始监听后置位
        self._start_error: Optional[str] = None

        # 热加载相关
        self._config_file: Optional[str] = None      # 当前加载的配置文件路径
        self._watcher_thread: Optional[threading.Thread] = None
        self._watcher_interval: float = 2.0
        self._watcher_stop = threading.Event()

        # 加载初始配置
        if config is not None:
            if isinstance(config, str):
                loaded = _load_json_file(config)
                if loaded:
                    self._load_config_dict(loaded)
                    self._config_file = str(_resolve_path(config))
            elif isinstance(config, dict):
                self._load_config_dict(config)

        # 创建 addon
        self._addon = MockAddon(self)

    # ---------- 配置加载 ----------

    def _load_config_dict(self, config: dict) -> None:
        """从字典加载配置"""
        if "port" in config:
            self._port = config["port"]
        if "host" in config:
            self._host = config["host"]
        if "rules" in config:
            for rule in config["rules"]:
                self._rules.append(rule)
            logger.info(f"[MockApi] 从配置加载了 {len(config['rules'])} 条规则")
        if "callbacks" in config:
            # callbacks 不支持从 JSON 文件自动加载（需要实际函数引用），此处仅记录
            logger.info(f"[MockApi] 配置中有 {len(config['callbacks'])} 个回调名称，"
                        f"请通过 register_callback() 手动注册")

    def load_config_file(self, file_path: str) -> None:
        """从 JSON 配置文件加载规则（增量添加）"""
        data = _load_json_file(file_path)
        if data:
            self._load_config_dict(data)
            self._config_file = str(_resolve_path(file_path))

    # ---------- 规则管理 ----------

    def add_rule(
        self,
        url_pattern: str,
        response_data: Any = None,
        match_type: str = "contains",
        status_code: int = 200,
        headers: Optional[dict] = None,
        name: Optional[str] = None,
        response_file: Optional[str] = None,
        response_func: Optional[Union[str, Callable]] = None,
        db_key: Optional[str] = None,
        response_sql: Optional[str] = None,
        response_db: Optional[dict] = None,
    ) -> int:
        """
        添加拦截规则。

        参数:
            url_pattern: URL 匹配模式
            response_data: 内联响应数据（dict/list/str），可作为数据库查询失败的降级 fallback
            match_type: 匹配方式 — "contains" (默认)、"regex"、"exact"
            status_code: 响应 HTTP 状态码，默认 200
            headers: 响应头字典
            name: 规则名称（用于日志标识）
            response_file: 响应数据 JSON 文件路径（最高优先级）
            response_func: 回调函数名或可调用对象，签名 func(rule) -> response
            db_key: 数据库连接 key，引用 db_configs 中的连接（需配合 response_sql 使用）
            response_sql: SQL 查询语句，命中规则时实时执行（优先级在 response_file 之后、response_data 之前）
            response_db: 规则级独立数据库连接配置，格式: {host, port, username, password, database, db_type}

        返回:
            当前规则总数
        """
        rule: dict = {
            "url_pattern": url_pattern,
            "match_type": match_type,
            "status_code": status_code,
            "headers": headers or {},
            "name": name or url_pattern,
        }

        # 处理回调函数（可与数据库查询/静态数据并存，优先级最低）
        if response_func is not None:
            if callable(response_func):
                # 内联回调，生成一个名字并注册
                func_name = f"__inline_{id(response_func)}__"
                self._callbacks[func_name] = response_func
                rule["response_func"] = func_name
            else:
                rule["response_func"] = response_func

        # 数据库查询相关字段（可与上面并存，优先级在 response_file 之后、response_data 之前）
        if response_sql:
            rule["response_sql"] = response_sql
            if db_key:
                rule["db_key"] = db_key
            elif response_db:
                rule["response_db"] = response_db

        # 静态响应数据（作为数据库查询失败时的降级 fallback）
        if response_file is not None:
            rule["response_file"] = response_file
        elif response_data is not None:
            rule["response_data"] = response_data

        with self._lock:
            self._rules.append(rule)
            count = len(self._rules)

        logger.info(f"[MockApi] 已添加规则: {rule['name']} "
                    f"(pattern={url_pattern}, match={match_type})")
        return count

    def remove_rule(self, url_pattern: str) -> int:
        """
        移除所有匹配 url_pattern 的规则。

        参数:
            url_pattern: 要匹配的 URL 模式

        返回:
            被移除的规则数量
        """
        with self._lock:
            before = len(self._rules)
            self._rules = [
                r for r in self._rules
                if r.get("url_pattern") != url_pattern
            ]
            removed = before - len(self._rules)
            logger.info(f"[MockApi] 已移除 {removed} 条规则 (pattern={url_pattern})")
            return removed

    def remove_rule_by_name(self, name: str) -> int:
        """按名称移除规则，返回被移除数量"""
        with self._lock:
            before = len(self._rules)
            self._rules = [r for r in self._rules if r.get("name") != name]
            removed = before - len(self._rules)
            logger.info(f"[MockApi] 已移除 {removed} 条规则 (name={name})")
            return removed

    def clear_rules(self) -> None:
        """清空所有规则"""
        with self._lock:
            count = len(self._rules)
            self._rules.clear()
            logger.info(f"[MockApi] 已清空全部 {count} 条规则")

    def load_rules_from_db(self, rules_queryset) -> int:
        """
        从 Django QuerySet 批量加载规则（清空现有规则后加载）。

        用于 CLI 独立启动脚本和 Web 视图层（热加载）共用同一段逻辑，
        避免各处重复 DB → add_rule 转换代码。

        参数:
            rules_queryset: ZMockApiRule QuerySet（应已按 .filter(status=1) 过滤并排序）

        返回:
            加载的规则数
        """
        self.clear_rules()
        count = 0
        for rule in rules_queryset:
            resp_db = None
            if rule.response_db:
                try:
                    resp_db = json.loads(rule.response_db)
                except (json.JSONDecodeError, TypeError):
                    resp_db = None

            resp_data = None
            if rule.response_data:
                try:
                    resp_data = json.loads(rule.response_data)
                except (json.JSONDecodeError, TypeError):
                    # 非 JSON 数据（如纯文本、base64 字符串等），直接作为原始字符串返回
                    resp_data = rule.response_data

            self.add_rule(
                url_pattern=rule.url_pattern,
                match_type=rule.match_type,
                response_file=rule.response_file or None,
                response_data=resp_data,
                response_sql=rule.response_sql or None,
                response_db=resp_db,
                status_code=int(rule.status_code),
                name=rule.rule_name,
            )
            count += 1

        logger.info(f"[MockApi] 从数据库加载了 {count} 条规则")
        return count

    def get_rules(self) -> list[dict]:
        """获取当前所有规则的副本（线程安全）"""
        with self._lock:
            return list(self._rules)

    def list_rules(self) -> None:
        """打印所有规则概览"""
        with self._lock:
            if not self._rules:
                logger.info("[MockApi] 当前无规则")
                return
            logger.info(f"[MockApi] 当前共 {len(self._rules)} 条规则:")
            for i, rule in enumerate(self._rules, 1):
                logger.info(f"  {i}. [{rule.get('match_type', 'contains')}] "
                            f"{rule.get('name', '')} → {rule.get('url_pattern', '')}")

    # ---------- 配置文件热加载 ----------

    def reload(self) -> int:
        """
        重新加载配置文件，返回加载的规则数。

        注意：会先清空所有现有规则，然后从 _config_file 重新加载。
        """
        if not self._config_file:
            logger.warning("[MockApi] 无配置文件可重载")
            return 0
        with self._lock:
            self._rules.clear()
        self.load_config_file(self._config_file)
        count = len(self._rules)
        logger.info(f"[MockApi] 热加载完成，共 {count} 条规则")
        return count

    def _watch_loop(self) -> None:
        """后台轮询配置文件 mtime，变化时自动 reload"""
        if not self._config_file:
            return
        try:
            last_mtime = os.path.getmtime(self._config_file)
        except OSError:
            last_mtime = 0

        while not self._watcher_stop.wait(timeout=self._watcher_interval):
            try:
                current_mtime = os.path.getmtime(self._config_file)
            except OSError:
                continue
            if current_mtime != last_mtime:
                last_mtime = current_mtime
                logger.info("[MockApi] 检测到配置文件变更，正在热加载...")
                self.reload()
                self.list_rules()
        logger.info("[MockApi] 配置文件监控已停止")

    def enable_hot_reload(self, interval: float = 2.0) -> None:
        """
        启用配置文件热加载。

        参数:
            interval: 轮询间隔（秒），默认 2.0
        """
        if not self._config_file:
            logger.warning("[MockApi] 未加载配置文件，无法启用热加载")
            return
        if self._watcher_thread is not None:
            logger.warning("[MockApi] 热加载已在运行中")
            return
        self._watcher_interval = interval
        self._watcher_stop.clear()
        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            name="mock-api-watcher",
            daemon=True,
        )
        self._watcher_thread.start()
        logger.info(f"[MockApi] 已启用配置文件热加载 (interval={interval}s): {self._config_file}")

    # ---------- 回调函数管理 ----------

    def register_callback(self, name: str, func: Callable) -> None:
        """
        注册回调函数，供规则的 response_func 按名称引用。

        参数:
            name: 回调名称
            func: 可调用对象，签名 func(rule: dict) -> response_data
        """
        self._callbacks[name] = func
        logger.info(f"[MockApi] 已注册回调函数: {name}")

    def get_callback(self, name: str) -> Optional[Callable]:
        """获取已注册的回调函数"""
        return self._callbacks.get(name)

    # ---------- 服务启停 ----------

    def _check_port_available(self, host: Optional[str] = None, port: Optional[int] = None) -> bool:
        """预检端口是否可用，避免 mitmproxy 内部报错难以排查"""
        bind_host = host if host is not None else self._host
        bind_port = port if port is not None else self._port
        # 用 127.0.0.1 探测更可靠：0.0.0.0 在部分系统上无法准确反映占用情况
        probe_host = "127.0.0.1" if bind_host in ("0.0.0.0", "::", "") else bind_host
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((probe_host, bind_port))
            return True
        except OSError:
            return False

    def wait_until_port_free(self, timeout: float = 5.0) -> bool:
        """等待本实例端口释放，返回是否已空闲"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._check_port_available():
                return True
            time.sleep(0.1)
        return self._check_port_available()

    def start(self, blocking: bool = False, ready_timeout: float = 8.0) -> bool:
        """
        启动 Mock API 代理服务。

        参数:
            blocking: True=前台阻塞运行, False=后台线程运行
            ready_timeout: 后台模式下等待监听就绪的超时秒数

        返回:
            是否成功启动（blocking=True 时仅表示启动过程是否异常退出前曾就绪）
        """
        if self.is_running():
            logger.warning("[MockApi] 代理服务已在运行中")
            return True

        # 残留线程/事件循环时先清理，避免重复启动占端口
        if self._thread is not None and self._thread.is_alive():
            logger.warning("[MockApi] 检测到残留代理线程，先停止再启动")
            self.stop()
        elif self._loop is not None or self._master is not None:
            self._cleanup()

        # 端口预检，避免 mitmproxy 内部报错难以排查
        if not self._check_port_available():
            logger.error(
                f"[MockApi] 端口 {self._port} 已被占用，无法启动代理服务。"
                f"请尝试: lsof -i :{self._port} 查看占用进程，"
                f"或指定其他端口: MockApiServer(port=18080)"
            )
            return False

        logger.info(f"[MockApi] 正在启动代理服务 → {self._host}:{self._port}")
        self.list_rules()

        self._ready.clear()
        self._start_error = None
        self._loop = asyncio.new_event_loop()

        if blocking:
            # 前台阻塞模式：在当前线程运行事件循环
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._run_master())
            except KeyboardInterrupt:
                logger.info("[MockApi] 收到中断信号，正在停止...")
            finally:
                self._cleanup()
            return self._start_error is None
        else:
            # 后台线程模式：必须等监听就绪后再返回，避免调用方误判失败并重复创建实例
            self._thread = threading.Thread(
                target=self._run_in_thread,
                name="mock-api-proxy",
                daemon=True,
            )
            self._thread.start()

            ready = self._ready.wait(timeout=ready_timeout)
            if not ready or not self._running:
                err = self._start_error or f"代理在 {ready_timeout}s 内未就绪"
                logger.error(f"[MockApi] 启动失败: {err}")
                self.stop()
                return False

            logger.info(f"[MockApi] 后台代理线程已启动 (port={self._port})")
            return True

    def _run_in_thread(self) -> None:
        """在后台线程中运行 asyncio 事件循环"""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_master())
        except Exception as e:
            self._start_error = str(e)
            logger.error(f"[MockApi] 代理线程异常: {e}")
        finally:
            self._running = False
            self._ready.set()
            self._cleanup()

    async def _run_master(self) -> None:
        """异步运行 mitmproxy Master"""
        opts = options.Options(
            listen_host=self._host,
            listen_port=self._port,
            ssl_insecure=True,  # 忽略 SSL 证书验证，便于拦截 HTTPS
        )

        try:
            # 在已运行的 event loop 内创建，Master 会绑定到 get_running_loop()
            self._master = DumpMaster(opts)
            self._master.addons.add(self._addon)
        except Exception as e:
            self._start_error = str(e)
            logger.error(f"[MockApi] 创建 Master 失败: {e}")
            return

        server_ref = self

        class _ReadySignal:
            """mitmproxy RunningHook：servers 绑定成功后触发"""

            def running(self):
                server_ref._running = True
                server_ref._ready.set()
                logger.info(
                    f"[MockApi] 代理已启动: http://{server_ref._host}:{server_ref._port}"
                )

        self._master.addons.add(_ReadySignal())

        try:
            await self._master.run()
        except Exception as e:
            self._start_error = str(e)
            logger.error(f"[MockApi] Master.run() 异常: {e}")
        finally:
            self._running = False

    def _cleanup(self) -> None:
        """清理资源（应在代理线程内、或线程已退出后调用）"""
        self._running = False
        loop = self._loop
        self._master = None
        self._loop = None
        if loop is not None and not loop.is_closed():
            try:
                if hasattr(asyncio, "all_tasks"):
                    pending = asyncio.all_tasks(loop)
                else:
                    pending = set()
                for task in pending:
                    task.cancel()
                if pending and not loop.is_running():
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass

    async def _async_shutdown(self) -> None:
        """在代理事件循环内：先关闭监听端口，再结束 Master"""
        master = self._master
        if master is None:
            return
        try:
            ps = master.addons.get("proxyserver")
            if ps is not None:
                # mitmproxy 的 Master.shutdown() 不会自动停掉 Proxyserver 监听 socket
                await ps.servers.update([])
        except Exception as e:
            logger.warning(f"[MockApi] 关闭 proxy servers 失败: {e}")
        try:
            master.shutdown()
        except Exception as e:
            logger.warning(f"[MockApi] Master.shutdown 失败: {e}")

    def stop(self) -> None:
        """停止代理服务（即使 is_running 已为 False，也会尝试回收残留线程/端口）"""
        has_thread = self._thread is not None and self._thread.is_alive()
        has_master = self._master is not None
        if not self._running and not has_thread and not has_master:
            logger.warning("[MockApi] 代理服务未在运行")
            # 仍尝试等待端口释放（应对上次异常退出残留）
            self.wait_until_port_free(timeout=1.0)
            return

        logger.info("[MockApi] 正在停止代理服务...")

        # 停止热加载监控
        if self._watcher_thread is not None and self._watcher_thread.is_alive():
            self._watcher_stop.set()
            self._watcher_thread.join(timeout=3)
            self._watcher_thread = None

        # 在代理 loop 内关闭监听 socket + shutdown（仅 call shutdown 不会释放端口）
        master = self._master
        loop = self._loop
        if master is not None and loop is not None and not loop.is_closed():
            try:
                fut = asyncio.run_coroutine_threadsafe(self._async_shutdown(), loop)
                fut.result(timeout=8)
            except Exception as e:
                logger.warning(f"[MockApi] 异步停止失败，回退 shutdown: {e}")
                try:
                    master.shutdown()
                except Exception as e2:
                    logger.warning(f"[MockApi] shutdown 调用失败: {e2}")

        # 等待代理线程自行退出并在 finally 中完成 _cleanup（勿跨线程强关 loop）
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=8)
            if self._thread.is_alive():
                logger.warning("[MockApi] 代理线程在 8s 内未退出")

        self._thread = None
        self._running = False

        # 线程已退出时通常已 cleanup；若仍有残留则兜底
        if self._loop is not None or self._master is not None:
            self._cleanup()

        # 等待端口真正释放，保证可立即再次启动
        if not self.wait_until_port_free(timeout=5.0):
            logger.warning(
                f"[MockApi] 停止后端口 {self._port} 仍可能被占用，"
                f"稍后重试启动或检查: lsof -i :{self._port}"
            )
        else:
            logger.info("[MockApi] 代理服务已停止")

    def is_running(self) -> bool:
        """返回代理服务是否正在运行（已就绪监听）"""
        return bool(self._running)


# ============================================================
# 模块级实例（兼容 mitmdump -s 加载方式）
# ============================================================

# 当通过 mitmdump -s script/mock_api_utils.py 加载时，mitmproxy 会识别
# 顶层 addons 列表，自动注册。

_server_instance: Optional[MockApiServer] = None
"""全局 MockApiServer 实例，供外部使用"""


def get_server() -> Optional[MockApiServer]:
    """获取全局 MockApiServer 实例"""
    return _server_instance


def create_server(
    config: Union[str, dict, None] = None,
    port: int = 8080,
    host: str = "0.0.0.0",
) -> MockApiServer:
    """
    创建并返回 MockApiServer 实例（同时设置全局实例）。

    参数:
        config: 配置文件路径或配置字典
        port: 代理监听端口，默认 8080
        host: 代理监听地址，默认 0.0.0.0

    返回:
        MockApiServer 实例
    """
    global _server_instance
    _server_instance = MockApiServer(config=config, port=port, host=host)
    return _server_instance


# mitmdump -s 加载时使用的 addon 列表
# 如果配置了 MOCK_API_CONFIG 环境变量则自动加载
addons = []

_config_path = os.environ.get("MOCK_API_CONFIG")
if _config_path:
    _config_data = _load_json_file(_config_path)
    if _config_data:
        _srv = MockApiServer(config=_config_data)
        _server_instance = _srv
        addons.append(_srv._addon)


# ============================================================
# 直接运行入口
# ============================================================

if __name__ == "__main__":
    import argparse

    # ============================================================
    # 运行方式1
    # 1. 安装 mitmproxy
    # pip install mitmproxy
    # 2. 启动代理（监听 8080 端口）
    # mitmproxy -s ecpm_interceptor.py --mode regular --listen-port 8080
    # 3、或者后台运行（无界面）
    # mitmdump -s ecpm_interceptor.py --mode regular --listen-port 8080
    # ============================================================

    """
    # start_mock_db.py — 命令行启动带数据库查询的 Mock 代理
    import sys
    from pathlib import Path
    
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    
    from base_utils.mock_api_utils import MockApiServer
    
    mock = MockApiServer(port=8080)
    
    # 从配置文件加载静态规则（可选）
    mock.load_config_file("base_utils/mock_config.json")
    
    # 额外添加数据库查询规则
    mock.add_rule(
        url_pattern="ecpm.afafb.com/infer/v1/ecpm",
        response_sql="SELECT ecpm, currency, update_time FROM ecpm_config WHERE status=1 LIMIT 1",
        response_db={
            "host":     "127.0.0.1",
            "port":     3306,
            "username": "root",
            "password": "123456",
            "database": "test_db",
            "db_type":  "mysql",
        },
        response_data={"code": 500, "msg": "DB查询失败，兜底数据"},
        name="ECPM-数据库实时查询",
    )
    
    mock.add_rule(
        url_pattern="/api/user/profile",
        response_sql="SELECT user_id, nickname, level FROM user_profile WHERE user_id=1001",
        response_db={
            "host":     "127.0.0.1",
            "port":     3306,
            "username": "root",
            "password": "123456",
            "database": "test_db",
            "db_type":  "mysql",
        },
        name="用户信息-数据库查询",
    )
    
    # 前台阻塞运行，Ctrl+C 退出
    print("🚀 Mock 代理启动: 127.0.0.1:8080")
    mock.start(blocking=True)

    
    """

    parser = argparse.ArgumentParser(description="Mock API 代理服务器")
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        help="配置文件路径 (JSON)",
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        deault=8080,
        help="代理监听端口 (默认: 8080)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="代理监听地址 (默认: 0.0.0.0)",
    )
    parser.add_argument(
        "--blocking",
        action="store_true",
        default=True,
        help="前台阻塞运行 (默认)",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="后台运行",
    )
    parser.add_argument(
        "-w", "--watch",
        action="store_true",
        help="启用配置文件热加载（检测到文件变更时自动重载规则）",
    )
    args = parser.parse_args()

    # 创建并启动
    server = create_server(
        config=args.config,
        port=args.port,
        host=args.host,
    )

    if args.config is None:
        # 未指定 -c 时，自动检测默认配置文件
        default_config = Path(__file__).resolve().parent / "mock_config.json"
        if default_config.exists():
            logger.info(f"[MockApi] 自动加载默认配置文件: {default_config}")
            server.load_config_file(str(default_config))
        else:
            raise ValueError("缺少配置文件！！")
    # 启用热加载
    if args.watch:
        server.enable_hot_reload()

    block = args.blocking and not args.background
    server.start(blocking=block)
