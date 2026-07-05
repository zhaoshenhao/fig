from __future__ import annotations

import sys
from pathlib import Path

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestApiCall:
    def test_no_url_returns_error(self):
        from src.engine.tools.api_call import api_call
        from src.session.data import SessionData

        result = api_call({"url": ""}, SessionData())
        assert "no url specified" in result["error"]

    def test_resolves_template_variables(self):
        from src.engine.tools.api_call import _resolve
        from src.session.data import SessionData

        sess = SessionData()
        sess.nodes = [{"name": "input", "data": {"text": "hello world"}}]
        sess.data_map["key"] = "value"

        result = _resolve("{{query}} {{key}}", sess)
        assert result == "hello world value"


class TestWebSearch:
    def test_unknown_engine(self):
        from src.engine.tools.web_search import web_search
        from src.session.data import SessionData

        result = web_search({"engine": "google"}, SessionData())
        assert "unknown" in result["text"]


class TestCodeExec:
    def test_executes_python(self):
        from src.engine.tools.code_exec import code
        from src.session.data import SessionData

        result = code({"code": "print(1 + 2)"}, SessionData())
        assert result["stdout"] == "3"

    def test_captures_error(self):
        from src.engine.tools.code_exec import code
        from src.session.data import SessionData

        result = code({"code": "raise ValueError('bad')"}, SessionData())
        assert "ValueError" in result["error"]

    def test_no_code_returns_error(self):
        from src.engine.tools.code_exec import code
        from src.session.data import SessionData

        result = code({}, SessionData())
        assert "no code" in result["error"]

    def test_resolves_session_variables(self):
        from src.engine.tools.code_exec import _resolve
        from src.session.data import SessionData

        sess = SessionData()
        sess.nodes = [{"name": "input", "data": {"text": "hi"}}]
        sess.data_map["order_id"] = "123"

        result = _resolve("{{query}} {{order_id}} {{chat_id}}", sess)
        assert "hi" in result
        assert "123" in result

    def test_blocked_imports(self):
        from src.engine.tools.code_exec import code
        from src.session.data import SessionData

        result = code({"code": "import os"}, SessionData())
        assert "not allowed" in result["error"]

    def test_allowed_imports(self):
        from src.engine.tools.code_exec import code
        from src.session.data import SessionData

        result = code({"code": "import json; print(json.dumps({'a': 1}))"}, SessionData())
        assert result["stdout"] == '{"a": 1}'


class TestPrometheus:
    def test_counter_inc_and_collect(self):
        from src.metrics.prometheus import Counter

        c = Counter()
        c.inc()
        c.inc({"method": "GET"})

        lines = c.collect("test_counter")
        assert len(lines) >= 3  # HELP, TYPE, + at least 1 value

    def test_histogram_observe_and_collect(self):
        from src.metrics.prometheus import Histogram

        h = Histogram(buckets=[0.5, 1.0, 2.0])
        h.observe(0.3)
        h.observe(1.5, {"method": "GET"})

        lines = h.collect("test_histogram")
        assert len(lines) >= 3

    def test_registry_generate(self):
        from src.metrics.prometheus import MetricsRegistry

        r = MetricsRegistry()
        r.counter("my_counter").inc()
        r.histogram("my_histogram").observe(0.5)

        output = r.generate_latest()
        assert "my_counter" in output
        assert "my_histogram" in output


class TestLogger:
    def test_get_logger_initializes(self):
        from src.logger import _ensure_initialized, get_logger

        _ensure_initialized()
        log = get_logger("test.logger.extra")
        assert log is not None

    def test_json_formatter(self):
        import logging

        from src.logger import JSONFormatter, _ensure_initialized

        _ensure_initialized()
        fmtr = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=1,
            msg="test message", args=(), exc_info=None,
        )
        record.request_id = "abc123"

        output = fmtr.format(record)
        assert "test message" in output
        assert "request_id" in output
