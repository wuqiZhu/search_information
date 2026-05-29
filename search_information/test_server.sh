#!/bin/bash
echo "=========================================="
echo "投资决策系统 - 服务器深度测试"
echo "=========================================="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

TOTAL=0
PASS=0
FAIL=0
WARN=0

check() {
    TOTAL=$((TOTAL+1))
    if eval "$1" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $2"
        PASS=$((PASS+1))
    else
        echo -e "${RED}✗${NC} $2"
        FAIL=$((FAIL+1))
    fi
}

warn() {
    WARN=$((WARN+1))
    echo -e "${YELLOW}⚠${NC} $1"
}

# ============================================================
echo "1. 容器状态"
# ============================================================
check "docker ps | grep -q trendradar" "trendradar 运行中"
check "docker ps | grep -q analyser" "analyser 运行中"
check "docker ps | grep -q invest-backend" "invest-backend 运行中"
check "docker ps | grep -q invest-frontend" "invest-frontend 运行中"
check "docker ps | grep -q notification-center" "notification-center 运行中"
check "docker ps | grep -q dashboard" "dashboard 运行中"
check "docker ps | grep -q feedback-learner" "feedback-learner 运行中"

# ============================================================
echo ""
echo "2. 服务健康检查"
# ============================================================
check "curl -s --max-time 5 http://localhost:5050/health | grep -q ok" "通知中心(5050)"
check "curl -s --max-time 5 http://localhost:5060/api/health | grep -q ok" "仪表盘(5060)"
check "curl -s --max-time 5 http://localhost:5000/api/health | grep -q ok" "投资后端(5000)"

# ============================================================
echo ""
echo "3. 环境变量检查"
# ============================================================
check "docker exec trendradar printenv MIMO_API_KEY | grep -q tp-" "trendradar MIMO_API_KEY"
check "docker exec analyser printenv MIMO_API_KEY | grep -q tp-" "analyser MIMO_API_KEY"
check "docker exec invest-backend printenv MIMO_API_KEY | grep -q tp-" "invest-backend MIMO_API_KEY"
check "docker exec feedback-learner printenv MIMO_API_KEY | grep -q tp-" "feedback-learner MIMO_API_KEY"

# ============================================================
echo ""
echo "4. Python 依赖检查（关键！）"
# ============================================================

echo "  --- trendradar ---"
check "docker exec trendradar python -c 'import requests'" "trendradar: requests"
check "docker exec trendradar python -c 'import yaml'" "trendradar: pyyaml"
check "docker exec trendradar python -c 'import bs4'" "trendradar: beautifulsoup4"
check "docker exec trendradar python -c 'import openai'" "trendradar: openai"
check "docker exec trendradar python -c 'import litellm'" "trendradar: litellm"

echo "  --- analyser ---"
check "docker exec analyser python -c 'import requests'" "analyser: requests"
check "docker exec analyser python -c 'import yaml'" "analyser: pyyaml"
check "docker exec analyser python -c 'import flask'" "analyser: flask"
check "docker exec analyser python -c 'import openai'" "analyser: openai"
check "docker exec analyser python -c 'import litellm'" "analyser: litellm"
check "docker exec analyser python -c 'import chromadb'" "analyser: chromadb"
check "docker exec analyser python -c 'import tqdm'" "analyser: tqdm"
check "docker exec analyser python -c 'import tenacity'" "analyser: tenacity"

echo "  --- invest-backend ---"
check "docker exec invest-backend python -c 'import requests'" "invest: requests"
check "docker exec invest-backend python -c 'import yaml'" "invest: pyyaml"
check "docker exec invest-backend python -c 'import pandas'" "invest: pandas"
check "docker exec invest-backend python -c 'import numpy'" "invest: numpy"
check "docker exec invest-backend python -c 'import openai'" "invest: openai"
check "docker exec invest-backend python -c 'import litellm'" "invest: litellm"
check "docker exec invest-backend python -c 'import tenacity'" "invest: tenacity"
check "docker exec invest-backend python -c 'import tqdm'" "invest: tqdm"
check "docker exec invest-backend python -c 'import chromadb'" "invest: chromadb"

echo "  --- feedback-learner ---"
check "docker exec feedback-learner python -c 'import requests'" "feedback: requests"
check "docker exec feedback-learner python -c 'import yaml'" "feedback: pyyaml"
check "docker exec feedback-learner python -c 'import psutil'" "feedback: psutil"
check "docker exec feedback-learner python -c 'import openai'" "feedback: openai"

# ============================================================
echo ""
echo "5. 数据库文件检查"
# ============================================================
check "docker exec trendradar sh -c 'ls /app/output/news/*.db'" "热榜数据库"
check "docker exec analyser ls /app/shared/data/analyzer.db" "分析数据库"
check "docker exec invest-backend ls /app/data/fund_data.db" "投资数据库"

# ============================================================
echo ""
echo "6. 核心模块导入检查"
# ============================================================
check "docker exec analyser python -c 'from analyzer.ai_analyzer import AIAnalyzer'" "analyser: AIAnalyzer"
check "docker exec analyser python -c 'from analyzer.rag_retriever import RAGRetriever'" "analyser: RAGRetriever"
check "docker exec invest-backend python -c 'import sys; sys.path.insert(0, \"/app/scripts\"); from ai_sentiment_analyzer import AISentimentAnalyzer'" "invest: AISentimentAnalyzer"
check "docker exec invest-backend python -c 'import sys; sys.path.insert(0, \"/app/scripts\"); import model_router'" "invest: model_router模块"
check "docker exec invest-backend python -c 'import sys; sys.path.insert(0, \"/app/scripts\"); from ai_gateway import DeepSeekCircuitBreaker'" "invest: ai_gateway"

# ============================================================
echo ""
echo "7. 网络连通性检查"
# ============================================================
check "docker exec trendradar python -c \"import requests; r=requests.get('https://token-plan-cn.xiaomimimo.com/v1/models', headers={'Authorization': 'Bearer ' + (__import__('os').getenv('MIMO_API_KEY',''))}, timeout=5); print(r.status_code)\" 2>/dev/null | grep -q 200" "MiMo API 可达"

# ============================================================
echo ""
echo "8. 日志错误检查"
# ============================================================
TRENDAR_ERRORS=$(docker logs trendradar --tail 50 2>&1 | grep -ic "error\|exception\|traceback" || true)
ANALYSER_ERRORS=$(docker logs analyser --tail 50 2>&1 | grep -ic "error\|exception\|traceback" || true)
INVEST_ERRORS=$(docker logs invest-backend --tail 50 2>&1 | grep -ic "error\|exception\|traceback" || true)
FEEDBACK_ERRORS=$(docker logs feedback-learner --tail 50 2>&1 | grep -ic "error\|exception\|traceback" || true)

if [ "$TRENDAR_ERRORS" -gt 5 ]; then
    warn "trendradar 最近50行有 $TRENDAR_ERRORS 个错误"
else
    check "true" "trendradar 日志正常"
fi

if [ "$ANALYSER_ERRORS" -gt 5 ]; then
    warn "analyser 最近50行有 $ANALYSER_ERRORS 个错误"
else
    check "true" "analyser 日志正常"
fi

if [ "$INVEST_ERRORS" -gt 5 ]; then
    warn "invest 最近50行有 $INVEST_ERRORS 个错误"
else
    check "true" "invest 日志正常"
fi

if [ "$FEEDBACK_ERRORS" -gt 5 ]; then
    warn "feedback 最近50行有 $FEEDBACK_ERRORS 个错误"
else
    check "true" "feedback 日志正常"
fi

# ============================================================
echo ""
echo "=========================================="
echo "结果: $PASS/$TOTAL 通过, $FAIL 失败, $WARN 警告"
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✓ 系统全部正常！${NC}"
else
    echo -e "${RED}✗ $FAIL 项需要修复${NC}"
    echo ""
    echo "常见修复命令："
    echo "  # 重建容器（安装新依赖后必须）"
    echo "  cd /root/projects && docker compose build && docker compose up -d"
    echo ""
    echo "  # 查看容器日志"
    echo "  docker logs invest-backend --tail 100"
    echo "  docker logs analyser --tail 100"
fi
echo "=========================================="
