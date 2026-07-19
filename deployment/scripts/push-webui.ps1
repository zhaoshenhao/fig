# push-webui.ps1 — 本地构建 Vue SPA 并推送 dist/ 到 Git
# 用法:
#   .\deployment\scripts\push-webui.ps1
#
# 前置: 本地需安装 Node.js (npm)

param()

$ROOT = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$UI_DIR = Join-Path $ROOT "src\gui\ui"

Write-Host "==> Building Vue SPA"
Push-Location $UI_DIR
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "    Installing dependencies..."
        cmd /c "npm install 2>&1"
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    }
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
    # commit may fail if nothing changed — that's fine
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    (nothing to commit, skip)"
    }
    cmd /c "git push origin master 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "git push origin failed" }
    cmd /c "git push github master 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "git push github failed" }
    Write-Host "    Pushed OK"
} finally {
    Pop-Location
}

Write-Host "==> Done"
