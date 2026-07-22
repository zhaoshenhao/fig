# push-workflow.ps1 — 推送本地 workflow 配置到 OSS，触发部署
# 用法:
#   .\deployment\scripts\push-workflow.ps1 [-Env test|prod] [-DryRun]
#
# 前置: 需安装 ossutil 并配置 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET / OSS_ENDPOINT
#       或从 K8s Secret 自动读取

param(
    [ValidateSet("test", "prod")]
    [string]$Env = "test",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ROOT = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$LOCAL = Join-Path $ROOT "config\workflows"

$NAMESPACE = if ($Env -eq "test") { "mb-test" } else { "mb-pr" }
$OSS_BUCKET = "kf-workflow"
$OSS_PREFIX = if ($Env -eq "test") { "mb-test" } else { "mb-pr" }

$OSSUtil = "C:\green\ossutil.exe"

Write-Host "==> Push workflow config to OSS"
Write-Host "    env:    $Env ($NAMESPACE)"
Write-Host "    local:  $LOCAL"
Write-Host "    target: oss://${OSS_BUCKET}/${OSS_PREFIX}/"

if (-not (Test-Path $LOCAL)) {
    Write-Host "ERROR: config dir not found: $LOCAL" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $OSSUtil)) {
    Write-Host "ERROR: ossutil not found: $OSSUtil" -ForegroundColor Red
    exit 1
}

# Read OSS creds from env or K8s secret
$ak  = $env:OSS_ACCESS_KEY_ID
$sk  = $env:OSS_ACCESS_KEY_SECRET
$ep  = $env:OSS_ENDPOINT
if (-not $ep) { $ep = "oss-cn-shanghai-internal.aliyuncs.com" }

if (-not $ak) {
    Write-Host "    Reading OSS creds from K8s secret kf-secrets ..."
    $ak = (kubectl get secret kf-secrets -n $NAMESPACE -o jsonpath='{.data.OSS_ACCESS_KEY_ID}' 2>$null)
    $sk = (kubectl get secret kf-secrets -n $NAMESPACE -o jsonpath='{.data.OSS_ACCESS_KEY_SECRET}' 2>$null)
    if ($ak) { $ak = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($ak)) }
    if ($sk) { $sk = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($sk)) }
}

if (-not $ak) {
    Write-Host "ERROR: OSS_ACCESS_KEY_ID not set (env or kf-secrets)" -ForegroundColor Red
    exit 1
}

Write-Host "    Configuring ossutil ..."
cmd /c "`"$OSSUtil`" config -e $ep -i $ak -k $sk -L CH 2>&1" | Out-Null

# Push
$args = @("cp", "-r", $LOCAL, "oss://${OSS_BUCKET}/${OSS_PREFIX}/", "--update")
if ($DryRun) { $args += "--dry-run"; Write-Host "    (dry-run mode)" }

Write-Host "    Running ossutil cp ..."
cmd /c "`"$OSSUtil`" $($args -join ' ') 2>&1"
if ($LASTEXITCODE -ne 0) { throw "ossutil cp failed" }

Write-Host "==> Done"
Write-Host "    Workflow config synced to oss://${OSS_BUCKET}/${OSS_PREFIX}/"
Write-Host "    Restart kf-api to pick up changes:"
Write-Host "      kubectl rollout restart deployment/kf-api -n $NAMESPACE"
