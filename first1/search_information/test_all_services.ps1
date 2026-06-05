# One-click test all services - PowerShell version
# Server: 188.166.249.182

$SERVER = "188.166.249.182"
$USER = "root"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Investment System - One-Click Test" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Server: $SERVER"
Write-Host "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

$TOTAL = 0
$PASSED = 0
$FAILED = 0

function Test-Service {
    param(
        [string]$Name,
        [scriptblock]$TestBlock
    )
    
    $script:TOTAL++
    Write-Host -NoNewline "Test $Name ... "
    
    try {
        $result = & $TestBlock
        if ($LASTEXITCODE -eq 0 -or $result) {
            Write-Host "PASS" -ForegroundColor Green
            $script:PASSED++
            return $true
        } else {
            Write-Host "FAIL" -ForegroundColor Red
            $script:FAILED++
            return $false
        }
    } catch {
        Write-Host "FAIL: $_" -ForegroundColor Red
        $script:FAILED++
        return $false
    }
}

# 1. Check SSH connection
Write-Host "1. Check SSH Connection" -ForegroundColor Yellow
Write-Host "----------------------------------------"
$sshTest = Test-Service "SSH" { ssh -o ConnectTimeout=5 "$USER@$SERVER" "echo ok" }

if (-not $sshTest) {
    Write-Host "Cannot connect to server. Check network and SSH config." -ForegroundColor Red
    exit 1
}
Write-Host ""

# 2. Check Docker
Write-Host "2. Check Docker Service" -ForegroundColor Yellow
Write-Host "----------------------------------------"
Test-Service "Docker" { ssh "$USER@$SERVER" "docker info" }
Write-Host ""

# 3. Check containers
Write-Host "3. Check Container Status" -ForegroundColor Yellow
Write-Host "----------------------------------------"
ssh "$USER@$SERVER" "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E '(trendradar|analyser|invest|feedback|notification|dashboard|semantic)'"
Write-Host ""

# 4. Check service health
Write-Host "4. Check Service Health" -ForegroundColor Yellow
Write-Host "----------------------------------------"
Test-Service "NotificationCenter(5050)" { ssh "$USER@$SERVER" "curl -s http://localhost:5050/health | grep -q ok" }
Test-Service "Dashboard(5060)" { ssh "$USER@$SERVER" "curl -s http://localhost:5060/api/health | grep -q ok" }
Test-Service "InvestBackend(5000)" { ssh "$USER@$SERVER" "curl -s http://localhost:5000/health | grep -q ok" }
Write-Host ""

# 5. Check databases
Write-Host "5. Check Databases" -ForegroundColor Yellow
Write-Host "----------------------------------------"
Test-Service "TrendRadar DB" { ssh "$USER@$SERVER" "docker exec trendradar ls /app/data/*.db" }
Test-Service "Analyzer DB" { ssh "$USER@$SERVER" "docker exec analyser ls /app/data/*.db" }
Test-Service "Invest DB" { ssh "$USER@$SERVER" "docker exec invest-backend ls /app/data/*.db" }
Write-Host ""

# 6. Check logs for errors
Write-Host "6. Check Logs for Errors" -ForegroundColor Yellow
Write-Host "----------------------------------------"
$containers = @("trendradar", "analyser", "invest-backend", "feedback-learner")
foreach ($container in $containers) {
    $errorCount = ssh "$USER@$SERVER" "docker logs --tail 100 $container 2>&1 | grep -i 'error\|exception\|fail' | wc -l"
    if ([int]$errorCount -gt 0) {
        Write-Host "$container : Found $errorCount errors" -ForegroundColor Yellow
    } else {
        Write-Host "$container : No errors" -ForegroundColor Green
    }
}
Write-Host ""

# 7. Check resource usage
Write-Host "7. Check Resource Usage" -ForegroundColor Yellow
Write-Host "----------------------------------------"
ssh "$USER@$SERVER" "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' | grep -E '(trendradar|analyser|invest|feedback|notification|dashboard|semantic)'"
Write-Host ""

# 8. Check disk space
Write-Host "8. Check Disk Space" -ForegroundColor Yellow
Write-Host "----------------------------------------"
ssh "$USER@$SERVER" "df -h / | tail -1"
Write-Host ""

# Summary
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Total: $TOTAL"
Write-Host "Passed: $PASSED" -ForegroundColor Green
Write-Host "Failed: $FAILED" -ForegroundColor Red

if ($FAILED -eq 0) {
    Write-Host ""
    Write-Host "All tests passed! System is healthy." -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host "$FAILED tests failed. Please check." -ForegroundColor Yellow
    exit 1
}
