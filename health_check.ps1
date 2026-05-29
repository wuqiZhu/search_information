$score = 0
if (docker ps --filter "name=n8n" --format "{{.Status}}" | Select-String "Up") { $score += 20; Write-Host "? n8n 运行中" -ForegroundColor Green } else { Write-Host "? n8n 未运行" -ForegroundColor Red }
if (Get-Process python -ErrorAction SilentlyContinue) { $score += 20; Write-Host "? TrendRadar 运行中" -ForegroundColor Green } else { Write-Host "? TrendRadar 未运行" -ForegroundColor Red }
$todaySignals = Get-ChildItem "C:\Users\zhuxiangbo\Desktop\project\search_information\TrendRadar\data\signals\*.json" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge (Get-Date).Date } | Measure-Object | Select-Object -ExpandProperty Count
if ($todaySignals -gt 0) { $score += 20; Write-Host "? 今日抓到 $todaySignals 个信号" -ForegroundColor Green } else { Write-Host "? 今日无信号（可能无匹配或源异常）" -ForegroundColor Yellow }
$todayAnalyzed = Get-ChildItem "C:\Users\zhuxiangbo\Desktop\project\analyse_information\knowledge_base\analyzed\*.json" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge (Get-Date).Date } | Measure-Object | Select-Object -ExpandProperty Count
if ($todayAnalyzed -gt 0) { $score += 20; Write-Host "? 今日分析 $todayAnalyzed 篇文章" -ForegroundColor Green } else { Write-Host "? 今日无分析（检查RSS源或API）" -ForegroundColor Yellow }
$lastLog = Get-Content "C:\Users\zhuxiangbo\Desktop\project\search_information\TrendRadar\logs\trendradar.log" -Tail 5 -ErrorAction SilentlyContinue | Select-String "ERROR"
if (-not $lastLog) { $score += 20; Write-Host "? 日志无近期错误" -ForegroundColor Green } else { Write-Host "? 日志存在错误" -ForegroundColor Yellow }
Write-Host "`n健康评分: $score/100" -ForegroundColor Cyan
if ($score -ge 80) { Write-Host "结论: 系统运行正常" -ForegroundColor Green }
elseif ($score -ge 50) { Write-Host "结论: 部分异常，建议检查" -ForegroundColor Yellow }
else { Write-Host "结论: 系统异常，需要排查" -ForegroundColor Red }