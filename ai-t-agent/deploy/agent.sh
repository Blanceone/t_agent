#!/bin/bash
# AI-T-Agent 服务器端管理脚本
# 用法: ./agent.sh <命令> [参数]
#
# 命令:
#   status          查看账户/持仓/股票池现价/最近交易
#   add <代码>      添加股票到池
#   remove <代码>   移除股票（触发清仓）
#   clear           全部清仓清池
#   pause           暂停策略
#   resume          恢复交易
#   cash <金额>     调整资金
#   log [行数]      查看最近日志（默认50）
#   report [日期]   查看日报
#   restart         重启服务
#   stop            停止服务
#   start           启动服务
#   running         查看服务状态
#   cal <年份>      生成交易日历

APP_DIR="/opt/ai-t-agent"
export PYTHONPATH="$APP_DIR/src"
PYTHON="$APP_DIR/.venv/bin/python"

cd "$APP_DIR" || exit 1

cli() {
    $PYTHON -m scripts.cli "$@"
}

case "$1" in
    status)
        cli STATUS
        ;;
    add)
        [ -z "$2" ] && echo "用法: ./agent.sh add <股票代码>" && exit 1
        cli ADD "$2"
        ;;
    remove)
        [ -z "$2" ] && echo "用法: ./agent.sh remove <股票代码>" && exit 1
        cli REMOVE "$2"
        ;;
    clear)
        cli CLEAR_ALL
        ;;
    pause)
        cli PAUSE
        ;;
    resume)
        cli RESUME
        ;;
    cash)
        [ -z "$2" ] && echo "用法: ./agent.sh cash <金额>" && exit 1
        cli SET_CASH "$2"
        ;;
    log)
        LINES=${2:-50}
        tail -"$LINES" data/logs/event_log.jsonl 2>/dev/null || echo "暂无日志"
        ;;
    report)
        if [ -n "$2" ]; then
            cat "data/reports/${2}_daily.json" 2>/dev/null || echo "该日期无日报"
        else
            LATEST=$(ls -t data/reports/ 2>/dev/null | head -1)
            if [ -n "$LATEST" ]; then
                echo "最新日报: $LATEST"
                echo "---"
                cat "data/reports/$LATEST"
            else
                echo "暂无日报"
            fi
        fi
        ;;
    restart)
        systemctl restart ai-t-agent
        sleep 1
        systemctl status ai-t-agent --no-pager
        ;;
    stop)
        systemctl stop ai-t-agent
        echo "服务已停止"
        ;;
    start)
        systemctl start ai-t-agent
        sleep 1
        systemctl status ai-t-agent --no-pager
        ;;
    running)
        systemctl status ai-t-agent --no-pager
        ;;
    cal)
        YEAR=${2:-$(date +%Y)}
        $PYTHON -m scripts.init_calendar --year "$YEAR"
        ;;
    *)
        echo "AI-T-Agent 管理脚本"
        echo ""
        echo "用法: ./agent.sh <命令> [参数]"
        echo ""
        echo "  status          查看账户/持仓/股票池现价/最近交易"
        echo "  add <代码>      添加股票到池"
        echo "  remove <代码>   移除股票（触发清仓）"
        echo "  clear           全部清仓清池"
        echo "  pause           暂停策略"
        echo "  resume          恢复交易"
        echo "  cash <金额>     调整资金"
        echo "  log [行数]      查看最近日志（默认50）"
        echo "  report [日期]   查看日报（默认最新）"
        echo "  restart         重启服务"
        echo "  stop            停止服务"
        echo "  start           启动服务"
        echo "  running         查看服务状态"
        echo "  cal <年份>      生成交易日历"
        ;;
esac
