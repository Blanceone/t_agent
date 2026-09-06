#!/bin/bash
# AI-T-Agent 部署脚本
set -e

APP_DIR=/opt/ai-t-agent

echo "=== AI-T-Agent 部署 ==="

# 1. 创建目录
mkdir -p $APP_DIR/{data/{account,memory,replay,logs,snapshots,reports},config,prompts}

# 2. 复制文件
cp -r src/ $APP_DIR/
cp -r config/ $APP_DIR/
cp -r prompts/ $APP_DIR/
cp -r scripts/ $APP_DIR/
cp pyproject.toml $APP_DIR/
cp .env $APP_DIR/

# 3. Python 虚拟环境
cd $APP_DIR
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

# 4. 初始化账户（如果不存在）
if [ ! -f data/account/state.json ]; then
    .venv/bin/python -m scripts.seed_account --codes 600584,002049 --cash 30000
fi

# 5. 生成交易日历
.venv/bin/python -m scripts.init_calendar --year 2026

# 6. 安装 systemd 服务
cp deploy/ai-t-agent.service /etc/systemd/system/
cp deploy/ai-t-agent-watchdog.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ai-t-agent ai-t-agent-watchdog

echo "=== 部署完成 ==="
echo "启动: systemctl start ai-t-agent"
echo "状态: systemctl status ai-t-agent"
echo "日志: journalctl -u ai-t-agent -f"
