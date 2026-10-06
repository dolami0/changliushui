# Lark fetcher - run every 30min via scheduled task
$WorkDir = 'D:\长流水\估值重构引擎_V5'
$LogDir = Join-Path $WorkDir 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$PythonExe = 'C:\Users\1\miniconda3\python.exe'
$ts = Get-Date -Format 'yyyyMMdd'
$logFile = Join-Path $LogDir "lark_fetcher_$ts.log"
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
"[$timestamp] lark fetch start" | Add-Content -Path $logFile -Encoding UTF8
Push-Location $WorkDir
try {
    $output = & $PythonExe -X utf8 -m src.tianjifeng.lark_fetcher 2>&1
    $output | Add-Content -Path $logFile -Encoding UTF8
    "[$timestamp] lark fetch done" | Add-Content -Path $logFile -Encoding UTF8
} catch {
    "[$timestamp] lark fetch error: $($_.Exception.Message)" | Add-Content -Path $logFile -Encoding UTF8
} finally {
    Pop-Location
}