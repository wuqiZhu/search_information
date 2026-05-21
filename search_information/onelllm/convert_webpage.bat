@echo off
chcp 65001 >nul
echo ========================================
echo OneFileLLM 网页转换工具
echo ========================================
echo.

if "%~1"=="" (
    echo 用法: convert_webpage.bat [URL] [输出文件名]
    echo.
    echo 示例:
    echo   convert_webpage.bat https://example.com
    echo   convert_webpage.bat https://example.com output.txt
    echo.
    pause
    exit /b 1
)

set URL=%~1
set OUTPUT=%~2
if "%OUTPUT%"=="" set OUTPUT=output.txt

cd /d "%~dp0OneFileLLM"

echo 正在转换网页: %URL%
echo 输出文件: %OUTPUT%
echo.

python onefilellm.py "%URL%" -o "../output/%OUTPUT%"

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo 转换完成!
    echo 文件已保存到: %~dp0output\%OUTPUT%
    echo ========================================
) else (
    echo.
    echo 错误: 转换失败，请检查URL是否正确
)

echo.
pause
