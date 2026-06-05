@echo off
chcp 65001 >nul

REM ===========================================
REM analyse_information 自动运行批处理
REM 用于 Windows 任务计划定时执行
REM ===========================================

REM 设置工作目录
cd /d "%~dp0"

REM 创建日志目录（如果不存在）
if not exist "shared\logs" mkdir shared\logs

REM 记录启动时间
echo [%date% %time%] ========================================== >> shared\logs\scheduler.log
echo [%date% %time%] analyse_information RSS处理 启动 >> shared\logs\scheduler.log

REM 运行 RSS 拉取和分析
python analyzer\pipeline.py --rss >> shared\logs\scheduler.log 2>&1

REM 记录结束时间
echo [%date% %time%] analyse_information RSS处理 结束 >> shared\logs\scheduler.log
echo [%date% %time%] ========================================== >> shared\logs\scheduler.log