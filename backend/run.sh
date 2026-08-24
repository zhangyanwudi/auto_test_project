#!/bin/bash
# ==============================================================================
# run.sh — Django manage.py 统一入口
# ==============================================================================
# 本项目所有 Django 命令的唯一入口，负责:
#   1. 自动创建/检测虚拟环境 (venv)
#   2. 自动安装依赖 (pip install -r requirements.txt)
#   3. 执行 manage.py 命令
#
# 用法:
#   ./run.sh runserver 0.0.0.0:8000     # 启动开发服务器
#   ./run.sh migrate                     # 数据库迁移
#   ./run.sh run_task_scheduler          # 启动定时任务调度器
#   ./run.sh shell                       # Django shell
#   ./run.sh <任意 manage.py 子命令>
#
# 其他脚本（如 service_manager.sh）通过 ./run.sh 来调用 Django 命令，
# 不再各自重复 venv 检测逻辑。
# ==============================================================================

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "未找到 venv，正在创建虚拟环境..."
  python3 -m venv venv
fi

if [ ! -f "venv/bin/python" ]; then
  echo "虚拟环境异常，请删除 venv 目录后重试。"
  exit 1
fi

# 确保 venv 中有可用的 pip
ensure_pip() {
  if [ ! -f "venv/bin/pip" ]; then
    echo "venv 中缺少 pip，正在修复..."
    # 方法1: 用 ensurepip 安装
    venv/bin/python -m ensurepip --upgrade 2>/dev/null || {
      # 方法2: 用 get-pip.py 引导安装
      echo "ensurepip 不可用，尝试 get-pip.py..."
      curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py 2>/dev/null || \
        wget -q https://bootstrap.pypa.io/get-pip.py -O /tmp/get-pip.py 2>/dev/null
      if [ -f /tmp/get-pip.py ]; then
        venv/bin/python /tmp/get-pip.py --force-reinstall 2>/dev/null
        rm -f /tmp/get-pip.py
      fi
    }
    if [ ! -f "venv/bin/pip" ]; then
      echo "ERROR: 无法安装 pip 到 venv，请手动执行: python3 -m venv --upgrade venv"
      exit 1
    fi
    echo "pip 修复完成"
  fi
}
ensure_pip

# 若未安装依赖，先安装（通过 .deps_installed 标记文件避免重复安装）
DEPS_MARKER=".deps_installed"
NEED_INSTALL=false

if [ -f "$DEPS_MARKER" ] && [ "$DEPS_MARKER" -nt "requirements.txt" ]; then
  # 标记文件比 requirements.txt 新，跳过安装检查
  :
else
  venv/bin/python -c "import django" 2>/dev/null || NEED_INSTALL=true
fi

if $NEED_INSTALL; then
  echo "正在安装依赖 (pip install -r requirements.txt)..."
  venv/bin/pip install -r requirements.txt && touch "$DEPS_MARKER"
fi

# 支持两种调用方式:
#   ./run.sh <manage.py 子命令>              → python manage.py <子命令>
#   ./run.sh --script <py文件> [参数...]      → python <py文件> [参数...]
if [ "$1" = "--script" ]; then
  shift
  exec venv/bin/python "$@"
else
  exec venv/bin/python manage.py "$@"
fi
