@echo off
REM Остановить бота и задачу планировщика.
schtasks /End /TN SigmaSteamBot 2>nul
for /f "tokens=2" %%p in ('tasklist /fi "imagename eq pythonw.exe" /fo list ^| find "PID:"') do taskkill /PID %%p /F 2>nul
echo Остановлено. Задача остаётся зарегистрированной (Start-ScheduledTask -TaskName SigmaSteamBot чтобы поднять снова).
