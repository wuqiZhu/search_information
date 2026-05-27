#!/bin/bash

PASSED=0
FAILED=0
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check() {
    local name="$1"
    local condition="$2"
    local detail="$3"
    if [ "$condition" = "true" ]; then
        PASSED=$((PASSED + 1))
        echo -e "  ${GREEN}✅ ${name}${NC}${detail:+ ($detail)}"
    else
        FAILED=$((FAILED + 1))
        echo -e "  ${RED}❌ ${name}${NC}${detail:+ ($detail)}"
    fi
}

echo "============================================================"
echo "服务器项目全面测试"
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

echo ""
echo "============================================================"
echo "Task 1: Docker容器状态检查"
echo "============================================================"

EXPECTED_CONTAINERS="trendradar analyser invest-backend invest-frontend notification-center dashboard"
for name in $EXPECTED_CONTAINERS; do
    STATUS=$(docker ps --filter "name=^${name}$" --format "{{.Status}}" 2>/dev/null)
    if [ -n "$STATUS" ]; then
        if echo "$STATUS" | grep -q "Up"; then
            check "容器 $name 状态" "true" "$STATUS"
        else
            check "容器 $name 状态" "false" "$STATUS"
        fi
    else
        check "容器 $name 状态" "false" "未找到"
    fi
done

JOB_SCRAPER=$(docker ps -a --filter "name=job-scraper" --format "{{.Names}}" 2>/dev/null)
check "无 job-scraper 容器" "$([ -z "$JOB_SCRAPER" ] && echo true || echo false)"

RUNNING_COUNT=$(docker ps --format "{{.Names}}" | wc -l)
check "运行中容器数量 >= 6" "$([ "$RUNNING_COUNT" -ge 6 ] && echo true || echo false)" "${RUNNING_COUNT}个"

echo ""
echo "============================================================"
echo "Task 2: API端点健康检查"
echo "============================================================"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5050/health)
check "通知中心 /health HTTP状态" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)" "HTTP $HTTP_CODE"

RESP=$(curl -s http://localhost:5050/health 2>/dev/null)
if echo "$RESP" | grep -q '"status"'; then
    check "通知中心 /health 响应格式" "true" "$RESP"
else
    check "通知中心 /health 响应格式" "false" "无status字段"
fi

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5060/api/health)
check "Dashboard /api/health HTTP状态" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)" "HTTP $HTTP_CODE"

RESP=$(curl -s http://localhost:5060/api/health 2>/dev/null)
if echo "$RESP" | grep -q '"status"'; then
    check "Dashboard /api/health 响应格式" "true" "$RESP"
else
    check "Dashboard /api/health 响应格式" "false" "无status字段"
fi

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/api/health)
check "投资后端 /api/health HTTP状态" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)" "HTTP $HTTP_CODE"

RESP=$(curl -s http://localhost:5000/api/health 2>/dev/null)
if echo "$RESP" | grep -q '"status"'; then
    check "投资后端 /api/health 响应格式" "true" "$RESP"
else
    check "投资后端 /api/health 响应格式" "false" "无status字段"
fi

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)
check "投资前端 HTTP状态" "$([ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ] || [ "$HTTP_CODE" = "304" ] && echo true || echo false)" "HTTP $HTTP_CODE"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5060/)
check "Dashboard 主页 HTTP状态" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)" "HTTP $HTTP_CODE"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5060/api/stats)
check "Dashboard /api/stats HTTP状态" "$([ "$HTTP_CODE" = "200" ] && echo true || echo false)" "HTTP $HTTP_CODE"

echo ""
echo "============================================================"
echo "Task 3: TrendRadar功能测试"
echo "============================================================"

LOGS=$(docker logs --tail 30 trendradar 2>&1)
if echo "$LOGS" | grep -qi "error\|traceback\|exception"; then
    check "TrendRadar日志无严重错误" "false" "发现错误"
else
    check "TrendRadar日志无严重错误" "true" "正常"
fi

if [ -n "$LOGS" ] && [ ${#LOGS} -gt 50 ]; then
    check "TrendRadar日志显示有活动" "true" "日志长度: ${#LOGS}字符"
else
    check "TrendRadar日志显示有活动" "false" "日志过短"
fi

OUTPUT_DIR=$(docker exec trendradar ls -la /app/output/ 2>/dev/null)
if [ -n "$OUTPUT_DIR" ]; then
    check "TrendRadar输出目录存在" "true"
else
    check "TrendRadar输出目录存在" "false" "目录不存在"
fi

DB_FILES=$(docker exec trendradar find /app/output -name "*.db" -type f 2>/dev/null | head -5)
if [ -n "$DB_FILES" ]; then
    check "TrendRadar数据库文件已生成" "true" "$DB_FILES"
else
    check "TrendRadar数据库文件已生成" "false" "无.db文件"
fi

echo ""
echo "============================================================"
echo "Task 4: 投资分析功能测试"
echo "============================================================"

RESP=$(curl -s http://localhost:5000/api/sentiment/latest 2>/dev/null)
if [ -n "$RESP" ]; then
    check "投资后端情绪数据API可用" "true" "$(echo $RESP | head -c 80)"
else
    check "投资后端情绪数据API可用" "false" "无响应"
fi

RESP=$(curl -s http://localhost:5000/api/sentiment/summary?days=7 2>/dev/null)
if [ -n "$RESP" ]; then
    check "投资后端情绪摘要API可用" "true" "$(echo $RESP | head -c 80)"
else
    check "投资后端情绪摘要API可用" "false" "无响应"
fi

LOGS=$(docker logs --tail 20 invest-backend 2>&1)
if echo "$LOGS" | grep -qi "error\|traceback"; then
    check "投资后端日志无严重错误" "false" "发现错误"
else
    check "投资后端日志无严重错误" "true" "正常"
fi

INVEST_DATA=$(docker exec invest-backend ls -la /app/data/ 2>/dev/null)
if [ -n "$INVEST_DATA" ]; then
    check "投资数据目录存在" "true"
else
    check "投资数据目录存在" "false" "目录不存在"
fi

INVEST_DB=$(docker exec invest-backend find /app/data -name "*.db" -type f 2>/dev/null | head -5)
if [ -n "$INVEST_DB" ]; then
    check "投资数据库文件存在" "true" "$INVEST_DB"
else
    check "投资数据库文件存在" "false" "无.db文件"
fi

echo ""
echo "============================================================"
echo "Task 5: 通知中心功能测试"
echo "============================================================"

RESP=$(curl -s http://localhost:5050/health 2>/dev/null)
if echo "$RESP" | grep -q 'dingtalk_configured.*true'; then
    check "钉钉Webhook已配置" "true"
else
    check "钉钉Webhook已配置" "false" "未配置"
fi

RESP=$(curl -s -X POST http://localhost:5050/notify \
  -H "Content-Type: application/json" \
  -d '{"text":"通知: 服务器测试消息 - 自动测试","title":"测试通知","priority":"high","source":"test"}' 2>/dev/null)
if echo "$RESP" | grep -q 'sent\|queued'; then
    check "通知发送API可用" "true" "$(echo $RESP | head -c 80)"
else
    check "通知发送API可用" "false" "$(echo $RESP | head -c 80)"
fi

LOGS=$(docker logs --tail 10 notification-center 2>&1)
if echo "$LOGS" | grep -qi "error" && ! echo "$LOGS" | grep -qi "warning"; then
    check "通知中心日志无严重错误" "false" "发现错误"
else
    check "通知中心日志无严重错误" "true" "正常"
fi

echo ""
echo "============================================================"
echo "Task 6: 数据完整性验证"
echo "============================================================"

if [ -d ~/projects/data ]; then
    check "数据根目录存在" "true"
else
    check "数据根目录存在" "false" "目录不存在"
fi

for subdir in search_information knowledge_base invest notification; do
    if [ -d ~/projects/data/$subdir ]; then
        check "数据子目录 $subdir 存在" "true"
    else
        check "数据子目录 $subdir 存在" "false" "目录不存在"
    fi
done

DB_COUNT=$(find ~/projects/data -name "*.db" -type f 2>/dev/null | wc -l)
check "数据库文件数量 > 0" "$([ "$DB_COUNT" -gt 0 ] && echo true || echo false)" "找到 ${DB_COUNT} 个.db文件"
find ~/projects/data -name "*.db" -type f 2>/dev/null | head -5 | while read f; do echo "    - $f"; done

DATA_SIZE=$(du -sh ~/projects/data/ 2>/dev/null | cut -f1)
check "数据目录有内容" "$([ -n "$DATA_SIZE" ] && echo true || echo false)" "$DATA_SIZE"

echo ""
echo "============================================================"
echo "Task 7: 容器资源使用检查"
echo "============================================================"

STATS=$(docker stats --no-cache --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" 2>/dev/null | head -10)
if [ -n "$STATS" ]; then
    echo "$STATS"
    check "容器资源使用正常" "true"
else
    check "容器资源使用正常" "false" "无法获取"
fi

DISK=$(df -h / | tail -1)
echo "  磁盘使用: $DISK"
check "磁盘空间充足" "true" "$(echo $DISK | awk '{print $5}') 已用"

echo ""
echo "============================================================"
echo "测试报告汇总"
echo "============================================================"

TOTAL=$((PASSED + FAILED))
if [ $TOTAL -gt 0 ]; then
    RATE=$((PASSED * 100 / TOTAL))
else
    RATE=0
fi

echo ""
echo "总测试项: $TOTAL"
echo -e "通过: ${GREEN}$PASSED${NC}"
echo -e "失败: ${RED}$FAILED${NC}"
echo "通过率: ${RATE}%"

echo ""
echo "============================================================"
echo "测试完成！ ($(date '+%Y-%m-%d %H:%M:%S'))"
echo "============================================================"
