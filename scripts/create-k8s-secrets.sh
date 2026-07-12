#!/bin/bash
# ============================================================================
# K8s Secret 管理脚本
# ============================================================================
# 用法:
#   方式 1 — 从环境变量读取（Jenkins / CI 推荐）
#     export NAMESPACE=mb-test
#     export DEEPSEEK_API_KEY=sk-xxx
#     ... (设置其他变量)
#     ./scripts/create-k8s-secrets.sh
#
#   方式 2 — 从 .env 文件读取（本地开发推荐）
#     NAMESPACE=mb-test ./scripts/create-k8s-secrets.sh .env.test
#
#   方式 3 — 仅查看当前 Secret 内容（不修改）
#     NAMESPACE=mb-test ./scripts/create-k8s-secrets.sh --show
#
#   方式 4 — 从 .env 文件读取并创建
#     NAMESPACE=mb-test ENV_FILE=.env.test ./scripts/create-k8s-secrets.sh
#
# 前置条件:
#   - kubectl 已配置到目标集群
#   - 命名空间已存在（或通过 kubectl create namespace 提前创建）
# ============================================================================

set -euo pipefail

NAMESPACE="${NAMESPACE:-}"
ENV_FILE="${ENV_FILE:-${1:-}}"

# ---- 帮助 ----
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "用法: NAMESPACE=<ns> [ENV_FILE=<file>] ./scripts/create-k8s-secrets.sh [--show]"
    echo ""
    echo "  NAMESPACE       目标 K8s 命名空间 (mb-test / mb-pr)"
    echo "  ENV_FILE         .env 文件路径（可选，缺省从环境变量读取）"
    echo "  --show           仅显示当前 Secret 内容"
    echo "  -h, --help       显示帮助"
    exit 0
fi

if [[ "${1:-}" == "--show" ]]; then
    if [[ -z "$NAMESPACE" ]]; then
        echo "错误: 需要设置 NAMESPACE 环境变量"
        exit 1
    fi
    kubectl get secret kf-secrets -n "$NAMESPACE" -o yaml 2>/dev/null || echo "Secret 不存在"
    exit 0
fi

# ---- 从 .env 文件加载 ----
if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
    echo "从文件加载: $ENV_FILE"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
elif [[ -n "$ENV_FILE" ]]; then
    echo "错误: 文件不存在: $ENV_FILE"
    exit 1
fi

# ---- 校验 ----
if [[ -z "$NAMESPACE" ]]; then
    echo "错误: 需要设置 NAMESPACE 环境变量 (mb-test / mb-pr)"
    exit 1
fi

MISSING=()
for var in DEEPSEEK_API_KEY KF_API_KEY EMBED_API_KEY \
           REDIS_URL \
           MYSQL_HOST MYSQL_PORT MYSQL_USER MYSQL_PASSWORD MYSQL_DB \
           KF_METRICS_DB_HOST KF_METRICS_DB_PORT KF_METRICS_DB_USER \
           KF_METRICS_DB_PASSWORD KF_METRICS_DB_NAME \
           PG_HOST PG_PORT PG_USER PG_PASSWORD PG_DB \
           OSS_ACCESS_KEY_ID OSS_ACCESS_KEY_SECRET; do
    if [[ -z "${!var:-}" ]]; then
        MISSING+=("$var")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "错误: 以下环境变量未设置:"
    for v in "${MISSING[@]}"; do
        echo "  - $v"
    done
    exit 1
fi

# ---- 默认值 ----
OSS_ENDPOINT="${OSS_ENDPOINT:-oss-cn-hangzhou.aliyuncs.com}"
KF_METRICS_DB_TYPE="${KF_METRICS_DB_TYPE:-mysql}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
PG_PORT="${PG_PORT:-5432}"

# ---- 构建 Secret ----
echo "创建/更新 Secret kf-secrets (namespace=$NAMESPACE) ..."

kubectl create secret generic kf-secrets \
    --namespace="$NAMESPACE" \
    --dry-run=client -o yaml \
    --from-literal=DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
    --from-literal=KF_API_KEY="$KF_API_KEY" \
    --from-literal=EMBED_API_KEY="$EMBED_API_KEY" \
    --from-literal=REDIS_URL="$REDIS_URL" \
    --from-literal=MYSQL_HOST="$MYSQL_HOST" \
    --from-literal=MYSQL_PORT="$MYSQL_PORT" \
    --from-literal=MYSQL_USER="$MYSQL_USER" \
    --from-literal=MYSQL_PASSWORD="$MYSQL_PASSWORD" \
    --from-literal=MYSQL_DB="$MYSQL_DB" \
    --from-literal=KF_METRICS_DB_TYPE="$KF_METRICS_DB_TYPE" \
    --from-literal=KF_METRICS_DB_HOST="${KF_METRICS_DB_HOST:-$MYSQL_HOST}" \
    --from-literal=KF_METRICS_DB_PORT="${KF_METRICS_DB_PORT:-$MYSQL_PORT}" \
    --from-literal=KF_METRICS_DB_USER="${KF_METRICS_DB_USER:-$MYSQL_USER}" \
    --from-literal=KF_METRICS_DB_PASSWORD="${KF_METRICS_DB_PASSWORD:-$MYSQL_PASSWORD}" \
    --from-literal=KF_METRICS_DB_NAME="${KF_METRICS_DB_NAME:-kf_metrics}" \
    --from-literal=PG_HOST="$PG_HOST" \
    --from-literal=PG_PORT="$PG_PORT" \
    --from-literal=PG_USER="$PG_USER" \
    --from-literal=PG_PASSWORD="$PG_PASSWORD" \
    --from-literal=PG_DB="$PG_DB" \
    --from-literal=OSS_ACCESS_KEY_ID="$OSS_ACCESS_KEY_ID" \
    --from-literal=OSS_ACCESS_KEY_SECRET="$OSS_ACCESS_KEY_SECRET" \
    --from-literal=OSS_ENDPOINT="$OSS_ENDPOINT" \
| kubectl apply -f -

echo "完成: Secret kf-secrets 已更新 (namespace=$NAMESPACE)"

# ---- 校验 ----
echo ""
echo "验证:"
kubectl get secret kf-secrets -n "$NAMESPACE" -o jsonpath='{.data}' | python3 -c "
import json, sys
data = json.load(sys.stdin)
for k in sorted(data):
    v = data[k]
    masked = v[:4] + '***' if len(v) > 6 else '***'
    print(f'  {k:30s} = {masked}')
" 2>/dev/null || kubectl get secret kf-secrets -n "$NAMESPACE"
