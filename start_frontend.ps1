# 前端 dev server — 自动重启 PowerShell 脚本
# 由计划任务 ValuationFrontendV5 开机调用
# 关闭窗口/删除任务才真正停止

$WorkDir = "D:\长流水"
$LogDir = Join-Path $WorkDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# 绝对路径 — SYSTEM 账户 PATH 不含用户级 node/corepack，直接写 "node"/"pnpm" 会解析失败
$NodeExe = "D:\Program Files\nodejs\node.exe"
if (-not (Test-Path $NodeExe)) { $NodeExe = "node" }
$ViteJs = Join-Path $WorkDir "node_modules\vite\bin\vite.js"

$TraceFile = Join-Path $LogDir "frontend_trace.log"
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 脚本启动 | user=$([Environment]::UserName) | node=$NodeExe" |
    Add-Content -Path $TraceFile -Encoding UTF8

while ($true) {
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $outLog = Join-Path $LogDir "frontend_$ts.out.log"
    $errLog = Join-Path $LogDir "frontend_$ts.err.log"

    Write-Host ""
    Write-Host "════════════════════════════════════════════════"
    Write-Host "  [$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 启动前端 dev server (port 5174)"
    Write-Host "  崩溃后 10s 自动重启,关闭窗口才真正停止"
    Write-Host "  日志: frontend_$ts.out.log / .err.log"
    Write-Host "════════════════════════════════════════════════"
    Write-Host ""

    $exitCode = -1
    Push-Location $WorkDir
    try {
        # 注意: PS5.1 的 Start-Process 不允许 stdout/stderr 重定向到同一文件
        # --strictPort: 端口被占时直接失败(由看门狗接手), 不静默换端口
        $proc = Start-Process -FilePath $NodeExe `
            -ArgumentList "`"$ViteJs`"", "--port", "5174", "--strictPort" `
            -WorkingDirectory $WorkDir `
            -RedirectStandardOutput $outLog `
            -RedirectStandardError $errLog `
            -NoNewWindow `
            -PassThru `
            -Wait
        $exitCode = $proc.ExitCode
    } catch {
        "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Start-Process 异常: $($_.Exception.Message)" |
            Add-Content -Path $TraceFile -Encoding UTF8
    } finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "════════════════════════════════════════════════"
    Write-Host "  [$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 前端进程已退出 (exit code $exitCode)"
    Write-Host "  10s 后自动重启... 按 Ctrl+C 取消"
    Write-Host "════════════════════════════════════════════════"
    Start-Sleep -Seconds 10
}
