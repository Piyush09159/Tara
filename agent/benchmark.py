"""Small local benchmark representation for repeatable Tara regressions."""
from statistics import median
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, Literal

from pydantic import BaseModel, Field


class BenchmarkCase(BaseModel):
    # Registry fields are optional so the M47 in-process benchmark API stays
    # compatible while M48 can execute declarative subprocess cases.
    id: str = ""
    name: str
    task: str
    fixture: str = ""
    expected_result: bool = True
    expected_facts: Dict[str, str] = Field(default_factory=dict)
    expected_final_state: Dict[str, Any] = Field(default_factory=dict)
    command: List[str] = Field(default_factory=list)
    category: str = "deterministic"
    requires_ollama: bool = False
    requires_browser: bool = False
    external_dependency: bool = False
    timeout_seconds: float = 60.0


class BenchmarkResult(BaseModel):
    name: str
    success: bool
    duration_seconds: float
    steps: int = 0
    planner_calls: int = 0
    deterministic_decisions: int = 0
    recovery_count: int = 0
    failures: List[Dict[str, Any]] = Field(default_factory=list)
    trace_path: Optional[str] = None


class BenchmarkSuite:
    def __init__(self):
        self.results: List[BenchmarkResult] = []

    def run_case(self, case: BenchmarkCase, runner: Callable[[BenchmarkCase], Any]) -> BenchmarkResult:
        started = perf_counter()
        try:
            loop, actual = runner(case)
            summary = getattr(loop, "last_run_summary", None)
            result = BenchmarkResult(name=case.name, success=(actual == case.expected_result),
                duration_seconds=perf_counter() - started,
                steps=getattr(summary, "total_steps", 0), planner_calls=getattr(summary, "planner_calls", 0),
                deterministic_decisions=getattr(summary, "deterministic_decisions", 0),
                recovery_count=getattr(summary, "recovery_count", 0),
                trace_path=getattr(loop, "last_trace_path", None))
        except Exception as error:
            result = BenchmarkResult(name=case.name, success=False, duration_seconds=perf_counter() - started,
                                     failures=[{"category": "task_failure", "error_type": type(error).__name__, "error": str(error)}])
        self.results.append(result)
        return result

    def aggregate(self) -> Dict[str, Any]:
        successes = [result for result in self.results if result.success]
        durations = [result.duration_seconds for result in self.results]
        return {"cases": len(self.results), "successes": len(successes), "failures": len(self.results) - len(successes),
                "success_rate": len(successes) / len(self.results) if self.results else 0.0,
                "median_steps": median([result.steps for result in successes]) if successes else 0,
                "median_llm_calls": median([result.planner_calls for result in successes]) if successes else 0,
                "recovery_rate": sum(result.recovery_count for result in self.results) / len(self.results) if self.results else 0.0,
                "average_duration": sum(durations) / len(durations) if durations else 0.0}
