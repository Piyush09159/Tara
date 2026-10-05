"""Isolated, local benchmark execution and conservative regression gating."""
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.error import URLError
from urllib.request import urlopen

from pydantic import BaseModel, Field

from agent.benchmark import BenchmarkCase
from agent.trace import sanitize_trace_data


class BenchmarkCaseResult(BaseModel):
    case_id: str
    name: str
    status: str
    duration_seconds: float = 0.0
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    failure_reason: str = ""
    environment_reason: str = ""
    cleanup_performed: bool = False
    model: str = ""
    trace_path: Optional[str] = None


class BenchmarkRun(BaseModel):
    benchmark_version: int = 1
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    python_version: str = Field(default_factory=lambda: sys.version)
    platform: str = Field(default_factory=platform.platform)
    ollama: Dict[str, object] = Field(default_factory=dict)
    results: List[BenchmarkCaseResult] = Field(default_factory=list)

    def aggregate(self):
        counts = {status: 0 for status in ("PASS", "FAIL", "BLOCKED", "TIMEOUT", "ENVIRONMENT_ERROR", "NOT_RUN")}
        for result in self.results: counts[result.status] = counts.get(result.status, 0) + 1
        total = len(self.results)
        return {"total": total, **counts, "success_rate": counts["PASS"] / total if total else 0.0}

    def save(self, directory=".tara/benchmarks"):
        target = Path(directory); target.mkdir(parents=True, exist_ok=True)
        path = target / f"{self.run_id}.json"
        fd, temporary = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=target)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        return str(path)


def ollama_preflight(model="qwen2.5-coder:7b"):
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = [item.get("name", "") for item in payload.get("models", [])]
        return {"reachable": True, "models": names, "requested_model": model, "model_available": model in names}
    except (URLError, OSError, ValueError) as error:
        return {"reachable": False, "models": [], "requested_model": model, "model_available": False, "reason": str(error)}


def playwright_preflight():
    """Verify the runtime can launch locally; no network navigation occurs."""
    probe = "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()"
    try:
        completed = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20)
        return {"available": completed.returncode == 0, "reason": completed.stderr[-500:]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "reason": str(error)}


class BenchmarkRunner:
    """Runs one configured script per child process; it never starts Ollama."""
    def __init__(self, root=".", model="qwen2.5-coder:7b"):
        self.root = Path(root)
        self.model = model
        self.ollama = ollama_preflight(model)
        self.playwright = None

    def run_case(self, case: BenchmarkCase) -> BenchmarkCaseResult:
        case_id = case.id or case.name
        if case.requires_ollama and not self.ollama.get("model_available"):
            return BenchmarkCaseResult(case_id=case_id, name=case.name, status="BLOCKED", model=self.model,
                environment_reason="Ollama service/model unavailable: " + str(self.ollama.get("reason", "requested model missing")))
        if not case.command:
            return BenchmarkCaseResult(case_id=case_id, name=case.name, status="NOT_RUN", failure_reason="No command configured")
        if case.requires_browser:
            self.playwright = self.playwright or playwright_preflight()
            if not self.playwright.get("available"):
                return BenchmarkCaseResult(case_id=case_id, name=case.name, status="ENVIRONMENT_ERROR",
                    environment_reason="Playwright unavailable: " + str(self.playwright.get("reason", "")))
        environment = os.environ.copy(); environment["PYTHONIOENCODING"] = "utf-8"; environment["PYTHONUTF8"] = "1"
        command = list(case.command)
        # Python's buffered output caused earlier real-model runs to appear
        # detached. Keep commands declarative while making Python children
        # terminal-capturable by this runner.
        if command and Path(command[0]).name.lower().startswith("python") and "-u" not in command:
            command.insert(1, "-u")
        started = time.perf_counter(); process = None; stdout = ""; stderr = ""
        try:
            process = subprocess.Popen(command, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", env=environment)
            stdout, stderr = process.communicate(timeout=case.timeout_seconds)
            duration = time.perf_counter() - started
        except subprocess.TimeoutExpired as error:
            if process: process.kill(); stdout, stderr = process.communicate()
            return BenchmarkCaseResult(case_id=case_id, name=case.name, status="TIMEOUT", duration_seconds=time.perf_counter()-started,
                stdout=sanitize_trace_data(stdout or ""), stderr=sanitize_trace_data(stderr or ""), failure_reason="timeout", cleanup_performed=True, model=self.model if case.requires_ollama else "")
        except OSError as error:
            return BenchmarkCaseResult(case_id=case_id, name=case.name, status="ENVIRONMENT_ERROR", duration_seconds=time.perf_counter()-started, environment_reason=str(error))
        stdout, stderr = sanitize_trace_data(stdout), sanitize_trace_data(stderr)
        # Existing scripts sometimes print an explicit terminal failure but
        # return 0. Do not mistake routine diagnostics such as "Failed
        # actions: 0" for a failure.
        failed_marker = bool(re.search(r"(?im)^\s*(?:❌\s*)?(?:MILESTONE(?:\s+\d+)?|TEST|REAL\s+LLM)[^\n]*\bFAILED\b", stdout))
        status = "PASS" if process.returncode == 0 and not failed_marker else "FAIL"
        return BenchmarkCaseResult(case_id=case_id, name=case.name, status=status, duration_seconds=duration,
            exit_code=process.returncode, stdout=stdout, stderr=stderr,
            failure_reason="explicit failure output" if failed_marker else (stderr[-1000:] if status == "FAIL" else ""), model=self.model if case.requires_ollama else "")

    def run(self, cases: Iterable[BenchmarkCase]):
        run = BenchmarkRun(ollama=self.ollama)
        run.results = [self.run_case(case) for case in cases]
        return run


def compare_baseline(baseline: BenchmarkRun, current: BenchmarkRun):
    """Only a prior PASS becoming non-PASS is a hard regression."""
    old = {result.case_id: result for result in baseline.results}
    return [case_id for case_id, result in ((item.case_id, item) for item in current.results)
            if case_id in old and old[case_id].status == "PASS" and result.status != "PASS"]
