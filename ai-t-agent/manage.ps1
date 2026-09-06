# AI-T-Agent 管理脚本
# 用法: .\manage.ps1 <命令> [参数]
#
# 命令:
#   status          查看账户/持仓/股票池现价/最近交易
#   add <代码>      添加股票到池 (如: .\manage.ps1 add 002185)
#   remove <代码>   移除股票 (触发清仓)
#   clear           全部清仓清池
#   pause           暂停策略
#   resume          恢复交易
#   cash <金额>     调整资金
#   log [行数]      查看最近日志 (默认50行)
#   report [日期]   查看日报
#   restart         重启服务
#   stop            停止服务
#   running         查看服务状态

param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet("status","add","remove","clear","pause","resume","cash","log","report","restart","stop","running")]
    [string]$Command,

    [Parameter(Position=1)]
    [string]$Arg = ""
)

$KEY = "C:\Users\13979\Desktop\notes\lxh的秘钥.pem"
$SERVER = "root@8.137.174.58"
$REMOTE_DIR = "/opt/ai-t-agent"
$CLI = "cd $REMOTE_DIR && PYTHONPATH=src .venv/bin/python -m scripts.cli"

function Run-Remote($cmd) {
    ssh -o StrictHostKeyChecking=no -i $KEY $SERVER $cmd
}

switch ($Command) {
    "status" {
        Run-Remote "$CLI STATUS"
    }
    "add" {
        if (-not $Arg) { Write-Host "请提供股票代码，如: .\manage.ps1 add 002185"; exit 1 }
        Run-Remote "$CLI ADD $Arg"
    }
    "remove" {
        if (-not $Arg) { Write-Host "请提供股票代码，如: .\manage.ps1 remove 600584"; exit 1 }
        Run-Remote "$CLI REMOVE $Arg"
    }
    "clear" {
        Run-Remote "$CLI CLEAR_ALL"
    }
    "pause" {
        Run-Remote "$CLI PAUSE"
    }
    "resume" {
        Run-Remote "$CLI RESUME"
    }
    "cash" {
        if (-not $Arg) { Write-Host "请提供金额，如: .\manage.ps1 cash 50000"; exit 1 }
        Run-Remote "$CLI SET_CASH $Arg"
    }
    "log" {
        $lines = if ($Arg) { $Arg } else { "50" }
        Run-Remote "tail -$lines $REMOTE_DIR/data/logs/event_log.jsonl"
    }
    "report" {
        if ($Arg) {
            Run-Remote "cat $REMOTE_DIR/data/reports/${Arg}_daily.json 2>/dev/null || echo '该日期无日报'"
        } else {
            Run-Remote "ls -t $REMOTE_DIR/data/reports/ 2>/dev/null | head -5; echo '---'; cat $REMOTE_DIR/data/reports/$(ls -t $REMOTE_DIR/data/reports/ 2>/dev/null | head -1) 2>/dev/null || echo '暂无日报'"
        }
    }
    "restart" {
        Run-Remote "systemctl restart ai-t-agent && sleep 1 && systemctl status ai-t-agent --no-pager"
    }
    "stop" {
        Run-Remote "systemctl stop ai-t-agent && echo '服务已停止'"
    }
    "running" {
        Run-Remote "systemctl status ai-t-agent --no-pager"
    }
}
