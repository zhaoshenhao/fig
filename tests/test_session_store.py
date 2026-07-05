from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestSessionData:
    def test_chat_id_starts_with_chat_prefix(self):
        from src.session.data import SessionData

        sess = SessionData()
        assert sess.chat_id.startswith("chat_")

    def test_turn_id_starts_at_zero(self):
        from src.session.data import SessionData

        sess = SessionData()
        assert sess.turn_id == 0

    def test_add_turn_creates_turn_record(self):
        from src.session.data import SessionData

        sess = SessionData()
        sess.add_turn("hello", "world")
        assert len(sess.history) == 1
        assert sess.turn_id == 1
        assert sess.history[0].input == "hello"
        assert sess.history[0].output == "world"
        assert sess.history[0].input_timestamp > 0
        assert sess.history[0].output_timestamp > 0

    def test_add_turn_accumulates(self):
        from src.session.data import SessionData

        sess = SessionData()
        sess.add_turn("q1", "a1")
        sess.add_turn("q2", "a2")
        assert len(sess.history) == 2
        assert sess.turn_id == 2
        assert sess.completed_turns == 2

    def test_data_map_operations(self):
        from src.session.data import SessionData

        sess = SessionData()
        sess.data_map["key1"] = "value1"
        sess.data_map["key2"] = "value2"
        assert sess.data_map["key1"] == "value1"
        sess.data_map["key1"] = "updated"
        assert sess.data_map["key1"] == "updated"

    def test_long_mem_data(self):
        from src.session.data import SessionData

        sess = SessionData()
        assert sess.long_mem_data == ""
        sess.long_mem_data = "VIP customer"
        assert sess.long_mem_data == "VIP customer"

    def test_serialization_roundtrip(self):
        from src.session.data import SessionData

        sess = SessionData(_workflow="wf", return_mode="full", turn_id=3)
        sess.data_map["order"] = "123"
        sess.long_mem_data = "memory"
        sess.add_turn("q", "a")
        sess.nodes = [{"name": "input", "data": {"text": "q"}}]

        raw = sess.to_dict()
        restored = SessionData.from_dict(raw)

        assert restored.chat_id == sess.chat_id
        assert restored.turn_id == 4
        assert restored._workflow == "wf"
        assert restored.data_map == {"order": "123"}
        assert restored.long_mem_data == "memory"
        assert len(restored.history) == 1
        assert restored.history[0].input == "q"
        assert restored.nodes == sess.nodes

    def test_dict_compat_getitem(self):
        from src.session.data import SessionData

        sess = SessionData(_workflow="test_wf")
        assert sess["_workflow"] == "test_wf"
        assert sess["chat_id"].startswith("chat_")

    def test_dict_compat_setitem(self):
        from src.session.data import SessionData

        sess = SessionData()
        sess["return_mode"] = "last"
        assert sess.return_mode == "last"

    def test_dict_compat_get(self):
        from src.session.data import SessionData

        sess = SessionData()
        assert sess.get("bogus", "fallback") == "fallback"
        assert sess.get("_workflow") == ""

    def test_dict_compat_setdefault(self):
        from src.session.data import SessionData

        sess = SessionData()
        val = sess.setdefault("_workflow", "default_wf")
        assert val == ""
        val2 = sess.setdefault("nonexistent", "created")
        assert val2 == "created"

    def test_dict_compat_contains(self):
        from src.session.data import SessionData

        sess = SessionData()
        assert "chat_id" in sess
        assert "bogus_key" not in sess

    def test_current_query_finds_last_input(self):
        from src.session.data import SessionData

        sess = SessionData()
        sess.nodes = [
            {"name": "input", "data": {"text": "first"}},
            {"name": "retrieve"},
            {"name": "input", "data": {"text": "second"}},
        ]
        assert sess.current_query == "second"

    def test_current_query_empty_when_no_input(self):
        from src.session.data import SessionData

        sess = SessionData()
        assert sess.current_query == ""

    def test_current_context_finds_last_non_input(self):
        from src.session.data import SessionData

        sess = SessionData()
        sess.nodes = [
            {"name": "input", "data": {"text": "q"}},
            {"name": "retrieve", "data": {"text": "context text"}},
            {"name": "generate", "data": {"text": "final"}},
        ]
        assert sess.current_context == "final"

    def test_completed_turns(self):
        from src.session.data import SessionData

        sess = SessionData()
        assert sess.completed_turns == 0
        sess.add_turn("q1", "a1")
        sess.add_turn("q2", "a2")
        assert sess.completed_turns == 2

    def test_from_dict_backward_compat_role_content(self):
        from src.session.data import SessionData

        sess = SessionData.from_dict({
            "chat_id": "chat_test",
            "turn_id": 1,
            "created_at": 1000.0,
            "last_active_at": 1000.0,
            "_workflow": "wf",
            "return_mode": "full",
            "history": [
                {"role": "user", "content": "old_q"},
                {"role": "assistant", "content": "old_a"},
            ],
            "data_map": {},
            "long_mem_data": "",
            "nodes": [],
        })
        assert len(sess.history) == 2
        assert sess.history[0].input == "old_q"


class TestTrimOrCompress:
    def test_trim_truncates_by_max_turns(self):
        from src.session.data import SessionData

        sess = SessionData()
        for i in range(10):
            sess.add_turn(f"q{i}", f"a{i}")

        sess.trim_or_compress(max_turns=5, keep=3)
        assert len(sess.history) == 3

    def test_trim_triggers_by_max_chars(self):
        from src.session.data import SessionData

        sess = SessionData()
        for i in range(20):
            sess.add_turn(f"q{i}", f"a{i}")

        total_chars = sum(len(t.input) + len(t.output) for t in sess.history)
        sess.trim_or_compress(max_chars=total_chars - 1, keep=2)
        assert len(sess.history) == 2

    def test_trim_noop_when_under_limit(self):
        from src.session.data import SessionData

        sess = SessionData()
        sess.add_turn("q", "a")
        sess.trim_or_compress(max_turns=10, keep=5)
        assert len(sess.history) == 1

    def test_trim_noop_with_no_params(self):
        from src.session.data import SessionData

        sess = SessionData()
        sess.add_turn("q", "a")
        sess.trim_or_compress()
        assert len(sess.history) == 1

    def test_trim_noop_empty_history(self):
        from src.session.data import SessionData

        sess = SessionData()
        sess.trim_or_compress(max_turns=10, keep=5)
        assert len(sess.history) == 0

    def test_compress_generates_summary_turn(self, mocker):
        mock_client = mocker.patch("src.llm.client.LLMClient")
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        mock_instance.chat.return_value = {
            "choices": [{"message": {"content": "summary text"}}],
        }

        from src.session.data import SessionData

        sess = SessionData()
        for i in range(10):
            sess.add_turn(f"question {i}", f"answer {i}")

        sess.trim_or_compress(
            max_turns=5, keep=2, compress_max_words=500,
            summary_base_url="http://llm",
            summary_api_key="key",
            summary_model="model",
            summary_system_prompt="compress {max_words} words",
        )

        assert len(sess.history) == 3
        assert sess.history[0].input == "[前8轮摘要]"
        assert sess.history[0].output == "summary text"
        assert mock_instance.chat.called

    def test_compress_fallback_on_llm_failure(self, mocker):
        mock_client = mocker.patch("src.llm.client.LLMClient")
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        mock_instance.chat.side_effect = RuntimeError("llm down")

        from src.session.data import SessionData

        sess = SessionData()
        for i in range(10):
            sess.add_turn(f"q{i}", f"a{i}")

        sess.trim_or_compress(
            max_turns=5, keep=2, compress_max_words=500,
            summary_base_url="http://llm",
            summary_api_key="key",
            summary_model="model",
        )

        assert len(sess.history) == 2


class TestMemorySessionStore:
    def test_create_returns_session(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore()
        session = store.create("test_wf", "full")

        assert session["chat_id"].startswith("chat_")
        assert session["created_at"] > 0
        assert session["_workflow"] == "test_wf"
        assert session["return_mode"] == "full"

    def test_get_returns_created_session(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore()
        session = store.create("wf", "full")
        cid = session["chat_id"]

        loaded = store.get(cid)
        assert loaded is not None
        assert loaded["chat_id"] == cid

    def test_get_returns_none_for_unknown(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore()
        assert store.get("bogus_id") is None

    def test_get_returns_none_for_expired(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore(max_age=1)
        session = store.create("wf", "full")
        cid = session["chat_id"]

        time.sleep(1.1)
        assert store.get(cid) is None

    def test_save_updates_last_active_at(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore(max_age=5)
        session = store.create("wf", "full")
        cid = session["chat_id"]
        original = session["last_active_at"]

        time.sleep(0.1)
        store.save(session)

        reloaded = store.get(cid)
        assert reloaded is not None
        assert reloaded["last_active_at"] > original

    def test_delete_removes_session(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore()
        session = store.create("wf", "full")
        cid = session["chat_id"]

        assert store.delete(cid) is True
        assert store.get(cid) is None

    def test_delete_returns_false_for_missing(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore()
        assert store.delete("nonexistent") is False

    def test_evicts_oldest_when_over_max_sessions(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore(max_sessions=3)
        s1 = store.create("w1", "full")
        time.sleep(0.01)
        s2 = store.create("w2", "full")
        time.sleep(0.01)
        s3 = store.create("w3", "full")
        time.sleep(0.01)
        s4 = store.create("w4", "full")

        assert store.get(s1["chat_id"]) is None
        assert store.get(s2["chat_id"]) is not None
        assert store.get(s3["chat_id"]) is not None
        assert store.get(s4["chat_id"]) is not None


class TestMemoryCleanup:
    def test_cleanup_expired_removes_only_expired(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore(max_age=1)
        s1 = store.create("wf", "full")
        c1 = s1["chat_id"]
        time.sleep(1.1)
        s2 = store.create("wf", "full")
        c2 = s2["chat_id"]

        removed = store.cleanup_expired()
        assert removed == 1
        assert store.get(c1) is None
        assert store.get(c2) is not None

    def test_cleanup_expired_returns_zero_when_none(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore(max_age=3600)
        s1 = store.create("wf", "full")
        s2 = store.create("wf", "full")

        removed = store.cleanup_expired()
        assert removed == 0
        assert store.get(s1["chat_id"]) is not None
        assert store.get(s2["chat_id"]) is not None

    def test_cleanup_expired_empty_store(self):
        from src.session.memory import MemorySessionStore

        store = MemorySessionStore()
        removed = store.cleanup_expired()
        assert removed == 0

    def test_cleanup_loop_runs_until_stopped(self):
        import threading

        from src.session.memory import MemorySessionStore

        store = MemorySessionStore(max_age=0)
        store.create("wf", "full")

        stop = threading.Event()
        store.max_age = 0  # 任何年龄都过期

        t = threading.Thread(
            target=store.cleanup_loop, args=(1, stop), daemon=True,
        )
        t.start()

        time.sleep(1.5)
        stop.set()
        t.join(timeout=3)

    def test_concurrent_access_does_not_raise(self):
        import threading

        from src.session.memory import MemorySessionStore

        store = MemorySessionStore(max_sessions=500)
        errors = []
        cids = []

        def worker():
            try:
                for _ in range(50):
                    s = store.create("wf", "full")
                    cids.append(s["chat_id"])
                    store.save(s)
                    store.get(s["chat_id"])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestRedisSessionStore:
    @pytest.fixture(autouse=True)
    def mock_redis(self, mocker):
        mock_client = MagicMock()
        mock_mod = mocker.patch("redis.Redis")
        mock_mod.from_url.return_value = mock_client
        return mock_client

    def test_create_stores_in_redis(self, mock_redis):
        from src.session.redis_store import RedisSessionStore

        store = RedisSessionStore(max_age=30)
        session = store.create("test_wf", "full")

        assert session["chat_id"].startswith("chat_")
        assert session["_workflow"] == "test_wf"
        assert mock_redis.setex.called

    def test_get_returns_none_when_redis_returns_none(self, mock_redis):
        from src.session.redis_store import RedisSessionStore

        mock_redis.get.return_value = None
        store = RedisSessionStore()
        assert store.get("missing") is None

    def test_get_returns_deserialized_session(self, mock_redis):
        import json

        from src.session.redis_store import RedisSessionStore

        session_data = {
            "chat_id": "chat_test123",
            "turn_id": 0,
            "created_at": 1000.0,
            "last_active_at": 1001.0,
            "_workflow": "wf",
            "return_mode": "full",
            "history": [
                {"input": "q1", "output": "a1",
                 "input_timestamp": 1000.0, "output_timestamp": 1001.0},
            ],
            "data_map": {},
            "long_mem_data": "",
            "nodes": [{"name": "input", "data": {"text": "q1"}}],
        }
        mock_redis.get.return_value = json.dumps(session_data)

        store = RedisSessionStore(prefix="test:")
        session = store.get("chat_test123")

        assert session is not None
        assert session["chat_id"] == "chat_test123"
        assert len(session["history"]) == 1

    def test_save_updates_redis_with_ttl(self, mock_redis):
        from src.session.redis_store import RedisSessionStore

        store = RedisSessionStore(max_age=60)
        session = store.create("wf", "full")
        mock_redis.setex.reset_mock()

        store.save(session)

        mock_redis.setex.assert_called_once()
        args, kwargs = mock_redis.setex.call_args
        assert args[1] == 60

    def test_delete_removes_from_redis(self, mock_redis):
        from src.session.redis_store import RedisSessionStore

        mock_redis.delete.return_value = 1
        store = RedisSessionStore()
        assert store.delete("chat_xyz") is True

    def test_delete_returns_false_for_missing(self, mock_redis):
        from src.session.redis_store import RedisSessionStore

        mock_redis.delete.return_value = 0
        store = RedisSessionStore()
        assert store.delete("missing") is False


class TestSessionStoreFactory:
    def test_create_memory_store(self):
        from src.session import create_session_store
        from src.session.memory import MemorySessionStore

        store = create_session_store({"store": "memory"})
        assert isinstance(store, MemorySessionStore)

    def test_create_redis_store(self, mocker):
        mocker.patch("redis.Redis")
        from src.session import create_session_store
        from src.session.redis_store import RedisSessionStore

        store = create_session_store({
            "store": "redis",
            "max_age": 1800,
            "redis": {"url": "redis://test:6379", "prefix": "kf:test:"},
        })
        assert isinstance(store, RedisSessionStore)
