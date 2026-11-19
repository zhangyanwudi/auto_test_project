# CLAUDE.md — 项目约定与开发规范

前后端分离项目：`frontend/`（Vue 3 + Vite）、`backend/`（Django + MySQL）。

## 时间约定（重要）

- 平台所有**展示给用户的时间统一使用 UTC+8（北京时间）**，后端负责转换、前端直接展示。
- 后端序列化时间时统一走 `base_utils/time_base.py` 的 `format_datetime_utc8(dt)`，输出 `%Y-%m-%d %H:%M:%S`；
  **不要**再对时间字段直接调用 `.isoformat()`（会输出 UTC 时间或带 `+00:00` 后缀的字符串）。
- naive datetime 一律视为 UTC 再转北京时间（与 `USE_TZ=True` 下数据库存储一致）。
- 前端展示时间直接渲染后端已格式化的字符串即可，无需再作时区/格式转换。

## 数据库（MySQL）

- 表结构通过手写 SQL 维护（`backend/sql/*.sql` 建表/升级脚本），`apps/*/migrations` 大多为空；改 schema 用 SQL 脚本，不用 Django migration。
- 默认连接：`127.0.0.1:3306`，用户 `root`，密码 `123456`，库 `auto_test_db`。

## 浏览器调试约定（重要）

- 所有调试、探索、回放执行的 Playwright 浏览器**一律使用无痕模式**：每次执行新建独立 context，不复用 cookie / localStorage / storage_state，不使用 `launch_persistent_context`。
- 登录态只能通过 `_inject_explore_login` 临时注入，不得因为「省事」去持久化 profile。
- 涉及真实提交（如订单「提交审核」）的实跑，需先与用户确认，再执行。

## 运行方式

- 后端：`cd backend && ./run.sh runserver`；进程生命周期用 `./service_manager.sh start|stop|restart|status|start-one|stop-one|restart-one <服务名>`。
- 前端：`cd frontend && yarn dev`（默认 http://localhost:5173）。
