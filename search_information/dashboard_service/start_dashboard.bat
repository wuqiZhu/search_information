@echo off
echo ========================================
echo   统一 Web Dashboard 启动
echo ========================================
echo.

cd /d "%~dp0.."

echo 启动 Dashboard 服务...
echo 访问地址: http://localhost:5060
echo.

python -m dashboard_service.server

pause
