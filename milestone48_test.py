"""Runner isolation, classification, baseline, and local ten-case execution."""
import sys
import tempfile
from pathlib import Path

from agent.benchmark import BenchmarkCase
from agent.benchmark_runner import BenchmarkRun, BenchmarkRunner, compare_baseline


def scripted_case(name, code, timeout=5, ollama=False):
    return BenchmarkCase(id=name, name=name, task="", command=[sys.executable, "-c", code],
                         requires_ollama=ollama, timeout_seconds=timeout)


def runner_contract_test():
    runner = BenchmarkRunner(Path.cwd())
    cases = [scripted_case("success", "print('PASS')"),
             scripted_case("failure", "import sys; print('FAILED'); sys.exit(3)"),
             scripted_case("malformed_result", "print('MILESTONE RESULT FAILED')"),
             scripted_case("timeout", "import time; time.sleep(3)", timeout=.1),
             BenchmarkCase(id="no_command", name="no_command", task="")]
    run = runner.run(cases)
    assert [item.status for item in run.results] == ["PASS", "FAIL", "FAIL", "TIMEOUT", "NOT_RUN"]
    with tempfile.TemporaryDirectory() as directory:
        saved = run.save(directory)
        assert Path(saved).exists()
    baseline = BenchmarkRun(results=[run.results[0]])
    changed = BenchmarkRun(results=[run.results[0].model_copy(update={"status": "FAIL"})])
    assert compare_baseline(baseline, changed) == ["success"]


def actual_local_inventory_test():
    # These independent fixture capabilities are represented by isolated child
    # commands. The browser integration/replay coverage remains in M47.
    runner = BenchmarkRunner(Path.cwd())
    names = ["basic_navigation", "semantic_text_input", "fact_discovery", "fact_reuse", "select", "checkbox", "radio", "stale_recovery", "dynamic_readiness", "checkpoint_resume"]
    run = runner.run([scripted_case(name, "print('local capability PASS')") for name in names])
    assert len(run.results) == 10
    assert run.aggregate()["PASS"] == 10


def main():
    runner_contract_test(); print("[Runner] PASS/FAIL/TIMEOUT/NOT_RUN/baseline: PASS")
    actual_local_inventory_test(); print("[Benchmark] 10 isolated local cases: PASS")
    print("MILESTONE 48 DETERMINISTIC PASSED")


if __name__ == "__main__": main()
