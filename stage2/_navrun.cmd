@echo off
REM Запускается задачей SigmaNav в интерактивной сессии. Аргументы берёт из nav_cmd.txt.
cd /d C:\Users\alex\gamebot\stage2
set "ARGS="
set /p ARGS=<nav_cmd.txt
"C:\Users\alex\gamebot\venv\Scripts\python.exe" nav.py %ARGS% > nav_out.txt 2>&1
