# start-embed.ps1 — 本地启动 kf-embed 向量化微服务
# 端口: 8100
# 用法: .\scripts\dev\start-embed.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSCommandPath))

Write-Host ">>> 启动 kf-embed (端口 8100) ..."

# 检查是否已在运行
$existing = netstat -ano | Select-String ":8100 .*LISTENING"
if ($existing) {
    Write-Host "WARN: 端口 8100 已被占用，尝试停止旧进程..."
    $pidMatch = [regex]::Match($existing, '\d+$')
    if ($pidMatch.Success) {
        Stop-Process -Id $pidMatch.Value -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

# 设置环境变量
$env:EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
$env:EMBED_WARMUP = "1"
$env:FASTEMBED_CACHE_PATH = "$ROOT\.fastembed_cache"
$env:HF_ENDPOINT = "https://hf-mirror.com"

# 后台启动
$process = Start-Process -FilePath "uv" -ArgumentList "run", "uvicorn", "src.embed_service.app:app", "--host", "0.0.0.0", "--port", "8100" -WorkingDirectory $ROOT -NoNewWindow -PassThru

Write-Host ">>> kf-embed PID: $($process.Id)"

# 快速就绪检测
$maxWait = 30
for ($i = 0; $i -lt $maxWait; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8100/ready" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            Write-Host ">>> kf-embed 就绪 (尝试 $($i+1) 次)"
            exit 0
        }
    } catch {}
    Start-Sleep -Seconds 3
}

Write-Host "WARN: kf-embed 未在 ${maxWait}s x 3s 内就绪，模型可能仍在下载..."
Write-Host "WARN: 检查 uv run 控制台输出或 $env:TEMP\kf-embed-*.log"
