"""Declarative local test registry; runner behaviour never branches by test id."""
import sys
from agent.benchmark import BenchmarkCase


def _case(script, category="deterministic", ollama=False, browser=True, external=False, timeout=None):
    return BenchmarkCase(id=script.removesuffix(".py"), name=script, task="", command=[sys.executable, script],
        category=category, requires_ollama=ollama, requires_browser=browser, external_dependency=external,
        timeout_seconds=timeout or (180 if ollama else 75))


def regression_cases(include_external=False):
    deterministic = ["task_context_test.py", "task_fact_planner_test.py", "milestone38_test.py", "milestone39_test.py",
        "milestone40_test.py", "milestone41_test.py", "milestone42_test.py", "milestone43_test.py", "milestone44_test.py",
        "milestone45_test.py", "milestone46_test.py", "milestone47_test.py", "milestone48_test.py", "stale_memory_test.py", "recovery_test.py", "runtime_recovery_test.py"]
    cases = [_case(script, "recovery" if "recovery" in script else "deterministic") for script in deterministic]
    cases += [_case(script, "real_llm", ollama=True, timeout=240) for script in ["milestone42_real_llm_test.py", "milestone43_real_llm_test.py", "milestone44_real_llm_test.py", "milestone45_real_llm_test.py", "milestone46_real_llm_test.py", "milestone47_real_llm_test.py", "milestone48_real_llm_test.py"]]
    if include_external: cases.append(_case("main.py", "external_smoke", external=True, timeout=90))
    return cases
