@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM  SigmaSteamBot — установка на Windows-VM.
REM  Запускать в cmd ОТ АДМИНИСТРАТОРА из папки deploy\.
REM
REM  Опции:  setup.bat  [BASE_DIR]  [/autologon USER PASSWORD]
REM  По умолчанию BASE_DIR = %USERPROFILE%\sigmabot
REM ============================================================================

set "SRC=%~dp0"
set "BASE=%~1"
if "%BASE%"=="" set "BASE=%USERPROFILE%\sigmabot"

set "AUTO="
set "AUSER=%USERNAME%"
set "APASS="
if /I "%~2"=="/autologon" (
  set "AUTO=1"
  set "AUSER=%~3"
  set "APASS=%~4"
)

echo.
echo === SigmaSteamBot setup ===
echo   source : %SRC%
echo   target : %BASE%
echo.

REM --- найти python ---
set "PYEXE="
for %%P in ("py -3" "python" "python3") do (
  %%~P --version >nul 2>&1 && set "PYEXE=%%~P" && goto :gotpy
)
echo [ERR] Python 3 не найден в PATH. Установите с python.org (галочка "Add to PATH").
exit /b 1
:gotpy
echo [ok] python: %PYEXE%

REM --- venv ---
if not exist "%BASE%\venv\Scripts\python.exe" (
  echo [..] создаю venv в %BASE%\venv
  mkdir "%BASE%" 2>nul
  %PYEXE% -m venv "%BASE%\venv" || (echo [ERR] venv не создан & exit /b 1)
)
echo [..] pip install
"%BASE%\venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"%BASE%\venv\Scripts\python.exe" -m pip install -r "%SRC%requirements.txt" || (echo [ERR] pip install & exit /b 1)
echo [ok] зависимости установлены

REM --- копирование файлов ---
mkdir "%BASE%\logs" 2>nul
copy /Y "%SRC%app\*.py"  "%BASE%\" >nul
copy /Y "%SRC%app\*.cmd" "%BASE%\" >nul
copy /Y "%SRC%app\*.ps1" "%BASE%\" >nul
copy /Y "%SRC%install.ps1" "%BASE%\" >nul
if not exist "%BASE%\config.json" (
  copy /Y "%SRC%app\config.example.json" "%BASE%\config.json" >nul
  echo [ok] создан %BASE%\config.json  — ОТРЕДАКТИРУЙТЕ его (token, allowed_user_ids, proxy, пути, base_dir)
) else (
  echo [--] config.json уже есть, не трогаю
)

REM --- задачи планировщика / автологон ---
set "PSARGS=-BaseDir "%BASE%""
if defined AUTO set "PSARGS=%PSARGS% -Autologon -User "%AUSER%" -Password "%APASS%""
powershell -NoProfile -ExecutionPolicy Bypass -File "%BASE%\install.ps1" %PSARGS%

echo.
echo === Дальше вручную ===
echo  1) Отредактируйте %BASE%\config.json
echo  2) Проверьте: "%BASE%\venv\Scripts\python.exe" "%BASE%\selftest.py"
echo  3) Запуск:   powershell Start-ScheduledTask -TaskName SigmaSteamBot
echo.
endlocal
