$ErrorActionPreference = "Stop"
$env:PYTHONPATH = (Get-Location).Path
if (-not $env:AGENTDESK_SHARED_SECRET) {
    $env:AGENTDESK_SHARED_SECRET = "local-test-secret"
}
python -m control_layer.main
if ($LASTEXITCODE -ne 0) {
    throw "能力发现启动失败，退出码：$LASTEXITCODE"
}
