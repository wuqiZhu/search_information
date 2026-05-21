@echo off
chcp 65001 >nul
title 信息处理流水线 - 启动控制台
color 0A

echo.
echo  ███████╗██╗ ██████╗ ███╗   ██╗ █████╗ ██╗
echo  ██╔════╝██║██╔════╝ ████╗  ██║██╔══██╗██║
echo  ███████╗██║██║  ███╗██╔██╗ ██║███████║██║
echo  ╚════██║██║██║   ██║██║╚██╗██║██╔══██║██║
echo  ███████║██║╚██████╔╝██║ ╚████║██║  ██║███████╗
echo  ╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝
echo.
echo  「信号 → 摘要 → 动作」自动化信息处理流水线
echo.
echo ========================================
echo.

:menu
echo 请选择操作:
echo.
echo  [1] 安装所有依赖
echo  [2] 启动所有服务
echo  [3] 停止所有服务
echo  [4] 查看服务状态
echo  [5] 启动 TrendRadar
echo  [6] 启动 BestBlogs (Docker)
echo  [7] 启动 n8n (Docker)
echo  [8] 安装 OneFileLLM
echo  [9] 导入 n8n 工作流
echo  [0] 退出
echo.
set /p choice=请输入选项 [0-9]:

if "%choice%"=="1" goto install
if "%choice%"=="2" goto start_all
if "%choice%"=="3" goto stop_all
if "%choice%"=="4" goto status
if "%choice%"=="5" goto start_trendradar
if "%choice%"=="6" goto start_bestblogs
if "%choice%"=="7" goto start_n8n
if "%choice%"=="8" goto install_onelllm
if "%choice%"=="9" goto import_workflow
if "%choice%"=="0" goto exit
echo 无效选项，请重新选择
goto menu

:install
echo.
echo ========================================
echo 安装所有依赖
echo ========================================
echo.

echo [1/3] 安装 TrendRadar Python 依赖...
cd trendradar
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
cd ..

echo.
echo [2/3] 拉取 Docker 镜像...
echo 拉取 BestBlogs 镜像...
docker pull ghcr.io/bestblogs/bestblogs:latest
echo 拉取 n8n 镜像...
docker pull n8nio/n8n:latest

echo.
echo [3/3] 安装 OneFileLLM...
cd onelllm
call install.bat
cd ..

echo.
echo ========================================
echo 所有依赖安装完成!
echo ========================================
echo.
pause
goto menu

:start_all
echo.
echo ========================================
echo 启动所有服务
echo ========================================
echo.

echo [1/3] 启动 BestBlogs...
cd bestblogs
docker-compose up -d
cd..

echo [2/3] 启动 n8n...
cd n8n
docker-compose up -d
cd..

echo [3/3] 启动 TrendRadar...
start "TrendRadar" cmd /k "cd trendradar && python main.py"

echo.
echo ========================================
echo 所有服务已启动!
echo.
echo 访问地址:
echo   - BestBlogs: http://localhost:3000
echo   - n8n: http://localhost:5678
echo.
echo TrendRadar 将在后台运行，信号将自动推送到 n8n
echo ========================================
echo.
pause
goto menu

:stop_all
echo.
echo ========================================
echo 停止所有服务
echo ========================================
echo.

echo 停止 BestBlogs...
cd bestblogs
docker-compose down
cd..

echo 停止 n8n...
cd n8n
docker-compose down
cd..

echo 停止 TrendRadar...
taskkill /FI "WINDOWTITLE eq TrendRadar*" /F 2>nul

echo.
echo ========================================
echo 所有服务已停止!
echo ========================================
echo.
pause
goto menu

:status
echo.
echo ========================================
echo 服务状态
echo ========================================
echo.

echo Docker 容器状态:
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr /I "bestblogs n8n"
echo.

echo 端口占用情况:
netstat -an | findstr ":3000 :5678"
echo.

pause
goto menu

:start_trendradar
echo.
echo ========================================
echo 启动 TrendRadar
echo ========================================
echo.
cd trendradar
python main.py
cd..
pause
goto menu

:start_bestblogs
echo.
echo ========================================
echo 启动 BestBlogs
echo ========================================
echo.
cd bestblogs
docker-compose up -d
echo.
echo BestBlogs 已启动!
echo 访问地址: http://localhost:3000
cd..
pause
goto menu

:start_n8n
echo.
echo ========================================
echo 启动 n8n
echo ========================================
echo.
cd n8n
docker-compose up -d
echo.
echo n8n 已启动!
echo 访问地址: http://localhost:5678
cd..
pause
goto menu

:install_onelllm
echo.
echo ========================================
echo 安装 OneFileLLM
echo ========================================
echo.
cd onelllm
call install.bat
cd..
pause
goto menu

:import_workflow
echo.
echo ========================================
echo 导入 n8n 工作流
echo ========================================
echo.
echo 请确保 n8n 已启动，然后:
echo 1. 打开 http://localhost:5678
echo 2. 登录 (默认账号: admin / n8n123)
echo 3. 点击左侧菜单 "Workflows"
echo 4. 点击 "Import from File"
echo 5. 选择文件: n8n\workflows\trendradar-to-bestblogs.json
echo.
echo 导入后，请配置以下环境变量:
echo   - DINGTALK_WEBHOOK: 钉钉机器人Webhook地址
echo   - DINGTALK_SECRET: 钉钉机器人签名密钥
echo   - EMAIL_USER: 发件邮箱
echo   - EMAIL_PASS: 邮箱密码/授权码
echo   - EMAIL_TO: 收件邮箱
echo.
pause
goto menu

:exit
echo.
echo 感谢使用，再见!
echo.
exit /b 0
