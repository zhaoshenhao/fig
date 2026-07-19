# start-api.ps1 — 本地启动 kf-api FastAPI 服务（chat 模式）
# 端口: 9000 (本地开发默认，避免与 Docker Compose 的 8000 冲突)
# 用法: .\scripts\dev\start-api.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSCommandPath))

Write-Host ">>> 启动 kf-api (端口 9000, mode=chat) ..."

# 检查是否已在运行
$existing = netstat -ano | Select-String ":9000 .*LISTENING"
if ($existing) {
    Write-Host "WARN: 端口 9000 已被占用，尝试停止旧进程..."
    $pidMatch = [regex]::Match($existing, '\d+$')
    if ($pidMatch.Success) {
        Stop-Process -Id $pidMatch.Value -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

# 加载 .env 变量
if (Test-Path "$ROOT\.env") {
    Write-Host ">>> 从 .env 加载环境变量"
}

# 后台启动（chat 模式）
$process = Start-Process -FilePath "uv" -ArgumentList "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "9000", "--reload" -WorkingDirectory $ROOT -NoNewWindow -PassThru

Write-Host ">>> kf-api PID: $($process.Id)"

# 快速就绪检测
$maxWait = 20
for ($i = 0; $i -lt $maxWait; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:9000/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            Write-Host ">>> kf-api 就绪 (尝试 $($i+1) 次)"
            Write-Host ">>> API 文档: http://localhost:9000/docs"
            exit 0
        }
    } catch {}
    Start-Sleep -Seconds 2
}

Write-Host "WARN: kf-api 未在 ${maxWait}s x 2s 内就绪"
Write-Host "WARN: 检查 uv run 控制台输出"
