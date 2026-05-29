#!/bin/bash
# 一键测试所有服务
# 服务器地址: 188.166.249.182

SERVER="188.166.249.182"
USER="root"

echo "=========================================="
echo "投资决策系统 - 一键测试"
echo "=========================================="
echo "服务器: $SERVER"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试结果统计
TOTAL=0
PASSED=0
FAILED=0

# 测试函数
test_service() {
    local name=$1
    local command=$2
    
    TOTAL=$((TOTAL + 1))
    echo -n "测试 $name ... "
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 通过${NC}"
        PASSED=$((PASSED + 1))
        return 0
    else
        echo -e "${RED}✗ 失败${NC}"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

# 1. 检查服务器连接
echo "1. 检查服务器连接"
echo "----------------------------------------"
test_service "SSH连接" "ssh -o ConnectTimeout=5 $USER@$SERVER 'echo ok'"

if [ $? -ne 0 ]; then
    echo -e "${RED}无法连接服务器，请检查网络和SSH配置${NC}"
    exit 1
fi
echo ""

# 2. 检查Docker服务
echo "2. 检查Docker服务"
echo "----------------------------------------"
test_service "Docker服务" "ssh $USER@$SERVER 'docker info'"
echo ""

# 3. 检查容器状态
echo "3. 检查容器状态"
echo "----------------------------------------"
ssh $USER@$SERVER 'docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(trendradar|analyser|invest|feedback|notification|dashboard|semantic)"'
echo ""

# 4. 测试服务健康状态
echo "4. 测试服务健康状态"
echo "----------------------------------------"
test_service "通知中心(5050)" "ssh $USER@$SERVER 'curl -s http://localhost:5050/health | grep -q ok'"
test_service "仪表盘(5060)" "ssh $USER@$SERVER 'curl -s http://localhost:5060/api/health | grep -q ok'"
test_service "投资后端(5000)" "ssh $USER@$SERVER 'curl -s http://localhost:5000/health | grep -q ok'"
echo ""

# 5. 检查数据库
echo "5. 检查数据库"
echo "----------------------------------------"
test_service "热榜数据库" "ssh $USER@$SERVER 'docker exec trendradar ls /app/data/*.db'"
test_service "分析数据库" "ssh $USER@$SERVER 'docker exec analyser ls /app/data/*.db'"
test_service "投资数据库" "ssh $USER@$SERVER 'docker exec invest-backend ls /app/data/*.db'"
echo ""

# 6. 查看最近日志（检查是否有错误）
echo "6. 检查最近日志（是否有错误）"
echo "----------------------------------------"
for container in trendradar analyser invest-backend feedback-learner; do
    ERROR_COUNT=$(ssh $USER@$SERVER "docker logs --tail 100 $container 2>&1 | grep -i 'error\|exception\|fail' | wc -l")
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo -e "$container: ${YELLOW}发现 $ERROR_COUNT 个错误/异常${NC}"
    else
        echo -e "$container: ${GREEN}无错误${NC}"
    fi
done
echo ""

# 7. 检查资源使用
echo "7. 检查资源使用"
echo "----------------------------------------"
ssh $USER@$SERVER 'docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep -E "(trendradar|analyser|invest|feedback|notification|dashboard|semantic)"'
echo ""

# 8. 检查磁盘空间
echo "8. 检查磁盘空间"
echo "----------------------------------------"
ssh $USER@$SERVER 'df -h / | tail -1 | awk "{print \"已用: \" \$3 \" / 总计: \" \$2 \" (\" \$5 \")\"}"'
echo ""

# 测试结果汇总
echo "=========================================="
echo "测试结果汇总"
echo "=========================================="
echo "总测试数: $TOTAL"
echo -e "通过: ${GREEN}$PASSED${NC}"
echo -e "失败: ${RED}$FAILED${NC}"

if [ $FAILED -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ 所有测试通过！系统运行正常。${NC}"
    exit 0
else
    echo ""
    echo -e "${YELLOW}⚠ 有 $FAILED 个测试失败，请检查相关服务。${NC}"
    exit 1
fi
