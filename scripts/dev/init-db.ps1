# init-db.ps1 — 初始化本地开发 MySQL 数据库
# 前置: WSL Docker kf-mysql 容器必须已运行（端口 3307）
# 用法: .\scripts\dev\init-db.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSCommandPath))

Write-Host ">>> 初始化 MySQL 数据库 (localhost:3307) ..."

$sql = @"
CREATE DATABASE IF NOT EXISTS kf_metrics
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'kf_app'@'%' IDENTIFIED BY 'UdiMYd7fZ9FXlH3MbsVM';

GRANT ALL PRIVILEGES ON kf_metrics.* TO 'kf_app'@'%';
FLUSH PRIVILEGES;
"@

$encodedSql = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($sql))

wsl bash -c "echo $encodedSql | base64 -d | mysql -uroot -pkfpass -h 127.0.0.1 -P 3307"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: 数据库初始化失败" -ForegroundColor Red
    exit 1
}

Write-Host ">>> 数据库初始化完成"
Write-Host ">>> kf_metrics 库已就绪，用户 kf_app 已配置"
