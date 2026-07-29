@echo off
REM 注册估值引擎后端到 Windows 任务计划,开机自启
REM 需要管理员权限运行

setlocal
set TASK_NAME=ValuationEngine_Backend
set PS1_PATH=D:\长流水\估值重构引擎_V5\start_backend.ps1

echo ════════════════════════════════════════════════
echo  注册任务: %TASK_NAME%
echo  启动脚本: %PS1_PATH%
echo ════════════════════════════════════════════════
echo.

REM 先删旧任务(如果存在)
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM 创建新任务:
REM   /sc onstart   开机时启动
REM   /ru system    以 SYSTEM 账户运行(无窗口)
REM   /rl highest   最高权限
schtasks /create /tn "%TASK_NAME%" ^
  /tr "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%PS1_PATH%\"" ^
  /sc onstart ^
  /ru system ^
  /rl highest ^
  /f

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ✓ 注册成功!下次开机会自动启动后端。
  echo.
  echo 常用命令:
  echo   立即启动:  schtasks /run /tn "%TASK_NAME%"
  echo   查看状态:  schtasks /query /tn "%TASK_NAME%"
  echo   停止:      schtasks /end /tn "%TASK_NAME%"
  echo   删除:      schtasks /delete /tn "%TASK_NAME%" /f
) else (
  echo.
  echo ✗ 注册失败,错误码 %ERRORLEVEL%
  echo  需要管理员权限运行此脚本(右键 -^> 以管理员身份运行)
)

echo.
pause
