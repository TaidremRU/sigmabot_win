@echo off
chcp 65001 >nul
title Запуск SigmaSteamBot
REM ---------------------------------------------------------------------------
REM  Включает и запускает задачу планировщика SigmaSteamBot.
REM  Нужно после команды /stopbot из Telegram — она ОТКЛЮЧАЕТ задачу, поэтому
REM  сам по себе (авто-рестартом / при входе в систему) бот уже не поднимется.
REM ---------------------------------------------------------------------------

set "TASK=SigmaSteamBot"

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Требуются права администратора - перезапускаю с повышением...
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)

echo.
echo [1/2] Включаю задачу "%TASK%"...
schtasks /Change /TN "%TASK%" /ENABLE
echo.
echo [2/2] Запускаю задачу "%TASK%"...
schtasks /Run /TN "%TASK%"
echo.
timeout /t 4 /nobreak >nul
schtasks /Query /TN "%TASK%" /FO LIST | findstr /I "TaskName: Status:"
echo.
echo Готово. Бот поднимется за несколько секунд.
echo Проверить: команда /status в Telegram, либо логи supervisor.log в папке бота.
echo.
pause
