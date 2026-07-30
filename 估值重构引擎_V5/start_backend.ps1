# 估值引擎后端 — 自动重启 PowerShell 脚本
# 用法: powershell -File start_backend.ps1
# 关闭窗口才真正停止

$WorkDir = "D:\长流水\估值重构引擎_V5"
$LogDir = Join-Path $WorkDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# SYSTEM 账户下无 UI host,跳过窗口标题设置
try { $host.UI.RawUI.WindowTitle = "估值引擎后端" } catch {}

while ($true) {
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $logFile = Join-Path $LogDir "backend_$ts.log"

    Write-Host ""
    Write-Host "════════════════════════════════════════════════"
    Write-Host "  [$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 启动估值引擎后端 (port 8080)"
    Write-Host "  崩溃后 10s 自动重启,关闭窗口才真正停止"
    Write-Host "  日志: $logFile"
    Write-Host "════════════════════════════════════════════════"
    Write-Host ""

    Push-Location $WorkDir
    try {
        # 用 cmd /c 启动,方便重定向
        $proc = Start-Process -FilePath "python" `
            -ArgumentList "-u", "-m", "uvicorn", "valuation_app.server:app", "--host", "0.0.0.0", "--port", "8080" `
            -WorkingDirectory $WorkDir `
            -RedirectStandardOutput $logFile `
            -RedirectStandardError $logFile `
            -NoNewWindow `
            -PassThru `
            -Wait

        $exitCode = $proc.ExitCode
    } finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "════════════════════════════════════════════════"
    Write-Host "  [$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 后端进程已退出 (exit code $exitCode)"
    Write-Host "  10s 后自动重启... 按 Ctrl+C 取消"
    Write-Host "════════════════════════════════════════════════"
    Start-Sleep -Seconds 10
}
