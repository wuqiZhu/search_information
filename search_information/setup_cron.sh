#!/bin/bash

echo "============================================================"
echo "设置定时任务"
echo "============================================================"

CRON_FILE="/tmp/crontab_backup"
crontab -l > "$CRON_FILE" 2>/dev/null

add_cron() {
    local schedule="$1"
    local command="$2"
    local comment="$3"
    
    if grep -qF "$command" "$CRON_FILE"; then
        echo "已存在: $comment"
    else
        echo "# $comment" >> "$CRON_FILE"
        echo "$schedule $command" >> "$CRON_FILE"
        echo "已添加: $comment"
    fi
}

add_cron "0 8 * * *" "cd ~/projects/invest/scripts && python daily.py --morning --notify --quiet >> ~/projects/data/logs/daily.log 2>&1" "每日晨报(早上8点)"

add_cron "0 */2 * * *" "cd ~/projects/search_information/search_information/TrendRadar && python main.py >> ~/projects/data/logs/trendradar.log 2>&1" "TrendRadar采集(每2小时)"

add_cron "0 2 * * *" "find ~/projects/data -name '*.db' -mtime +30 -exec gzip {} \\;" "数据库压缩(凌晨2点)"

crontab "$CRON_FILE"
rm "$CRON_FILE"

echo ""
echo "============================================================"
echo "当前定时任务列表："
echo "============================================================"
crontab -l
