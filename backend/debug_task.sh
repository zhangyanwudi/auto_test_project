#!/bin/bash
# ==============================================================================
# debug_task.sh — 本地调试定时任务脚本
# ==============================================================================
# 自动处理两件容易踩坑的事：
#   1. 使用项目 venv 的 python（无需手动 source activate）
#   2. 注入 PYTHONPATH=backend（否则 import apis / base_utils 会报 ModuleNotFoundError）
#
# 用法：
#   ./debug_task.sh <task_file 下的文件名> [脚本参数...]
#
# 示例：
#   ./debug_task.sh test_run_task.py
#   ./debug_task.sh run_kol_activate_pro.py --debug
#   ./debug_task.sh run_kol_activate_pro.py --debug --only "获取达人列表"
#   ./debug_task.sh run_kol_activate_pro.py --prod
#
# 说明：
#   - 第一个参数必须是 backend/task_file 目录下的文件名（支持带不带 task_file/ 前缀）
#   - 其余参数原样透传给任务脚本
#   - 与 executor 调度执行的区别：不会注入 SCHEDULED_TASK_EXEC 标记，
#     因此 run_kol_activate_pro.py 的 IS_DEBUG 仍由 --debug / --prod 决定（默认正式）
# ==============================================================================

set -euo pipefail

# ---- 工作目录：定位到 backend（脚本所在目录）----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---- 检查 venv ----
if [ ! -f "venv/bin/python" ]; then
    echo "未找到 venv，请先执行 ./run.sh runserver 完成依赖初始化，或手动创建 venv。" >&2
    exit 1
fi

# ---- 解析第一个参数：任务文件名 ----
if [ $# -lt 1 ]; then
    echo "用法：$0 <task_file 下的文件名> [脚本参数...]" >&2
    echo "示例：$0 run_kol_activate_pro.py --debug" >&2
    exit 1
fi

TASK_FILE="$1"
shift

# ---- 归一化文件名：去掉可能的前缀，只保留 basename ----
BASE_NAME="$(basename "$TASK_FILE")"

# ---- 安全校验：文件必须真实存在于 task_file 目录下（防路径穿越）----
TASK_FILE_DIR="$(cd "$SCRIPT_DIR/task_file" && pwd)"
SCRIPT_PATH="$TASK_FILE_DIR/$BASE_NAME"
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "未找到任务文件：$BASE_NAME" >&2
    echo "task_file 目录下可选文件：" >&2
    ls -1 "$TASK_FILE_DIR" 2>/dev/null | grep -v '^\.gitkeep$' || true
    exit 1
fi

# ---- 注入 PYTHONPATH 并执行（venv python + -u 实时输出）----
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec venv/bin/python -u "$SCRIPT_PATH" "$@"
