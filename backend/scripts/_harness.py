"""Shared runner for the live BharatCode capability scripts. Never prints the API key."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.bharatcode_client import BharatCodeClient, BharatCodeError, ChatResult  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252

MODELS = ["qwen-3.8-27b", "deepseek-v4.1-flash"]
RESULTS_DIR = Path(__file__).resolve().parent / "results"  # git-ignored


class Skip(Exception):
    pass


def parse_models(description: str) -> list[str]:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--model", default=settings.bharatcode_model)
    ap.add_argument("--all-models", action="store_true", help=f"run against {', '.join(MODELS)}")
    a = ap.parse_args()
    return MODELS if a.all_models else [a.model]


def require_key() -> BharatCodeClient:
    if not settings.llm_configured:
        print("[SKIP] BHARATCODE_API_KEY is not set. Put it in .env (repo root or backend/) or the environment.")
        sys.exit(2)
    return BharatCodeClient(settings)


class Run:
    def __init__(self, script: str, model: str):
        self.script, self.model, self.rows = script, model, []
        self.blocked: str | None = None  # set when the model is unusable (e.g. no plan access)
        print(f"\n=== {script} | model={model} | base_url={settings.bharatcode_base_url}")

    def check(self, name: str, fn):
        """fn returns (passed: bool, detail: str, ChatResult | list[ChatResult] | None)."""
        if self.blocked:
            return self._record(name, "NOT TESTED", self.blocked, [], 0)
        t0 = time.perf_counter()
        try:
            ok, detail, results = fn()
            status = "PASS" if ok else "FAIL"
        except Skip as e:
            status, detail, results = "NOT TESTED", str(e), None
        except BharatCodeError as e:
            status, detail, results = "FAIL", f"{e} code={e.code} request_id={e.request_id}", None
            if e.kind in ("invalid_credentials", "access_denied", "not_found"):
                self.blocked = f"blocked by earlier {e.kind} (HTTP {e.status})"
        results = results if isinstance(results, list) else [results] if results else []
        return self._record(name, status, detail, results, time.perf_counter() - t0)

    def _record(self, name, status, detail, results: list[ChatResult], elapsed):
        tokens = sum(r.usage.get("total_tokens", 0) for r in results) or None
        row = {"check": name, "status": status, "detail": detail, "wall_s": round(elapsed, 2),
               "model_latency_s": round(sum(r.latency_s for r in results), 2) or None, "total_tokens": tokens,
               "finish_reasons": [r.finish_reason for r in results],
               "request_ids": [r.request_id for r in results if r.request_id]}
        self.rows.append(row)
        print(f"[{status}] {name} ({elapsed:.1f}s, tokens={tokens}) {detail}")
        return row

    def save(self) -> bool:
        RESULTS_DIR.mkdir(exist_ok=True)
        out = RESULTS_DIR / f"{self.script}--{self.model}.json"
        out.write_text(json.dumps({"script": self.script, "model": self.model,
                                   "at": datetime.now(timezone.utc).isoformat(), "checks": self.rows}, indent=2))
        print(f"saved {out.relative_to(RESULTS_DIR.parent.parent)}")
        return all(r["status"] == "PASS" for r in self.rows)
