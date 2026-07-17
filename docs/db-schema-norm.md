[English](db-schema-norm_EN.md)

# 数据库 Schema 变更规范

## 核心原则

- **Schema 唯一定义在 `src/metrics/schema.py`**（canonical source of truth）
- **版本化迁移**在 `src/metrics/migration.py`（`Migration` 数据类 + `MIGRATIONS` 列表）
- 应用启动时自动执行 `migrate(conn, dialect)`，检测 schema 漂移并备份旧表
- **永远不要**提交删除数据的迁移，除非有显式的备份步骤

---

## 新增迁移的标准步骤

### 1. 修改 Schema 定义

编辑 `src/metrics/schema.py`，添加/修改列定义：

```python
# 在 all_table_ddl() 中添加新列
def all_table_ddl(dialect):
    ...
    runs_cols = {
        ...
        "new_field": "TEXT",  # 新增字段
    }
```

> 完整列定义参见 `COLUMNS` 常量。

### 2. 添加 Migration 条目

在 `src/metrics/migration.py` 的 `MIGRATIONS` 列表末尾追加：

```python
Migration(
    version=2,  # 当前最大版本 + 1
    description="add new_field to runs",
    table_columns={
        "runs": [
            # 列出迁移后 runs 表全部的期望列名
            "id", "chat_id", "turn_id", "workflow_name",
            "query", "reply", "node_count", "duration_ms",
            "status", "error_message", "prompt_tokens",
            "completion_tokens", "created_at",
            "new_field",  # 新增列
        ],
    },
    ddl_sql=[
        "ALTER TABLE runs ADD COLUMN new_field TEXT",
    ],
    index_sql=[
        # 如果需要新索引
        # "CREATE INDEX idx_runs_new_field ON runs(new_field)",
    ],
),
```

### 3. 更新索引定义

如果新增了索引，在 `src/metrics/schema.py` 的 `all_index_ddl()` 中添加对应条目。

### 4. 验证

```bash
# 全新数据库
rm -f data/metrics.db
pytest tests/unit/test_metrics.py -v

# 从旧版本升级（保留旧 DB 文件后重启应用）
python -m uvicorn src.api.main:app

# 检查迁移日志
grep "migration" logs/app.log
```

### 5. 检查备份

如果迁移检测到 schema 漂移（实际列与期望列不一致），会自动将旧表重命名为 `<table>_backup_<YYYYMMDD_HHMMSS>`。确认备份无误后手动删除。

---

## 迁移数据结构

```python
@dataclass
class Migration:
    version: int                            # 递增版本号
    description: str                        # 可读描述
    table_columns: dict[str, list[str]]     # 受影响表的期望列集
    ddl_sql: list[str]                      # DDL 语句列表
    index_sql: list[str]                    # 索引创建语句列表
```

---

## 注意事项

| 规则 | 说明 |
|------|------|
| 版本号递增 | 每个 Migration 的 `version` 必须严格递增 |
| 不可逆 | 迁移是只追加的，已有 Migration 不可修改 |
| 幂等 | `_schema_version` 表确保已执行的迁移自动跳过 |
| 无数据丢失 | 不使用 `DROP TABLE`，始终先备份再变更 |
| 测试覆盖 | 每个迁移必须有对应的单元测试 |

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `src/metrics/schema.py` | 权威 Schema 定义（DDL + 索引 + 列列表） |
| `src/metrics/migration.py` | 迁移引擎 + MIGRATIONS 列表 |
| `src/metrics/dialect.py` | SQL 方言抽象（SQLite / MySQL / PostgreSQL） |
| `src/metrics/store.py` | SQLite MetricsStore，调用 `_init_db()` |
| `src/metrics/sql_store.py` | MySQL / PG MetricsStore，调用 `_init_db()` |
