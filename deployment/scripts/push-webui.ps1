# push-webui.ps1 — 本地构建 Vue SPA 并推送 dist/ 到 Git
# 用法:
#   .\deployment\scripts\push-webui.ps1
#
# 前置: 本地需安装 Node.js (npm)

$ROOT = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$UI_DIR = Join-Path $ROOT "src\gui\ui"

Write-Host "==> Building Vue SPA"
Push-Location $UI_DIR
try {
    cmd /c "npm ci 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    cmd /c "npm run build 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    Write-Host "    Build OK"
} finally {
    Pop-Location
}

Write-Host "==> Git push"
Push-Location $ROOT
try {
    cmd /c "git add src/gui/ui/dist/ 2>&1"
    cmd /c 'git commit -m "chore(webui): update dist" 2>&1'
    cmd /c "git push origin master 2>&1"
    cmd /c "git push github master 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }
    Write-Host "    Pushed OK"
} finally {
    Pop-Location
}

Write-Host "==> Done"
