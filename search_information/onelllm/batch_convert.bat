@echo off
chcp 65001 >nul
echo ========================================
echo OneFileLLM 批量转换工具
echo ========================================
echo.

setlocal enabledelayedexpansion

cd /d "%~dp0"

:: 创建输出目录
if not exist "output" mkdir output

:: 检查URL列表文件
if not exist "urls.txt" (
    echo 错误: 未找到 urls.txt 文件
    echo.
    echo 请创建 urls.txt 文件，每行一个URL，例如:
    echo   https://example.com/article1
    echo   https://github.com/user/repo1
    echo   https://example.com/article2
    echo.
    pause
    exit /b 1
)

echo 开始批量转换...
echo.

set count=0
for /f "tokens=*" %%a in (urls.txt) do (
    set /a count+=1
    set url=%%a
    
    :: 从URL生成文件名
    for %%b in ("%%a") do set filename=%%~nb
    set filename=!filename:~0,50!
    
    echo [!count!] 正在转换: %%a
    echo     输出文件: output\!filename!.txt
    
    cd OneFileLLM
    python onefilellm.py "%%a" -o "../output/!filename!.txt" 2>nul
    cd ..
    
    if !errorlevel! equ 0 (
        echo     状态: 成功
    ) else (
        echo     状态: 失败
    )
    echo.
)

echo ========================================
echo 批量转换完成!
echo 共处理 !count! 个URL
echo 输出目录: %~dp0output\
echo ========================================
echo.
echo 提示: 生成的文本文件可以直接复制到 Obsidian 知识库中
echo.
pause
