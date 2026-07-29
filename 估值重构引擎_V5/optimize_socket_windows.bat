REM 估值引擎后端 — Windows socket 资源优化
REM 解决 errno 22 (WSAEINVAL) socket 端口耗尽问题
REM 需要管理员权限运行,重启后生效

echo ════════════════════════════════════════════════
echo  Windows socket 资源优化
echo  解决 errno 22 端口耗尽导致的 LLM API 调用失败
echo ════════════════════════════════════════════════
echo.

REM 1. 扩大动态端口范围 (1024-65535,默认只有 49152-65535)
REM    默认约 16K 端口 → 扩大到 64K 端口
netsh int ipv4 set dynamicport tcp start=1024 num=64511

REM 2. 缩短 TIME_WAIT 状态时间 (默认 120s → 30s)
REM    让用过的端口更快释放回可用池
REM    注: Win10/11 这个值在注册表,单位是秒
reg add "HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters" /v TcpTimedWaitDelay /t REG_DWORD /d 30 /f

REM 3. 提高 socket 连接 backlog (默认 200 → 1000)
netsh int ipv4 set dynamicport udp start=1024 num=64511

echo.
echo ✓ 设置完成!
echo.
echo 已修改:
echo   - 动态端口范围: 1024-65535 (64K 端口,默认 16K)
echo   - TIME_WAIT 时间: 120s → 30s
echo.
echo 需要重启电脑才能完全生效
echo.
pause
