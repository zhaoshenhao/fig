#!/usr/bin/env bash
# =============================================================================
# init-metrics-db.sh — 一键初始化 Metrics 数据库和应用用户
#
# 用法:
#   # MySQL
#   DB_TYPE=mysql \
#   DB_ROOT_USER=root DB_ROOT_PASSWORD=rootpass \
#   ./scripts/init-metrics-db.sh
#
#   # PostgreSQL
#   DB_TYPE=postgresql \
#   DB_ROOT_USER=postgres DB_ROOT_PASSWORD=rootpass \
#   ./scripts/init-metrics-db.sh
#
# 环境变量（全部可选，有默认值）:
#   DB_TYPE           mysql | postgresql   (默认: mysql)
#   DB_HOST           数据库主机           (默认: 127.0.0.1)
#   DB_PORT           数据库端口           (默认: 3306 mysql / 5432 pg)
#   DB_ROOT_USER      管理员用户名         (默认: root mysql / postgres pg)
#   DB_ROOT_PASSWORD  管理员密码           (必填)
#   DB_APP_USER       应用用户名           (默认: kf)
#   DB_APP_PASSWORD   应用密码             (默认: 随机生成并打印)
#   DB_NAME           数据库名             (默认: kf_metrics)
#
# 注意:
#   - 需要 mysql 或 psql 客户端已安装
#   - 表结构由应用启动时自动创建，本脚本只建库和用户
# =============================================================================
set -euo pipefail

DB_TYPE="${DB_TYPE:-mysql}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_ROOT_USER="${DB_ROOT_USER:-}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-}"
DB_APP_USER="${DB_APP_USER:-kf}"
DB_NAME="${DB_NAME:-kf_metrics}"

# ---- 生成随机密码（12 位） ----
if [ -z "${DB_APP_PASSWORD:-}" ]; then
  DB_APP_PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^' < /dev/urandom 2>/dev/null | head -c12 || python3 -c "import secrets; print(secrets.token_urlsafe(9))")"
  echo ">>> 未设置 DB_APP_PASSWORD，已随机生成"
fi

# ---- 默认端口和 root 用户 ----
case "$DB_TYPE" in
  mysql)
    DB_PORT="${DB_PORT:-3306}"
    DB_ROOT_USER="${DB_ROOT_USER:-root}"
    ;;
  postgresql|postgres|pg)
    DB_PORT="${DB_PORT:-5432}"
    DB_ROOT_USER="${DB_ROOT_USER:-postgres}"
    ;;
  *)
    echo "ERROR: 不支持的 DB_TYPE='$DB_TYPE'，请设为 mysql 或 postgresql"
    exit 1
    ;;
esac

# ---- 检查 root 密码 ----
if [ -z "$DB_ROOT_PASSWORD" ]; then
  echo "ERROR: 必须通过 DB_ROOT_PASSWORD 环境变量提供管理员密码"
  exit 1
fi

# ---- 连接测试 ----
echo ">>> 连接 $DB_HOST:$DB_PORT ($DB_TYPE) ..."

# ---- MySQL ----
if [ "$DB_TYPE" = "mysql" ]; then
  if ! command -v mysql &>/dev/null; then
    echo "ERROR: 未找到 mysql 客户端。请安装: apt install mysql-client 或 brew install mysql-client"
    exit 1
  fi

  mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_ROOT_USER" -p"$DB_ROOT_PASSWORD" -e "SELECT 1" &>/dev/null
  echo ">>> 连接成功"

  mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_ROOT_USER" -p"$DB_ROOT_PASSWORD" <<SQL
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 删除旧用户（如存在）后重新创建
DROP USER IF EXISTS '$DB_APP_USER'@'%';
CREATE USER '$DB_APP_USER'@'%' IDENTIFIED BY '$DB_APP_PASSWORD';

GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_APP_USER'@'%';
FLUSH PRIVILEGES;

-- 设定全局时区为 UTC（可选，建议）
SET GLOBAL time_zone = '+00:00';
SQL

# ---- PostgreSQL ----
elif [ "$DB_TYPE" = "postgresql" ] || [ "$DB_TYPE" = "postgres" ] || [ "$DB_TYPE" = "pg" ]; then
  if ! command -v psql &>/dev/null; then
    echo "ERROR: 未找到 psql 客户端。请安装: apt install postgresql-client 或 brew install libpq"
    exit 1
  fi

  export PGPASSWORD="$DB_ROOT_PASSWORD"

  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_ROOT_USER" -d postgres -c "SELECT 1" &>/dev/null
  echo ">>> 连接成功"

  # 需要在事务外创建数据库
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_ROOT_USER" -d postgres <<SQL
SELECT 'CREATE DATABASE $DB_NAME ENCODING ''UTF8'''
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gset
\if :error
  \echo '数据库已存在，跳过创建'
\endif
SQL

  # 如果数据库不存在则创建
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_ROOT_USER" -d postgres \
    -c "CREATE DATABASE \"$DB_NAME\" ENCODING 'UTF8'" 2>/dev/null || echo ">>> 数据库已存在，跳过创建"

  # 创建用户并授权（在目标库中执行）
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_ROOT_USER" -d "$DB_NAME" <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_APP_USER') THEN
    CREATE USER $DB_APP_USER WITH PASSWORD '$DB_APP_PASSWORD';
  END IF;
END
\$\$;

-- PostgreSQL 15+ 需要分别授权 schema
GRANT ALL PRIVILEGES ON DATABASE "$DB_NAME" TO $DB_APP_USER;
GRANT ALL ON SCHEMA public TO $DB_APP_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_APP_USER;
SQL

  unset PGPASSWORD
fi

# ---- 结果 ----
echo ""
echo "=============================================="
echo "  初始化完成"
echo "=============================================="
echo "  类型:     $DB_TYPE"
echo "  主机:     $DB_HOST:$DB_PORT"
echo "  数据库:   $DB_NAME"
echo "  用户名:   $DB_APP_USER"
echo "  密码:     $DB_APP_PASSWORD"
echo "=============================================="
echo ""
echo "下一步: 在 .env 中配置以下环境变量:"
echo ""
echo "  KF_METRICS_ENGINE=$DB_TYPE"
echo "  KF_METRICS_DB_HOST=$DB_HOST"
echo "  KF_METRICS_DB_PORT=$DB_PORT"
echo "  KF_METRICS_DB_USER=$DB_APP_USER"
echo "  KF_METRICS_DB_PASSWORD=$DB_APP_PASSWORD"
echo "  KF_METRICS_DB_NAME=$DB_NAME"
echo ""
echo "然后启动应用，表结构将在首次启动时自动创建。"
