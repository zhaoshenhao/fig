# push-workflow.ps1 — 推送本地 workflow 配置到 OSS，触发部署
# 用法:
#   .\deployment\scripts\push-workflow.ps1 [-Env test|prod] [-DryRun]
#
# 凭据从 .env_mb_test / .env_mb_pr 读取，优先级: env-file → 环境变量 → K8s Secret

param(
    [ValidateSet("test", "prod")]
    [string]$Env = "test",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ROOT = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$LOCAL = Join-Path $ROOT "config\workflows"
$ENVFILE = Join-Path $ROOT ".env_mb_$Env"

$NAMESPACE = if ($Env -eq "test") { "mb-test" } else { "mb-pr" }
$OSS_BUCKET = "kf-workflow"
$OSS_PREFIX = if ($Env -eq "test") { "mb-test" } else { "mb-pr" }

$OSSUtil = "C:\green\ossutil.exe"

function Load-EnvFile($path) {
    $hash = @{}
    if (Test-Path $path) {
        Get-Content $path | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#") -and $line -match '^\s*([^=]+)=(.*)') {
                $hash[$Matches[1].Trim()] = $Matches[2].Trim()
            }
        }
    }
    return $hash
}

$envMap = Load-EnvFile $ENVFILE

function Get-Config($key) {
    if ($envMap.ContainsKey($key) -and $envMap[$key]) { return $envMap[$key] }
    $v = [System.Environment]::GetEnvironmentVariable($key)
    if ($v) { return $v }
    return ""
}

Write-Host "==> Push workflow config to OSS"
Write-Host "    env:    $Env ($NAMESPACE)"
Write-Host "    config: $ENVFILE"
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

# Read OSS creds: env-file → env var → K8s secret
$ak  = Get-Config "OSS_ACCESS_KEY_ID"
$sk  = Get-Config "OSS_ACCESS_KEY_SECRET"
$ep  = Get-Config "OSS_ENDPOINT"
if (-not $ep) { $ep = "oss-cn-shanghai-internal.aliyuncs.com" }
$region = if ($ep -match 'oss-(cn-\S+?)\.') { $Matches[1] } else { "cn-shanghai" }

if (-not $ak) {
    Write-Host "    Reading OSS creds from K8s secret kf-secrets ..."
    $ak = (kubectl get secret kf-secrets -n $NAMESPACE -o jsonpath='{.data.OSS_ACCESS_KEY_ID}' 2>$null)
    $sk = (kubectl get secret kf-secrets -n $NAMESPACE -o jsonpath='{.data.OSS_ACCESS_KEY_SECRET}' 2>$null)
    if ($ak) { $ak = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($ak)) }
    if ($sk) { $sk = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($sk)) }
}

if (-not $ak) {
    Write-Host "ERROR: OSS_ACCESS_KEY_ID not set ($ENVFILE / env / kf-secrets)" -ForegroundColor Red
    exit 1
}

Write-Host "    Configuring ossutil (region=$region) ..."
cmd /c "`"$OSSUtil`" config set accessKeyID $ak --language CH 2>&1" | Out-Null
cmd /c "`"$OSSUtil`" config set accessKeySecret $sk --language CH 2>&1" | Out-Null
cmd /c "`"$OSSUtil`" config set endpoint $ep --language CH 2>&1" | Out-Null
cmd /c "`"$OSSUtil`" config set region $region --language CH 2>&1" | Out-Null

# Push
$args = @("cp", "-r", $LOCAL, "oss://${OSS_BUCKET}/${OSS_PREFIX}/", "--update", "--region", $region)
if ($DryRun) { $args += "--dry-run"; Write-Host "    (dry-run mode)" }

Write-Host "    Running ossutil cp ..."
cmd /c "`"$OSSUtil`" $($args -join ' ') 2>&1"
if ($LASTEXITCODE -ne 0) { throw "ossutil cp failed" }

Write-Host "==> Done"
Write-Host "    Workflow config synced to oss://${OSS_BUCKET}/${OSS_PREFIX}/"
Write-Host "    Restart kf-api to pick up changes:"
Write-Host "      kubectl rollout restart deployment/kf-api -n $NAMESPACE"
