@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo 启动智能通知中心 API 服务器
echo ========================================
echo.

echo 正在启动服务器...
python notification_api.py --host 0.0.0.0 --port 8080 --log-level INFO

echo.
echo 服务器已停止
pause
