#!/bin/bash
# 日终备份脚本（cron 每日 15:30 执行）
APP_DIR=/opt/ai-t-agent
BACKUP_DIR=$APP_DIR/data/snapshots/$(date +%Y%m%d)
mkdir -p $BACKUP_DIR

cp $APP_DIR/data/account/state.json $BACKUP_DIR/ 2>/dev/null || true
cp $APP_DIR/data/memory/memory.db $BACKUP_DIR/ 2>/dev/null || true
cp $APP_DIR/config/default.yaml $BACKUP_DIR/

# 压缩当日 Replay
if [ -d "$APP_DIR/data/replay/$(date +%Y-%m-%d)" ]; then
    tar -czf $BACKUP_DIR/replay.tar.gz -C $APP_DIR/data/replay $(date +%Y-%m-%d)
fi

# 保留最近 30 日
find $APP_DIR/data/snapshots -maxdepth 1 -mtime +30 -exec rm -rf {} \; 2>/dev/null || true

echo "Backup done: $BACKUP_DIR"
