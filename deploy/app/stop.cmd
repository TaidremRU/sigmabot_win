@echo off
REM Остановить бота (задача остаётся зарегистрированной).
schtasks /End /TN SigmaSteamBot 2>nul
for /f "tokens=2" %%p in ('tasklist /fi "imagename eq pythonw.exe" /fo list ^| find "PID:"') do taskkill /PID %%p /F 2>nul
echo stopped. Start again:  powershell Start-ScheduledTask -TaskName SigmaSteamBot
