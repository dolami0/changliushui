@echo off
REM 估值引擎后端启动入口 — 调用 PowerShell 脚本实现自动重启
REM 双击此文件即可,无需管理员权限

powershell -NoProfile -ExecutionPolicy Bypass -File "D:\长流水\估值重构引擎_V5\start_backend.ps1"
