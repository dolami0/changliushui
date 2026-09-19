# 登录后自动打开前端 + 监控大屏入口
# 由计划任务 ValuationPortalsOpen 在用户登录时调用
# 逻辑: 先等两个端口就绪(服务开机已自启,通常秒级), 再用默认浏览器打开页面

$LogDir = "D:\长流水\logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$TraceFile = Join-Path $LogDir "portals_trace.log"
function Trace([string]$msg) {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg" | Add-Content -Path $TraceFile -Encoding UTF8
}

Trace "脚本启动 | user=$([Environment]::UserName)"

# 端口 → 页面 映射
$portals = @(
    @{ Port = 8080; Url = "http://localhost:8080/api/pipeline/dashboard/html" },
    @{ Port = 5174; Url = "http://localhost:5174" }
)

# 等待各端口就绪, 总超时 120 秒
$deadline = (Get-Date).AddSeconds(120)
foreach ($p in $portals) {
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $client = New-Object Net.Sockets.TcpClient
            $client.Connect("127.0.0.1", $p.Port)
            $ready = $client.Connected
            $client.Close()
        } catch { $ready = $false }
        if ($ready) { break }
        Start-Sleep -Seconds 2
    }
    $p.Ready = $ready
    Trace "端口 $($p.Port) 就绪=$ready"
}

# 稍等1秒让服务稳定, 然后打开页面
Start-Sleep -Seconds 1
foreach ($p in $portals) {
    if ($p.Ready) {
        try {
            Start-Process $p.Url
            Trace "已打开 $($p.Url)"
        } catch {
            Trace "打开失败 $($p.Url): $($_.Exception.Message)"
        }
        Start-Sleep -Milliseconds 800
    } else {
        Trace "跳过(端口未就绪) $($p.Url)"
    }
}

Trace "完成"
