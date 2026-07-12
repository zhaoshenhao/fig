"""真实数据库集成测试（MySQL / PostgreSQL）。

若目标数据库不可达，则自动 skip（CI 无 DB 环境仍通过）。
本地运行前置：在 WSL 用 docker 启动
    docker run -d --name kf-mysql -e MYSQL_ROOT_PASSWORD=kfpass \
        -e MYSQL_DATABASE=kf_metrics -p 3307:3306 mysql:8
    docker run -d --name kf-pg -e POSTGRES_PASSWORD=kfpass \
        -e POSTGRES_DB=kf_metrics -p 5433:5432 postgres:16
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))

MYSQL = {"type": "mysql", "host": "127.0.0.1", "port": 3307,
         "user": "root", "password": "kfpass", "database": "kf_metrics"}
PG = {"type": "postgresql", "host": "127.0.0.1", "port": 5433,
      "user": "postgres", "password": "kfpass", "database": "kf_metrics"}


def _reachable(cfg) -> bool:
    try:
        if cfg["type"] == "mysql":
            import pymysql
            c = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                                password=cfg["password"], database=cfg["database"],
                                connect_timeout=3)
        else:
            import psycopg2
            c = psycopg2.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                                 password=cfg["password"], dbname=cfg["database"],
                                 connect_timeout=3)
        c.close()
        return True
    except Exception:
        return False


def _pool(cfg):
    from src.db import create_pool
    from src.db.base import DBPoolConfig
    return create_pool(f"it_{cfg['type']}_{uuid.uuid4().hex[:6]}", DBPoolConfig(**cfg))


def _store(cfg):
    from src.metrics.sql_store import MySQLMetricsStore, PostgresMetricsStore
    pool = _pool(cfg)
    return (MySQLMetricsStore if cfg["type"] == "mysql" else PostgresMetricsStore)(pool)


PARAMS = [
    pytest.param(MYSQL, id="mysql"),
    pytest.param(PG, id="postgresql"),
]


@pytest.mark.parametrize("cfg", PARAMS)
class TestMetricsRealDB:
    @pytest.fixture(autouse=True)
    def _skip_if_down(self, cfg):
        if not _reachable(cfg):
            pytest.skip(f"{cfg['type']} not reachable at {cfg['host']}:{cfg['port']}")

    def test_crud_and_feedback(self, cfg):
        s = _store(cfg)
        cid = "it_" + uuid.uuid4().hex[:8]
        rid = s.insert_run(cid, 0, "wf_it", query="问题", reply="答复",
                           duration_ms=12.5, prompt_tokens=3, completion_tokens=5)
        assert rid >= 1
        nid = s.insert_node_log(rid, cid, 0, "n1", "llm", None, "输出", 9.0,
                                status="error", error_message="boom")
        s.insert_tool_log(nid, rid, cid, 0, "n1", "llm", "{}", "{}", 7.0)
        s.insert_feedback(cid, 0, "down", comment="不准", correction="应为X")

        turns = s.query_session_turns(cid)
        assert turns[0]["workflow_name"] == "wf_it"
        assert turns[0]["query"] == "问题"
        nodes = s.query_turn_nodes(rid)
        assert nodes[0]["node_name"] == "n1" and nodes[0]["status"] == "error"
        fb = s.query_feedback(cid, 0)
        assert fb[0]["rating"] == "down" and fb[0]["correction"] == "应为X"

    def test_search_and_aggregate(self, cfg):
        s = _store(cfg)
        cid = "it_" + uuid.uuid4().hex[:8]
        rid = s.insert_run(cid, 0, "wf_agg", query="q", reply="a", duration_ms=50.0)
        s.insert_node_log(rid, cid, 0, "search_kb", "rag_search", None, "o", 40.0)
        rows, total = s.search_sessions(workflow="wf_agg")
        assert total >= 1
        assert any(r["chat_id"] == cid for r in rows)

        summ = s.aggregate_summary()
        assert "satisfaction_rate" in summ["overview"]
        assert "wf_nodes" in summ and "wf_tools" in summ

        ts = s.timeseries("wf_agg")
        assert ts["workflow"] == "wf_agg"
        assert len(ts["buckets"]) >= 1

    def test_export_training_with_feedback(self, cfg):
        s = _store(cfg)
        cid = "it_" + uuid.uuid4().hex[:8]
        s.insert_run(cid, 0, "wf_exp", query="q1", reply="r1", duration_ms=5.0)
        s.insert_feedback(cid, 0, "up", comment="good")
        rows = s.export_training(workflow="wf_exp", status="")
        assert rows and "feedback_rating" in rows[0]

    def test_health(self, cfg):
        s = _store(cfg)
        assert s.health_check()["ok"] is True

    def test_session_meta(self, cfg):
        s = _store(cfg)
        cid = "it_meta_" + uuid.uuid4().hex[:8]
        s.insert_run(cid, 0, "wf_meta", query="q", reply="a", duration_ms=5.0)
        s.upsert_session_meta(cid, title="VIP", tags=["a", "b"])
        assert s.get_session_meta(cid)["title"] == "VIP"
        rows, _ = s.search_sessions(title="VIP")
        assert any(r["chat_id"] == cid and r["tags"] == ["a", "b"] for r in rows)


@pytest.mark.parametrize("cfg", PARAMS)
class TestDBQueryToolRealDB:
    @pytest.fixture(autouse=True)
    def _skip_if_down(self, cfg):
        if not _reachable(cfg):
            pytest.skip(f"{cfg['type']} not reachable")

    def test_db_query_tool_roundtrip(self, cfg):
        from src.engine.tools.db_query import db_query
        from src.session.data import SessionData

        pool = _pool(cfg)
        # 通过全局注册名调用工具
        from src.db import _pools
        name = [k for k, v in _pools.items() if v is pool][0]

        tbl = "it_products_" + uuid.uuid4().hex[:6]
        pool.execute(f"DROP TABLE IF EXISTS {tbl}", ())
        pool.execute(f"CREATE TABLE {tbl} (id INT PRIMARY KEY, name VARCHAR(100), price INT)", ())
        pool.execute(f"INSERT INTO {tbl} (id,name,price) VALUES (%s,%s,%s)", (1, "太阳膜", 800))
        pool.execute(f"INSERT INTO {tbl} (id,name,price) VALUES (%s,%s,%s)", (2, "隐形车衣", 5000))

        # 持久化验证（新连接可见）
        cnt = pool.execute(f"SELECT COUNT(*) AS c FROM {tbl}", ())
        assert cnt[0]["c"] == 2

        sess = SessionData()
        sess.nodes = [{"name": "input", "data": {"text": "隐形车衣"}}]
        r = db_query(
            {"db": name, "query": f"SELECT name, price FROM {tbl} WHERE name = %s",
             "params": ["{{query}}"]},
            sess,
        )
        assert r.get("error") is None
        assert r["rows"] == [{"name": "隐形车衣", "price": 5000}]

        pool.execute(f"DROP TABLE IF EXISTS {tbl}", ())
