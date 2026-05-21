@echo off
chcp 65001 >nul
echo ========================================
echo OneFileLLM 安装脚本
echo ========================================
echo.

echo [1/4] 克隆 OneFileLLM 仓库...
cd /d "%~dp0"
git clone https://github.com/jimmc444/OneFileLLM.git
if %errorlevel% neq 0 (
    echo 错误: 克隆仓库失败，请检查网络连接
    pause
    exit /b 1
)
echo 仓库克隆成功!
echo.

echo [2/4] 进入项目目录...
cd OneFileLLM
echo.

echo [3/4] 安装 Python 依赖...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo 错误: 安装依赖失败
    pause
    exit /b 1
)
echo 依赖安装成功!
echo.

echo [4/4] 验证安装...
python onefilellm.py --help
if %errorlevel% neq 0 (
    echo 警告: 验证失败，但安装可能已完成
)
echo.

echo ========================================
echo OneFileLLM 安装完成!
echo ========================================
echo.
echo 使用方法:
echo   1. 网页转文本: python onefilellm.py https://example.com
echo   2. GitHub仓库: python onefilellm.py https://github.com/user/repo
echo   3. 本地文件: python onefilellm.py path/to/file
echo.
echo 输出文件将保存在当前目录下的 output.txt
echo.
pause
