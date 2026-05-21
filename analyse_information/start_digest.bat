@echo off
chcp 65001 >nul
"C:\Users\zhuxiangbo\anaconda3\python.exe" "C:\Users\zhuxiangbo\Desktop\project\analyse_information\analyzer\pipeline.py" --digest >> "C:\Users\zhuxiangbo\Desktop\project\analyse_information\shared\logs\scheduler.log" 2>&1