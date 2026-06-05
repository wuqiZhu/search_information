@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo 统一数据库初始化脚本
echo ========================================
echo.

echo 正在创建数据库目录...
if not exist "data" mkdir "data"

echo 正在初始化数据库表...
python init_database.py

echo.
echo ========================================
echo 初始化完成！
echo ========================================
echo.
echo 数据库位置: %~dp0data\system.db
echo.
pause
