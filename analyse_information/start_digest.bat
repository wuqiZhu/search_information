@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "analyzer\pipeline.py" --digest >> "shared\logs\scheduler.log" 2>&1