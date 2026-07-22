#!/usr/bin/env python3
"""KF API 性能测试脚本 — 使用知识库问题对 workflow 进行多轮对话压力测试。

用法:
  python tests/perf/perf_test.py -q questions.json -k <API_KEY>
  python tests/perf/perf_test.py -q questions.json -k <API_KEY> -b http://localhost:9000
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import httpx2 as httpx
except ImportError:
    import httpx

WORKFLOW_DEFAULT = "auto_film"
API_BASE_URL = os.environ.get("KF_API_URL", "http://localhost:9000")
DEFAULT_TIMEOUT = 120.0


class PerfRunner:
    def __init__(self, base_url: str, api_key: str = "", timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key} if api_key else {}
        self.timeout = timeout
        self.client = httpx.Client(timeout=self.timeout)

    def _post(self, path: str, payload: dict) -> dict:
        return self.client.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=self.headers,
        )

    def run_session(self, session_id: int, workflow: str, questions: list[str]) -> list[dict]:
        chat_id = None
        results = []
        for i, question in enumerate(questions):
            payload: dict = {"query": question}
            if chat_id:
                payload["chat_id"] = chat_id

            t0 = time.perf_counter()
            try:
                resp = self._post(f"/api/v1/workflows/{workflow}/run", payload)
                elapsed = round((time.perf_counter() - t0) * 1000, 1)
                if resp.status_code == 200:
                    data = resp.json()
                    chat_id = data.get("chat_id")
                    reply_len = len(data.get("reply", ""))
                    results.append({
                        "turn": i + 1,
                        "question": question[:60],
                        "status": resp.status_code,
                        "latency_ms": elapsed,
                        "success": True,
                        "reply_len": reply_len,
                        "chat_id": chat_id,
                    })
                else:
                    results.append({
                        "turn": i + 1,
                        "question": question[:60],
                        "status": resp.status_code,
                        "latency_ms": elapsed,
                        "success": False,
                        "error": resp.text[:200],
                    })
            except Exception as exc:
                elapsed = round((time.perf_counter() - t0) * 1000, 1)
                results.append({
                    "turn": i + 1,
                    "question": question[:60],
                    "status": 0,
                    "latency_ms": elapsed,
                    "success": False,
                    "error": str(exc),
                })
        return results

    def close(self):
        self.client.close()


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * p / 100.0
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_vals):
        return sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])
    return sorted_vals[f]


def fmt_ms(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.1f}s"


def main():
    parser = argparse.ArgumentParser(description="KF API Performance Test")
    parser.add_argument("--questions-file", "-q", required=True, type=Path, help="JSON 问题文件路径")
    parser.add_argument("--api-key", "-k", default="", help="X-API-Key (留空则跳过鉴权)")
    parser.add_argument("--base-url", "-b", default=API_BASE_URL, help=f"KF API 地址 (默认: {API_BASE_URL})")
    parser.add_argument("--workflow", "-w", default=WORKFLOW_DEFAULT, help=f"全局默认 workflow (默认: {WORKFLOW_DEFAULT})")
    parser.add_argument("--parallel", "-p", type=int, default=1, help="并发 session 数 (1=串行)")
    parser.add_argument("--output", "-o", type=Path, help="结果输出 JSON 文件")
    args = parser.parse_args()

    if not args.questions_file.exists():
        print(f"[ERROR] 问题文件不存在: {args.questions_file}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(args.questions_file.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        print("[ERROR] 问题文件格式错误：顶层应为 JSON 数组", file=sys.stderr)
        sys.exit(1)

    sessions = []
    for item in data:
        sid = item.get("session_id", len(sessions) + 1)
        workflow = item.get("workflow", args.workflow)
        questions = item.get("questions", [])
        if questions:
            sessions.append({"session_id": sid, "workflow": workflow, "questions": questions})

    total_sessions = len(sessions)
    total_questions = sum(len(s["questions"]) for s in sessions)

    print("=" * 72)
    print(f"  KF API Performance Test")
    print(f"  Base URL : {args.base_url}")
    print(f"  Workflow : {args.workflow}")
    print(f"  Sessions : {total_sessions}")
    print(f"  Questions: {total_questions}")
    print(f"  Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)
    print()

    runner = PerfRunner(args.base_url, args.api_key)
    all_results = []
    t_start = time.perf_counter()

    if args.parallel > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _do_session(sess):
            s_start = time.perf_counter()
            results = runner.run_session(sess["session_id"], sess["workflow"], sess["questions"])
            s_elapsed = round((time.perf_counter() - s_start) * 1000, 1)
            return {"session_id": sess["session_id"], "session_elapsed_ms": s_elapsed, "turns": results}

        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {executor.submit(_do_session, s): s for s in sessions}
            for future in as_completed(futures):
                all_results.append(future.result())
        all_results.sort(key=lambda r: r["session_id"])
    else:
        for session in sessions:
            s_start = time.perf_counter()
            results = runner.run_session(session["session_id"], session["workflow"], session["questions"])
            s_elapsed = round((time.perf_counter() - s_start) * 1000, 1)
            all_results.append({
                "session_id": session["session_id"],
                "session_elapsed_ms": s_elapsed,
                "turns": results,
            })
            ok_count = sum(1 for r in results if r["success"])
            print(f"  Session {session['session_id']:2d}  {ok_count}/{len(results)} ok  {fmt_ms(s_elapsed)}")

    runner.close()
    t_total = round((time.perf_counter() - t_start) * 1000, 1)

    all_latencies = []
    total_ok = 0
    total_fail = 0
    for sr in all_results:
        for r in sr["turns"]:
            all_latencies.append(r["latency_ms"])
            if r["success"]:
                total_ok += 1
            else:
                total_fail += 1

    avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0

    print()
    print("=" * 72)
    print("  Results Summary")
    print("=" * 72)
    print(f"  Total time     : {fmt_ms(t_total)}")
    print(f"  Total requests : {len(all_latencies)}")
    print(f"  Success        : {total_ok}")
    print(f"  Failed         : {total_fail}")
    print(f"  Avg latency    : {fmt_ms(avg_latency)}")
    print(f"  Min latency    : {fmt_ms(min(all_latencies))}")
    print(f"  Max latency    : {fmt_ms(max(all_latencies))}")
    print(f"  P50            : {fmt_ms(percentile(all_latencies, 50))}")
    print(f"  P90            : {fmt_ms(percentile(all_latencies, 90))}")
    print(f"  P95            : {fmt_ms(percentile(all_latencies, 95))}")
    print(f"  P99            : {fmt_ms(percentile(all_latencies, 99))}")
    print(f"  Finished       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    report = {
        "start_time": datetime.now().isoformat(),
        "base_url": args.base_url,
        "workflow": args.workflow,
        "total_sessions": total_sessions,
        "total_questions": total_questions,
        "total_elapsed_ms": t_total,
        "total_success": total_ok,
        "total_failed": total_fail,
        "latency_avg_ms": round(avg_latency, 1),
        "latency_min_ms": round(min(all_latencies), 1),
        "latency_max_ms": round(max(all_latencies), 1),
        "latency_p50_ms": round(percentile(all_latencies, 50), 1),
        "latency_p90_ms": round(percentile(all_latencies, 90), 1),
        "latency_p95_ms": round(percentile(all_latencies, 95), 1),
        "latency_p99_ms": round(percentile(all_latencies, 99), 1),
        "sessions": all_results,
    }

    if args.output:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n  Report saved to: {args.output}")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
