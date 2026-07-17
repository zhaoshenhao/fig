from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_proj_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_proj_root))

from src.db import close_all_pools, create_pool, get_db_pool
from src.db.base import DBConfig, DBPool, DBPoolConfig
from src.db.mysql_pool import MySQLPool
from src.db.pg_pool import PgPool


@pytest.fixture(autouse=True)
def _mock_db_drivers(monkeypatch):
    mock_pymysql = MagicMock()
    mock_pymysql.connect = MagicMock()
    monkeypatch.setattr("src.db.mysql_pool.pymysql", mock_pymysql)

    mock_psycopg2 = MagicMock()
    mock_psycopg2.connect = MagicMock()
    monkeypatch.setattr("src.db.pg_pool.psycopg2", mock_psycopg2)


@pytest.fixture(autouse=True)
def _cleanup_pools():
    yield
    close_all_pools()


@pytest.fixture
def mysql_config():
    return DBPoolConfig(type="mysql", pool_size=1)


@pytest.fixture
def pg_config():
    return DBPoolConfig(type="postgresql", pool_size=1)


class TestDBConfig:
    def test_default(self):
        cfg = DBConfig()
        assert cfg.default == ""
        assert cfg.pools == {}

    def test_get_uses_default(self):
        cfg = DBConfig(default="main", pools={"main": DBPoolConfig(type="mysql")})
        assert cfg.get().type == "mysql"

    def test_get_by_name(self):
        cfg = DBConfig(pools={"logs": DBPoolConfig(type="postgresql")})
        assert cfg.get("logs").type == "postgresql"

    def test_get_unknown_raises_keyerror(self):
        cfg = DBConfig()
        with pytest.raises(KeyError, match="not found"):
            cfg.get("nonexistent")


class TestDBPoolConfig:
    def test_defaults(self):
        cfg = DBPoolConfig(type="mysql")
        assert cfg.host == "localhost"
        assert cfg.port == 3306
        assert cfg.user == ""
        assert cfg.password == ""
        assert cfg.database == ""
        assert cfg.pool_size == 5

    def test_custom_values(self):
        cfg = DBPoolConfig(
            type="postgresql", host="pg", port=5432,
            user="u", password="p", database="d", pool_size=10,
        )
        assert cfg.type == "postgresql"
        assert cfg.host == "pg"
        assert cfg.port == 5432
        assert cfg.user == "u"
        assert cfg.password == "p"
        assert cfg.database == "d"
        assert cfg.pool_size == 10


class TestDBPoolABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            DBPool(DBPoolConfig(type="mysql"))


class TestCreatePool:
    def test_mysql_type_returns_mysql_pool(self, mysql_config):
        pool = create_pool("test_mysql", mysql_config)
        assert isinstance(pool, MySQLPool)

    def test_postgresql_type_returns_pg_pool(self, pg_config):
        pool = create_pool("test_pg", pg_config)
        assert isinstance(pool, PgPool)

    def test_unsupported_type_raises_valueerror(self):
        cfg = DBPoolConfig(type="oracle")
        with pytest.raises(ValueError, match="unsupported"):
            create_pool("bad", cfg)


class TestGetDBPool:
    def test_returns_existing_pool(self, mysql_config):
        pool = create_pool("existing", mysql_config)
        found = get_db_pool("existing")
        assert found is pool

    def test_raises_keyerror_for_unknown(self):
        with pytest.raises(KeyError, match="not found"):
            get_db_pool("nonexistent")


class TestCloseAllPools:
    def test_clears_all_pools(self, mysql_config, pg_config):
        m_pool = create_pool("m", mysql_config)
        p_pool = create_pool("p", pg_config)
        assert get_db_pool("m") is m_pool
        assert get_db_pool("p") is p_pool

        close_all_pools()

        with pytest.raises(KeyError):
            get_db_pool("m")
        with pytest.raises(KeyError):
            get_db_pool("p")


class TestMySQLPool:
    def test_init_raises_when_pymysql_not_installed(self, monkeypatch):
        monkeypatch.setattr("src.db.mysql_pool.pymysql", None)
        cfg = DBPoolConfig(type="mysql")
        with pytest.raises(RuntimeError, match="pymysql"):
            MySQLPool(cfg)

    def test_acquire_creates_connection(self, monkeypatch, mysql_config):
        mock_pymysql = MagicMock()
        mock_conn = MagicMock()
        mock_pymysql.connect.return_value = mock_conn
        monkeypatch.setattr("src.db.mysql_pool.pymysql", mock_pymysql)

        pool = MySQLPool(mysql_config)
        conn = pool._acquire()
        assert conn is mock_conn
        assert pool._created == 1
        pool._release(conn)
        pool.close()

    def test_release_reuses_connection(self, monkeypatch, mysql_config):
        mock_pymysql = MagicMock()
        mock_conn = MagicMock()
        mock_conn.ping.return_value = None
        mock_pymysql.connect.return_value = mock_conn
        monkeypatch.setattr("src.db.mysql_pool.pymysql", mock_pymysql)

        pool = MySQLPool(mysql_config)
        conn = pool._acquire()
        pool._release(conn)
        conn2 = pool._acquire()
        assert conn2 is mock_conn
        pool.close()

    def test_close(self, monkeypatch, mysql_config):
        mock_pymysql = MagicMock()
        mock_conn = MagicMock()
        mock_pymysql.connect.return_value = mock_conn
        monkeypatch.setattr("src.db.mysql_pool.pymysql", mock_pymysql)

        pool = MySQLPool(mysql_config)
        pool._acquire()
        pool.close()

    def test_execute(self, monkeypatch, mysql_config):
        mock_pymysql = MagicMock()
        mock_conn = MagicMock()
        mock_pymysql.connect.return_value = mock_conn
        monkeypatch.setattr("src.db.mysql_pool.pymysql", mock_pymysql)

        mock_cursor = MagicMock()
        mock_cursor.description = [("val",)]
        mock_cursor.fetchall.return_value = [(99,)]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cursor)

        pool = MySQLPool(mysql_config)
        rows = pool.execute("SELECT 99", None)
        assert len(rows) == 1
        assert rows[0]["val"] == 99
        pool.close()


class TestPgPool:
    def test_init_raises_when_psycopg2_not_installed(self, monkeypatch):
        monkeypatch.setattr("src.db.pg_pool.psycopg2", None)
        cfg = DBPoolConfig(type="postgresql")
        with pytest.raises(RuntimeError, match="psycopg2"):
            PgPool(cfg)

    def test_acquire_creates_connection(self, monkeypatch, pg_config):
        mock_psycopg2 = MagicMock()
        mock_conn = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        monkeypatch.setattr("src.db.pg_pool.psycopg2", mock_psycopg2)

        pool = PgPool(pg_config)
        conn = pool._acquire()
        assert conn is mock_conn
        pool._release(conn)
        pool.close()

    def test_execute(self, monkeypatch, pg_config):
        mock_psycopg2 = MagicMock()
        mock_conn = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        monkeypatch.setattr("src.db.pg_pool.psycopg2", mock_psycopg2)

        mock_cursor = MagicMock()
        mock_cursor.description = [("val",)]
        mock_cursor.fetchall.return_value = [(42,)]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cursor)

        pool = PgPool(pg_config)
        rows = pool.execute("SELECT 42", None)
        assert len(rows) == 1
        assert rows[0]["val"] == 42
        mock_cursor.execute.assert_called_once_with("SELECT 42", None)
        pool.close()

    def test_close(self, monkeypatch, pg_config):
        mock_psycopg2 = MagicMock()
        mock_conn = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        monkeypatch.setattr("src.db.pg_pool.psycopg2", mock_psycopg2)

        pool = PgPool(pg_config)
        pool._acquire()
        pool.close()
