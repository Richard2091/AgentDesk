# AgentDesk 反向 SSH 隧道启动脚本
# 将本地 8765 端口转发到 CodexServer 的 127.0.0.1:8765
# 用法: .\deploy\start-tunnel.ps1

$SSH_HOST = "ccny"
$LOCAL_PORT = 8765
$REMOTE_PORT = 8765
$LOG_FILE = "$env:USERPROFILE\.agentdesk-tunnel.log"

function Write-Log {
    param([string]$Message)
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message" | Add-Content -Path $LOG_FILE
    Write-Host $Message
}

function Start-Tunnel {
    Write-Log "Starting reverse SSH tunnel..."
    Write-Log "Local: 127.0.0.1:$LOCAL_PORT -> Remote(ccny): 127.0.0.1:$REMOTE_PORT"
    
    while ($true) {
        try {
            Write-Log "Connecting..."
            # Reverse tunnel: -R binds remote port to forward to local
            ssh -N -R "${REMOTE_PORT}:127.0.0.1:${LOCAL_PORT}" `
                -o ServerAliveInterval=30 -o ServerAliveCountMax=3 `
                -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no `
                $SSH_HOST 2>&1 | ForEach-Object { Write-Log $_ }
        }
        catch {
            Write-Log "Connection error: $_"
        }
        Write-Log "Disconnected. Reconnecting in 5 seconds..."
        Start-Sleep -Seconds 5
    }
}

Start-Tunnel
