# build-kf-embed.ps1 — 本地构建并推送 kf-embed 镜像到阿里云容器仓库
# 用法:
#   .\deployment\scripts\build-kf-embed.ps1 [-Tag mytag]
#
# 前置: 先执行 docker login（凭据不写入本脚本）
#   docker login registry-vpc.cn-shanghai.aliyuncs.com -u <user> --password-stdin

param(
    [string]$Tag = "latest",
    [string]$Registry = $env:DOCKER_REG_BASE_URL,
    [string]$Namespace = $env:DOCKER_NS,
    [string]$Mirror = "docker.m.daocloud.io"
)

if (-not $Registry) { $Registry = "registry-vpc.cn-shanghai.aliyuncs.com" }
if (-not $Namespace) { $Namespace = "ybbmb" }

$Image = "$Registry/$Namespace/kf-embed`:$Tag"
$ROOT = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent

Write-Host "==> KF-EMBED Image Build"
Write-Host "    Registry:  $Registry"
Write-Host "    Namespace: $Namespace"
Write-Host "    Tag:       $Tag"
Write-Host "    Image:     $Image"
Write-Host ""

Write-Host "==> Pull base image from mirror..."
docker pull "$Mirror/library/python:3.14-slim"
if ($LASTEXITCODE -ne 0) { throw "Base image pull failed" }
docker tag "$Mirror/library/python:3.14-slim" "python:3.14-slim"

Write-Host "==> Build $Image..."
docker build -t $Image -f "$ROOT\Dockerfile.embed" $ROOT
if ($LASTEXITCODE -ne 0) { throw "Docker build failed" }

Write-Host "==> Push $Image..."
docker push $Image
if ($LASTEXITCODE -ne 0) { throw "Docker push failed" }

Write-Host ""
Write-Host "==> Done: $Image"
