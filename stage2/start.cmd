@echo off
REM Ручной запуск в консоли (для отладки). Штатно бот стартует задачей SigmaSteamBot.
cd /d %~dp0
"C:\Users\alex\gamebot\venv\Scripts\python.exe" supervisor.py
