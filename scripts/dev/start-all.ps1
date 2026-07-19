# start-all.ps1 — 一键启动本地开发全部服务
# 用法: .\scripts\dev\start-all.ps1

$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSCommandPath))

Write-Host "=============================================="
Write-Host "  KF 本地开发环境启动"
Write-Host "=============================================="
Write-Host ""

# ── 1. Qdrant (WSL Docker) ──
Write-Host "[1/4] Qdrant (6333/6334)"
& "$ROOT\scripts\dev\start-qdrant.ps1"

# ── 2. 数据库初始化 ──
Write-Host ""
Write-Host "[2/4] MySQL 初始化"
& "$ROOT\scripts\dev\init-db.ps1"

# ── 3. kf-embed ──
Write-Host ""
Write-Host "[3/4] kf-embed (8100)"
& "$ROOT\scripts\dev\start-embed.ps1"

# ── 4. kf-api ──
Write-Host ""
Write-Host "[4/4] kf-api (9000)"
& "$ROOT\scripts\dev\start-api.ps1"

Write-Host ""
Write-Host "=============================================="
Write-Host "  启动完成"
Write-Host "=============================================="
Write-Host "  Qdrant:    http://localhost:6333 (HTTP) / :6334 (gRPC)"
Write-Host "  kf-embed:  http://localhost:8100"
Write-Host "  kf-api:    http://localhost:9000/docs"
Write-Host "  MySQL:     localhost:3307 (root/kfpass)"
Write-Host "=============================================="
