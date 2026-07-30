@echo off
chcp 65001 >nul
setlocal

set TASK_NAME=ValuationEngineV5
set "PS1_PATH=D:\长流水\估值重构引擎_V5\start_backend.ps1"

echo ============================================
echo  Register Task: %TASK_NAME%
echo  Script: %PS1_PATH%
echo ============================================
echo.

C:\Windows\System32\schtasks.exe /delete /tn "%TASK_NAME%" /f >nul 2>&1

C:\Windows\System32\schtasks.exe /create /tn "%TASK_NAME%" /tr "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%PS1_PATH%\"" /sc onstart /ru system /rl highest /f

if %ERRORLEVEL% EQU 0 (
  echo.
  echo [OK] Task registered successfully.
  echo.
) else (
  echo.
  echo [FAIL] Error %ERRORLEVEL%. Please run as Administrator.
)

echo.
pause
