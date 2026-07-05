# DB 配置指南

## 配置文件

`config/db.yaml` — 数据库连接配置，一个系统可以有多个数据库连接池。

```yaml
default: mysql_main        # 默认使用的连接池名称

pools:
  mysql_main:
    type: mysql
    host: localhost
    port: 3306
    user: root
    password: ${MYSQL_PASSWORD:}
    database: kf
    pool_size: 5

  pg_analytics:
    type: postgresql
    host: localhost
    port: 5432
    user: postgres
    password: ${PG_PASSWORD:}
    database: analytics
    pool_size: 3
```

## 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `default` | 否 | 默认连接池名称 |
| `pools.{name}.type` | 是 | `mysql` 或 `postgresql` |
| `pools.{name}.host` | 否 | 主机地址，默认 `localhost` |
| `pools.{name}.port` | 否 | 端口，MySQL 默认 3306，PostgreSQL 默认 5432 |
| `pools.{name}.user` | 否 | 用户名 |
| `pools.{name}.password` | 否 | 密码，支持 `${ENV_VAR}` 占位符 |
| `pools.{name}.database` | 否 | 数据库名 |
| `pools.{name}.pool_size` | 否 | 连接池大小，默认 5 |

## 依赖安装

```bash
# MySQL
pip install pymysql

# PostgreSQL
pip install psycopg2-binary
```

## db_query 工具使用

### 节点配置

```yaml
tool: db_query
db: mysql_main                    # 使用 config/db.yaml 中的连接池名称
query: "SELECT * FROM faq WHERE question LIKE %s"
params:
  - "%{{query}}%"                # 参数化查询，{{query}} 替换为当前用户问题
limit: 20                         # 最多返回行数
```

### 模板变量

| 变量 | 来源 |
|------|------|
| `{{query}}` | 当前轮的用户输入 |
| `{{session_id}}` | 会话 ID |
| `{{_workflow}}` | 工作流名称 |
| `{{text}}` | 前一个节点的 data.text |

### 返回结果

```json
{
  "text": "mysql_main\nid, question, answer\n----------------\n1, FAQ问题, FAQ答案",
  "rows": [
    {"id": 1, "question": "FAQ问题", "answer": "FAQ答案"}
  ],
  "db": "mysql_main"
}
```

## 连接池管理

- 启动时根据 `config/db.yaml` 创建所有连接池
- 每个池在 `pool_size` 范围内复用连接
- `db_query` 自动从对应连接池取连接，查询后归还
- 连接池在应用关闭时释放
