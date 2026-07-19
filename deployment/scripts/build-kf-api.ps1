# build-kf-api.ps1 — 本地构建并推送 kf-api 镜像到阿里云容器仓库
# 用法（WSL Docker）:
#   .\deployment\scripts\build-kf-api.ps1 -Tag v1
#
# 用法（Windows 原生 Docker）:
#   .\deployment\scripts\build-kf-api.ps1 -Tag v1 -Native
#
# 前置: 先执行 docker login
#   wsl bash -c "docker login registry.cn-shanghai.aliyuncs.com -u <user> --password-stdin"

# 如果设置了 -Latest，额外打 latest 标签并推送

param(
    [string]$Tag = "latest",
    [switch]$Native,
    [switch]$Latest,
    [string]$Registry = "registry.cn-shanghai.aliyuncs.com",
    [string]$Namespace = "ybbmb",
    [string]$Mirror = "docker.m.daocloud.io"
)

$ROOT = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$Image = "$Registry/$Namespace/kf-api`:$Tag"

if ($Native) {
    $docker = "docker"
    $ctx = $ROOT
} elseif (Get-Command docker -ErrorAction SilentlyContinue) {
    $docker = "docker"
    $ctx = $ROOT
} else {
    $docker = "wsl docker"
    $ctx = ($ROOT -replace "\\", "/" -replace "^([A-Z]):", "/mnt/`$1").ToLower()
}

Write-Host "==> KF-API Image Build"
Write-Host "    Engine:    $docker"
Write-Host "    Context:   $ctx"
Write-Host "    Image:     $Image"
Write-Host ""

cmd /c "$docker pull $Mirror/library/python:3.14-slim 2>&1"
if ($LASTEXITCODE -ne 0) { throw "Base image pull failed" }
cmd /c "$docker tag $Mirror/library/python:3.14-slim python:3.14-slim 2>&1"

cmd /c "$docker build -t $Image -f `"$ctx/Dockerfile`" $ctx 2>&1"
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

cmd /c "$docker push $Image 2>&1"
if ($LASTEXITCODE -ne 0) { throw "Push failed" }

if ($Latest) {
    $latestImg = "$Registry/$Namespace/kf-api:latest"
    cmd /c "$docker tag $Image $latestImg 2>&1"
    cmd /c "$docker push $latestImg 2>&1"
    Write-Host "==> Also pushed: $latestImg"
}

Write-Host "==> Done: $Image"
