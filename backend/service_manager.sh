#!/bin/bash
# ==============================================================================
# 服务批量管理脚本
# ==============================================================================
# Django 命令统一通过 run.sh 执行（不再各自重复 venv/依赖管理逻辑）。
# 本脚本专注于进程生命周期管理：启动(nohup)、停止、状态检查、健康监控。
#
# 功能：
#   1. start       — 批量启动所有服务（自动检查并停止已运行的实例）
#   2. stop        — 批量停止所有服务
#   3. restart     — 批量重启所有服务
#   4. status      — 查看所有服务的运行状态
#   5. start-one   — 启动单个服务
#   6. stop-one    — 停止单个服务
#
# 用法:
#   ./service_manager.sh start            # 启动所有服务
#   ./service_manager.sh stop             # 停止所有服务
#   ./service_manager.sh restart          # 重启所有服务
#   ./service_manager.sh status           # 查看所有服务状态
#   ./service_manager.sh start-one <name> # 启动指定服务
#   ./service_manager.sh stop-one <name>  # 停止指定服务
# ==============================================================================

set -e

# ---- 颜色定义 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# ---- 工作目录 ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---- 配置 ----
LOG_DIR="${SCRIPT_DIR}/logs"
PID_DIR="${SCRIPT_DIR}/.pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

# 默认启动超时（秒），可通过环境变量覆盖
DEFAULT_STARTUP_TIMEOUT="${SERVICE_STARTUP_TIMEOUT:-30}"
# 健康检查间隔（秒），使用递增间隔避免频繁轮询
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-1}"

# ---- 依赖检查 ----
# Django 命令统一通过 run.sh 执行（run.sh 负责 venv 检测和依赖安装）
# 独立脚本（如 mock-proxy）直接使用 venv/bin/python
RUN_SH="${SCRIPT_DIR}/run.sh"
VENV_PYTHON="${SCRIPT_DIR}/venv/bin/python"

if [ ! -f "$RUN_SH" ]; then
    echo -e "${RED}[ERROR] run.sh 未找到: ${RUN_SH}${NC}"
    exit 1
fi

# ---- 本机 IP 检测 ----
detect_local_ip() {
    # 通过创建到外部地址的路由查询来获取本机主要 IP
    # macOS / Linux 通用
    local ip
    if command -v ifconfig &>/dev/null; then
        # macOS: 优先用 route get 找到默认网关接口
        ip=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}' | xargs ifconfig 2>/dev/null | awk '/inet /{print $2}' | head -1)
    fi
    if [ -z "$ip" ]; then
        # Linux fallback: ip route
        ip=$(ip route get 8.8.8.8 2>/dev/null | awk '/src/{print $7}' | head -1)
    fi
    if [ -z "$ip" ] || [ "$ip" = "127.0.0.1" ]; then
        # 最后兜底：hostname -I (Linux) 或 ifconfig 枚举
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi
    echo "${ip:-未知}"
}

# ==============================================================================
# 服务定义
# ==============================================================================
# 格式: "服务名|启动命令|PID文件|日志文件|健康检查端口|基础等待秒数|日志成功标志(可选)"
#   - 基础等待秒数: 进程启动后先等多久再开始健康检查（给进程初始化时间）
#   - 日志成功标志: grep -E 正则，用于辅助判断启动成功（| 分隔多个候选模式）
#   - 总超时 = 基础等待秒数 + DEFAULT_STARTUP_TIMEOUT（默认30s，可通过 SERVICE_STARTUP_TIMEOUT 环境变量覆盖）
#   - 添加新服务只需在 SERVICES 数组中新增一行即可。
# ==============================================================================

SERVICES=(
    # name              | start command                                                                                      | pid file                   | log file                       | health port | wait | log_success_pattern
    # Django 命令通过 run.sh 执行（统一 venv + 依赖管理）
    # wait: 进程启动后的基础等待秒数（有健康检查端口时，实际超时 = wait + 额外缓冲）
    # log_success_pattern: 日志中的启动成功标志，用于辅助判断（可选）
    "django-runserver  | ${RUN_SH} runserver 0.0.0.0:8000                                                                   | ${PID_DIR}/django.pid      | ${LOG_DIR}/django_runserver.log | 8000        | 8    | Starting development server"
    "task-scheduler     | ${RUN_SH} run_task_scheduler                                                                        | ${PID_DIR}/scheduler.pid   | ${LOG_DIR}/task_scheduler.log   | -           | 5    | Scheduler started|Task scheduler started|任务调度器已启动"
    # 非 Django 命令通过 run.sh --script 执行（统一 venv + 依赖管理）
    "mock-proxy         | ${RUN_SH} --script scripts/start_mock_proxy.py --host 0.0.0.0 --port 8080 --reload-interval 2 --background  | ${PID_DIR}/mock_proxy.pid  | ${LOG_DIR}/mock_proxy.log       | 8080        | 8    | Mock proxy started|代理服务已启动|Starting proxy"
)

# ==============================================================================
# 工具函数
# ==============================================================================

# 解析服务配置
# 参数: $1 = 数组元素, $2 = 要获取的字段 (name|command|pid_file|log_file|health_port|wait|log_success_pattern)
parse_field() {
    local entry="$1"
    local field="$2"
    case "$field" in
        name)                echo "$entry" | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $1); print $1}' ;;
        command)             echo "$entry" | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2}' ;;
        pid_file)            echo "$entry" | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $3); print $3}' ;;
        log_file)            echo "$entry" | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $4); print $4}' ;;
        health_port)         echo "$entry" | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $5); print $5}' ;;
        wait)                echo "$entry" | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $6); print $6}' ;;
        log_success_pattern) echo "$entry" | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $7); print $7}' ;;
    esac
}

# 根据服务名查找服务配置行
find_service() {
    local name="$1"
    for entry in "${SERVICES[@]}"; do
        local sname
        sname=$(parse_field "$entry" name)
        if [ "$sname" = "$name" ]; then
            echo "$entry"
            return 0
        fi
    done
    return 1
}

# 获取进程 PID（从 PID 文件）
get_pid() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        cat "$pid_file"
    fi
}

# 检查进程是否存活
is_process_alive() {
    local pid="$1"
    if [ -z "$pid" ]; then
        return 1
    fi
    kill -0 "$pid" 2>/dev/null
}

# 通过进程命令行特征查找 PID
# 使用 grep 在进程列表中搜索关键字
find_pid_by_pattern() {
    local pattern="$1"
    pgrep -f "$pattern" 2>/dev/null | head -1
}

# 检查端口是否被监听
is_port_listening() {
    local port="$1"
    if [ "$port" = "-" ]; then
        return 1  # 不检查端口
    fi
    lsof -i ":$port" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN
}

# 带超时的端口等待（使用递增间隔减少 CPU 开销）
# 参数: $1=端口 $2=超时秒数
wait_for_port() {
    local port="$1"
    local timeout="$2"
    local elapsed=0
    local interval=1
    while [ $elapsed -lt $timeout ]; do
        if is_port_listening "$port"; then
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
        # 递增间隔：1s → 2s → 3s → ... 最大 5s
        if [ "$interval" -lt 5 ]; then
            interval=$((interval + 1))
        fi
    done
    return 1
}

# 等待日志文件中出现成功标志
# 参数: $1=日志文件路径 $2=超时秒数 $3=成功标志的正则表达式（| 分隔）
wait_for_log_pattern() {
    local log_file="$1"
    local timeout="$2"
    local pattern="$3"

    if [ -z "$pattern" ]; then
        return 1
    fi

    local elapsed=0
    local interval=1
    while [ $elapsed -lt $timeout ]; do
        if [ -f "$log_file" ] && grep -qE "$pattern" "$log_file" 2>/dev/null; then
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
        # 递增间隔：1s → 2s → 3s → ... 最大 5s
        if [ "$interval" -lt 5 ]; then
            interval=$((interval + 1))
        fi
    done
    return 1
}

# 打印分隔线
print_divider() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 打印服务头部
print_header() {
    local title="$1"
    echo ""
    print_divider
    echo -e "${BOLD}${CYAN}  $title${NC}"
    print_divider
}

# ==============================================================================
# 核心操作函数
# ==============================================================================

# 获取服务的综合状态
# 返回: status_code (0=running, 1=not_running, 2=pid_stale)
get_service_status() {
    local entry="$1"
    local name pid_file pid health_port
    name=$(parse_field "$entry" name)
    pid_file=$(parse_field "$entry" pid_file)
    health_port=$(parse_field "$entry" health_port)
    pid=$(get_pid "$pid_file")

    local pid_alive=false
    local port_open=false

    if [ -n "$pid" ] && is_process_alive "$pid"; then
        pid_alive=true
    fi

    if [ "$health_port" != "-" ] && is_port_listening "$health_port"; then
        port_open=true
    fi

    # 检查是否有其他同名进程（没通过 pid 文件但实际在跑）
    local extra_pid
    extra_pid=$(find_pid_by_pattern "$name")

    if $pid_alive; then
        # 没有健康检查端口的服务，进程存活即视为运行中
        if [ "$health_port" = "-" ] || $port_open; then
            echo "running"  # 正常运行
        else
            echo "starting" # 进程存在但端口还没就绪
        fi
    elif ! $pid_alive && $port_open; then
        # 端口被占用但不是我们的 PID 文件记录的进程
        echo "port_stale"
    elif [ -f "$pid_file" ] && ! $pid_alive; then
        echo "dead"     # PID 文件存在但进程已死
    else
        echo "stopped"  # 未运行
    fi
}

# 停止单个服务
stop_service() {
    local entry="$1"
    local name pid_file pid
    name=$(parse_field "$entry" name)
    pid_file=$(parse_field "$entry" pid_file)
    pid=$(get_pid "$pid_file")

    echo -ne "  ${YELLOW}⏸  停止 ${name}...${NC}"

    local stopped=false

    # 1. 先尝试通过 PID 文件优雅终止
    if [ -n "$pid" ] && is_process_alive "$pid"; then
        kill "$pid" 2>/dev/null || true
        # 等待最多 10 秒
        for i in $(seq 1 10); do
            if ! is_process_alive "$pid"; then
                stopped=true
                break
            fi
            sleep 1
        done
        # 还没退出就强杀
        if ! $stopped && is_process_alive "$pid"; then
            kill -9 "$pid" 2>/dev/null || true
            sleep 1
            stopped=true
        fi
    fi

    # 2. 如果 PID 文件记录了但进程已经不在了，清理 PID 文件即可
    if [ -f "$pid_file" ] && [ -z "$pid" ] || [ -n "$pid" ] && ! is_process_alive "$pid" 2>/dev/null; then
        rm -f "$pid_file"
        stopped=true
    fi

    # 3. 尝试通过进程名查找并停止（兜底，处理没有 PID 文件但进程在跑的情况）
    local extra_pid
    extra_pid=$(find_pid_by_pattern "$name")
    if [ -n "$extra_pid" ]; then
        kill "$extra_pid" 2>/dev/null || true
        sleep 1
        if is_process_alive "$extra_pid"; then
            kill -9 "$extra_pid" 2>/dev/null || true
            sleep 1
        fi
        stopped=true
    fi

    rm -f "$pid_file"

    if $stopped || [ ! -f "$pid_file" ]; then
        echo -e " ${GREEN}已停止${NC}"
    else
        echo -e " ${YELLOW}未在运行${NC}"
    fi
}

# 启动单个服务
# 参数: $1=服务配置行 $2=skip_check(可选, 跳过已运行检查)
start_service() {
    local entry="$1"
    local skip_check="${2:-false}"
    local name command pid_file log_file health_port wait_time log_pattern
    name=$(parse_field "$entry" name)
    command=$(parse_field "$entry" command)
    pid_file=$(parse_field "$entry" pid_file)
    log_file=$(parse_field "$entry" log_file)
    health_port=$(parse_field "$entry" health_port)
    wait_time=$(parse_field "$entry" wait)
    log_pattern=$(parse_field "$entry" log_success_pattern)

    # 前置检查：如果已在运行且不跳过检查
    if ! $skip_check; then
        local status
        status=$(get_service_status "$entry")
        case "$status" in
            running|starting)
                echo -e "  ${YELLOW}⚠ ${name} 已在运行中，先停止再启动...${NC}"
                stop_service "$entry"
                sleep 1
                ;;
            port_stale)
                echo -e "  ${YELLOW}⚠ ${name} 端口被占用但 PID 不匹配，尝试清理...${NC}"
                stop_service "$entry"
                sleep 1
                ;;
        esac
    fi

    # 确保日志目录存在
    mkdir -p "$(dirname "$log_file")"

    echo -ne "  ${BLUE}🚀 启动 ${name}...${NC}"

    # 后台启动并记录 PID
    nohup $command > "$log_file" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$pid_file"

    # ---- 启动健康检查 ----
    # 基础等待：让进程先跑起来
    sleep "$wait_time"

    # 计算剩余超时（总超时 = 基础 wait + DEFAULT_STARTUP_TIMEOUT）
    local remaining_timeout=$((DEFAULT_STARTUP_TIMEOUT - wait_time))
    if [ "$remaining_timeout" -lt 5 ]; then
        remaining_timeout=5
    fi

    local success=false
    local port_ok=false
    local log_ok=false

    # 并行检查策略：
    #   1. 有健康检查端口 → 等待端口就绪（主要判断）
    #   2. 有日志成功标志 → 同时检查日志（辅助判断）
    #   3. 都没有 → 等待指定时间后检查进程存活

    if [ "$health_port" != "-" ]; then
        # 有健康检查端口：等待端口就绪
        echo -ne "\n         等待端口 ${health_port} 就绪（最多 ${remaining_timeout}s）..."
        if wait_for_port "$health_port" "$remaining_timeout"; then
            port_ok=true
        fi

        # 同时检查日志成功标志（如果有配置）
        if [ -n "$log_pattern" ]; then
            if wait_for_log_pattern "$log_file" "$((remaining_timeout / 2))" "$log_pattern"; then
                log_ok=true
            fi
        fi
    else
        # 没有健康检查端口：检查进程存活 + 日志成功标志
        sleep "$remaining_timeout"
    fi

    # 最终判断
    if is_process_alive "$new_pid"; then
        if [ "$health_port" != "-" ]; then
            if $port_ok; then
                # 端口已就绪 → 确认启动成功
                success=true
            elif [ -n "$log_pattern" ] && $log_ok; then
                # 日志有成功标志但端口还没就绪 → 大概率还在启动中，再等一会
                echo -ne "\n         日志检测到启动信号，额外等待 ${health_port} 端口就绪..."
                if wait_for_port "$health_port" "10"; then
                    success=true
                fi
            else
                # 端口未就绪，再给 10 秒机会（有些服务启动慢）
                echo -ne "\n         端口尚未就绪，额外等待..."
                if wait_for_port "$health_port" "10"; then
                    success=true
                fi
            fi
        elif [ -n "$log_pattern" ]; then
            # 无端口，靠日志模式判断
            if grep -qE "$log_pattern" "$log_file" 2>/dev/null; then
                success=true
            else
                # 进程存活但日志无成功标志 → 可能还在初始化
                echo -ne "\n         等待日志成功标志..."
                if wait_for_log_pattern "$log_file" "10" "$log_pattern"; then
                    success=true
                fi
            fi
        else
            # 无端口无日志模式 → 进程存活即视为成功
            success=true
        fi
    fi

    # 输出结果
    if $success; then
        echo -e "\r  ${BLUE}🚀 启动 ${name}...${NC} ${GREEN}✅ 成功${NC}  (PID: ${new_pid})"
        if [ "$health_port" != "-" ]; then
            echo -e "         端口: ${GREEN}${health_port} (已就绪)${NC}"
        fi
        if [ -n "$log_pattern" ] && $log_ok; then
            echo -e "         日志: 检测到启动成功标志"
        fi
        echo -e "         日志: ${log_file}"
    elif is_process_alive "$new_pid"; then
        echo -e "\r  ${BLUE}🚀 启动 ${name}...${NC} ${YELLOW}⚠ 进程存活但健康检查未通过${NC}  (PID: ${new_pid})"
        if [ "$health_port" != "-" ]; then
            echo -e "         端口 ${health_port}: ${YELLOW}未就绪（可能仍在初始化中）${NC}"
        fi
        echo -e "         日志: ${log_file}"
        echo -e "         ${YELLOW}提示: 稍后可用 './service_manager.sh status' 确认状态${NC}"
    else
        echo -e "\r  ${BLUE}🚀 启动 ${name}...${NC} ${RED}❌ 失败 — 进程启动后退出了${NC}"
        echo -e "         查看日志: tail -50 ${log_file}"
        rm -f "$pid_file"
        return 1
    fi

    return 0
}

# 打印单个服务状态行
print_service_status() {
    local entry="$1"
    local name pid_file log_file health_port pid status
    name=$(parse_field "$entry" name)
    pid_file=$(parse_field "$entry" pid_file)
    log_file=$(parse_field "$entry" log_file)
    health_port=$(parse_field "$entry" health_port)
    pid=$(get_pid "$pid_file")
    status=$(get_service_status "$entry")

    printf "  ${BOLD}%-22s${NC} " "$name"

    case "$status" in
        running)
            echo -ne "${GREEN}● 运行中${NC}   "
            ;;
        starting)
            echo -ne "${YELLOW}◐ 启动中${NC}   "
            ;;
        dead)
            echo -ne "${RED}✕ 已失效${NC}   "
            ;;
        port_stale)
            echo -ne "${RED}⚠ 端口残留${NC} "
            ;;
        stopped)
            echo -ne "${RED}○ 未运行${NC}   "
            ;;
        *)
            echo -ne "${RED}? 未知${NC}     "
            ;;
    esac

    if [ -n "$pid" ]; then
        if is_process_alive "$pid"; then
            echo -ne "PID: ${GREEN}${pid}${NC}  "
        else
            echo -ne "PID: ${RED}${pid}(stale)${NC}  "
        fi
    else
        echo -ne "PID: -       "
    fi

    if [ "$health_port" != "-" ]; then
        if is_port_listening "$health_port"; then
            echo -ne "端口: ${GREEN}${health_port}${NC}  "
        else
            echo -ne "端口: ${RED}${health_port}${NC}  "
        fi
    fi

    # 显示日志文件最后修改时间
    if [ -f "$log_file" ]; then
        local log_size
        log_size=$(du -h "$log_file" 2>/dev/null | cut -f1)
        echo -ne "日志: ${log_file} (${log_size})"
    fi

    echo ""
}

# ==============================================================================
# 命令实现
# ==============================================================================

cmd_status() {
    print_header "服务运行状态"
    local all_running=true
    for entry in "${SERVICES[@]}"; do
        print_service_status "$entry"
        local status
        status=$(get_service_status "$entry")
        if [ "$status" != "running" ]; then
            all_running=false
        fi
    done
    echo ""
    print_divider
    if $all_running; then
        echo -e "  ${GREEN}所有服务运行正常 ✅${NC}"
    else
        echo -e "  ${YELLOW}部分服务未运行，使用 'start' 命令启动${NC}"
    fi
    print_divider
    echo ""
}

cmd_start() {
    print_header "启动所有服务"
    local failed_services=()
    local success_count=0
    local total=${#SERVICES[@]}

    for entry in "${SERVICES[@]}"; do
        local name
        name=$(parse_field "$entry" name)
        echo ""
        if start_service "$entry"; then
            success_count=$((success_count + 1))
        else
            failed_services+=("$name")
        fi
    done

    echo ""
    print_divider
    echo -e "  启动完成: ${GREEN}${success_count}/${total}${NC} 成功"
    if [ ${#failed_services[@]} -gt 0 ]; then
        echo -e "  ${RED}失败的服务:${NC}"
        for f in "${failed_services[@]}"; do
            echo -e "    - $f"
        done
    fi
    print_divider
    echo ""

    # 显示最终状态
    cmd_status

    # 有失败的服务则返回非零
    if [ ${#failed_services[@]} -gt 0 ]; then
        return 1
    fi
}

cmd_stop() {
    print_header "停止所有服务"
    for entry in "${SERVICES[@]}"; do
        stop_service "$entry"
    done
    echo ""
    print_divider
    echo -e "  ${GREEN}所有服务已停止${NC}"
    print_divider
    echo ""

    # 清理残留
    rm -f "$PID_DIR"/*.pid
}

cmd_restart() {
    print_header "重启所有服务"
    cmd_stop > /dev/null 2>&1
    sleep 2
    cmd_start
}

cmd_start_one() {
    local name="$1"
    if [ -z "$name" ]; then
        echo -e "${RED}用法: $0 start-one <服务名>${NC}"
        echo ""
        echo "可用服务:"
        for entry in "${SERVICES[@]}"; do
            local sname
            sname=$(parse_field "$entry" name)
            echo "  - $sname"
        done
        exit 1
    fi

    local entry
    entry=$(find_service "$name")
    if [ -z "$entry" ]; then
        echo -e "${RED}未找到服务: ${name}${NC}"
        echo ""
        echo "可用服务:"
        for e in "${SERVICES[@]}"; do
            local sname
            sname=$(parse_field "$e" name)
            echo "  - $sname"
        done
        exit 1
    fi

    print_header "启动服务: ${name}"
    start_service "$entry"
    echo ""
}

cmd_stop_one() {
    local name="$1"
    if [ -z "$name" ]; then
        echo -e "${RED}用法: $0 stop-one <服务名>${NC}"
        echo ""
        echo "可用服务:"
        for entry in "${SERVICES[@]}"; do
            local sname
            sname=$(parse_field "$entry" name)
            echo "  - $sname"
        done
        exit 1
    fi

    local entry
    entry=$(find_service "$name")
    if [ -z "$entry" ]; then
        echo -e "${RED}未找到服务: ${name}${NC}"
        exit 1
    fi

    print_header "停止服务: ${name}"
    stop_service "$entry"
    echo ""
}

cmd_list() {
    echo ""
    echo -e "${BOLD}已注册的服务:${NC}"
    echo ""
    for entry in "${SERVICES[@]}"; do
        local name command
        name=$(parse_field "$entry" name)
        command=$(parse_field "$entry" command)
        echo -e "  ${BOLD}${name}${NC}"
        echo -e "    命令: ${command}"
        echo ""
    done
}

# ==============================================================================
# 主入口
# ==============================================================================

print_banner() {
    local local_ip
    local_ip=$(detect_local_ip)
    echo ""
    echo -e "${CYAN}  ╔══════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}  ║       🚀 服务批量管理工具 v1.0          ║${NC}"
    echo -e "${CYAN}  ╚══════════════════════════════════════════╝${NC}"
    echo -e "  项目目录: ${SCRIPT_DIR}"
    echo -e "  Django入口: ${RUN_SH}"
    echo -e "  本机IP: ${local_ip}"
    echo -e "  管理服务数: ${#SERVICES[@]}"
    echo ""
}

show_usage() {
    echo "用法: $0 <命令> [参数]"
    echo ""
    echo "命令:"
    echo "  start                  启动所有服务（自动停止已运行的实例）"
    echo "  stop                   停止所有服务"
    echo "  restart                重启所有服务"
    echo "  status                 查看所有服务运行状态"
    echo "  list                   列出所有已注册的服务"
    echo "  start-one <服务名>     启动指定服务"
    echo "  stop-one <服务名>      停止指定服务"
    echo ""
    echo "可用服务名:"
    for entry in "${SERVICES[@]}"; do
        local name
        name=$(parse_field "$entry" name)
        echo "  - $name"
    done
    echo ""
    echo "示例:"
    echo "  $0 start"
    echo "  $0 status"
    echo "  $0 start-one mock-proxy"
    echo "  $0 stop-one django-runserver"
    echo ""
}

case "${1:-}" in
    start)
        print_banner
        cmd_start
        ;;
    stop)
        print_banner
        cmd_stop
        ;;
    restart)
        print_banner
        cmd_restart
        ;;
    status)
        print_banner
        cmd_status
        ;;
    list)
        cmd_list
        ;;
    start-one)
        print_banner
        cmd_start_one "$2"
        ;;
    stop-one)
        print_banner
        cmd_stop_one "$2"
        ;;
    *)
        print_banner
        show_usage
        ;;
esac
