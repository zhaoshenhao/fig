# start-qdrant.ps1 — 在 WSL Docker 中启动 Qdrant 向量库
# 端口: 6333 (HTTP), 6334 (gRPC)
# 用法: .\scripts\dev\start-qdrant.ps1

$ErrorActionPreference = "Stop"

Write-Host ">>> 启动 Qdrant (WSL Docker) ..."

$running = wsl bash -c "docker inspect kf-qdrant --format '{{.State.Status}}' 2>/dev/null"

if ($running -eq "running") {
    Write-Host ">>> kf-qdrant 已在运行中"
} else {
    wsl bash -c "docker start kf-qdrant 2>/dev/null || docker run -d --name kf-qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Qdrant 启动失败" -ForegroundColor Red
        exit 1
    }
    Write-Host ">>> kf-qdrant 容器已启动"
}

# 等待就绪
$maxWait = 15
for ($i = 0; $i -lt $maxWait; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:6333/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            Write-Host ">>> Qdrant 就绪 (尝试 $($i+1) 次)"
            exit 0
        }
    } catch {}
    Start-Sleep -Seconds 2
}

Write-Host "WARN: Qdrant 未在 ${maxWait}s 内就绪，继续启动其他服务..."
