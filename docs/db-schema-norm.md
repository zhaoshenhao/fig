# 数据库 Schema 变更规范

## 原则

1. **唯一真相源**: 所有表结构定义在 `src/metrics/schema.py`，Dialect 参数化支持 SQLite/MySQL/PostgreSQL
2. **版本化迁移**: 所有变更通过 `src/metrics/migration.py` 的 `Migration` 数据类定义，`version` 递增
3. **自动执行**: 启动时 `_init_db()` → `migrate(conn, dialect)` 自动应用待处理迁移
4. **非破坏性**: 表结构变更前自动备份原表（`ALTER TABLE ... RENAME TO _backup_<YYYYMMDD_HHMMSS>`）
5. **已执行跳过**: `_schema_version` 表记录已应用的版本号，重复执行幂等

## 架构

```
src/metrics/
├── schema.py       # 规范表 DDL + 列定义（唯一真相源）
├── migration.py    # Migration 数据类 + MIGRATIONS 列表 + migrate() 引擎
├── dialect.py      # SQL 方言（SQLite/MySQL/PG）
├── store.py        # MetricsStore (SQLite) → _init_db() 调用 migrate()
├── sql_store.py    # SQLMetricsStore (MySQL/PG) → _init_db() 调用 migrate()
└── factory.py      # create_metrics_store() 工厂
```

## 如何新增一次数据库变更

例如要为 `runs` 表加 `cost_estimated` 列：

### 1. 更新 schema.py

在 `TABLE_COLUMNS["runs"]` 列表末尾添加 `"cost_estimated"`：

```python
TABLE_COLUMNS: dict[str, list[str]] = {
    "runs": [
        ...
        "created_at",
        "cost_estimated",  # 新增
    ],
```

在 `all_table_ddl()` 的 runs DDL 中添加新列：

```python
f"""CREATE TABLE IF NOT EXISTS runs (
    ...
    created_at    {vc} DEFAULT {ts},
    cost_estimated REAL DEFAULT 0
)"""
```

### 2. 新增 Migration

在 `migration.py` 的 `MIGRATIONS` 列表末尾追加：

```python
MIGRATIONS: list[Migration] = [
    Migration(version=1, ...),
    # ── 在此之上追加新迁移 ──
    Migration(
        version=2,
        description="Add cost_estimated column to runs",
        table_columns={
            "runs": TABLE_COLUMNS["runs"],  # 复用 schema.py 的列定义
        },
        ddl_sql=[
            "ALTER TABLE runs ADD COLUMN cost_estimated REAL DEFAULT 0",
        ],
        index_sql=[],
    ),
]
```

### 3. 验证

```bash
# 1. 在新数据库中运行 — 应创建表并记录版本
python -m pytest tests/test_metrics.py -k "metrics or migration"

# 2. 在已有数据库中运行 — 应检测 drift 并备份旧表
# （从旧版本升级时自动触发）

# 3. 检查备份表
# SELECT * FROM runs_backup_20260712_143000 LIMIT 10;
```

### 4. 部署

- API 启动时自动检测版本号并执行迁移
- 若迁移失败（如 DDL 错误），API 启动失败，不会以错误 schema 运行
- 备份表保留 7 天，确认数据完整后手动清理

## 迁移规则

| 操作 | 迁移 action | 示例 |
|------|------------|------|
| 新增表 | `ddl_sql` 含 `CREATE TABLE`（但同时应更新 `all_table_ddl`） | version 1 |
| 新增列 | `ddl_sql` 含 `ALTER TABLE ADD COLUMN` | `cost_estimated` |
| 改变列类型 | `table_columns` 触发 drift → 备份 → 重建 | 极少发生 |
| 新增索引 | `index_sql` 含 `CREATE INDEX` | `idx_runs_cost` |
| 删除列 | 不建议直接删除，标记为弃用后下个大版本清理 | — |

**禁止**：迁移中直接 `DROP TABLE` 或 `DELETE`。如需清理数据，先用 `_backup_table`。
