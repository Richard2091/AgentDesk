# AgentDesk Windows 执行器启动脚本
$env:PYTHONPATH = Split-Path $PSScriptRoot -Parent
$env:AGENTDESK_SHARED_SECRET = "agentdesk-remote-2026"
$env:AGENTDESK_NETWORK_HOST = "127.0.0.1"
$env:AGENTDESK_NETWORK_PORT = "8765"

Write-Host "Starting AgentDesk Executor on $($env:AGENTDESK_NETWORK_HOST):$($env:AGENTDESK_NETWORK_PORT)"
Write-Host "Shared secret: [configured]"
py -3 -m windows_executor.network_main
