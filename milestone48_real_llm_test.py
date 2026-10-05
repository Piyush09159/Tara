"""M48 real-Qwen entrypoint, intentionally delegated to the local M47 flow."""
import subprocess
import sys
from agent.benchmark import BenchmarkCase
from agent.benchmark_runner import BenchmarkRunner


def main():
    runner = BenchmarkRunner()
    case = BenchmarkCase(id="m47_real_cross_page", name="M47 real cross-page fact reuse", task="",
        command=[sys.executable, "milestone47_real_llm_test.py"], category="real_llm",
        requires_ollama=True, requires_browser=True, timeout_seconds=240)
    run = runner.run([case]); result = run.results[0]
    print("[M48 real benchmark]", run.aggregate())
    print("[M48 real benchmark] status:", result.status)
    if result.status != "PASS": raise SystemExit("MILESTONE 48 REAL LLM FAILED")
    print("MILESTONE 48 REAL LLM PASSED")


if __name__ == "__main__": main()
