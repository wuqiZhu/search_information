@echo off
chcp 65001 >nul
echo ========================================
echo OneFileLLM 仓库转换工具
echo ========================================
echo.

if "%~1"=="" (
    echo 用法: convert_repo.bat [GitHub仓库URL] [输出文件名]
    echo.
    echo 示例:
    echo   convert_repo.bat https://github.com/torvalds/linux
    echo   convert_repo.bat https://github.com/torvalds/linux linux_kernel.txt
    echo.
    pause
    exit /b 1
)

set URL=%~1
set OUTPUT=%~2
if "%OUTPUT%"=="" set OUTPUT=repo_output.txt

cd /d "%~dp0OneFileLLM"

echo 正在转换仓库: %URL%
echo 输出文件: %OUTPUT%
echo 注意: 大型仓库转换可能需要较长时间...
echo.

python onefilellm.py "%URL%" -o "../output/%OUTPUT%"

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo 转换完成!
    echo 文件已保存到: %~dp0output\%OUTPUT%
    echo ========================================
    echo.
    echo 提示: 生成的文本文件可以直接导入到 Obsidian 中
    echo       作为知识库的一部分进行管理
) else (
    echo.
    echo 错误: 转换失败，请检查仓库URL是否正确
)

echo.
pause
