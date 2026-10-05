# Tara

Tara is a local, goal-driven browser agent built with Python, Playwright,
Ollama, Qwen2.5-Coder, and Pydantic. It plans browser actions from compact,
structured page state rather than screenshots or brittle historical selectors.

## How it works

Tara follows a synchronous agent loop:

```text
Observe -> Understand -> Plan -> Act -> Verify
                         |          |
                         +-> Recover +-> Re-observe / re-plan
```

The current page is always authoritative. Browser memory retains historical
context, while task-context memory stores DOM-free semantic facts such as a
verification code or customer reference for reuse after navigation.

## Capabilities

- Semantic links and buttons
- Text, email, password, search, URL, and textarea entry
- Native select-option interaction
- Checkbox checking/unchecking and radio selection
- Label extraction from explicit labels, ARIA labels, `aria-labelledby`,
  wrapping labels, placeholders, and names
- Current-page stable element resolution with stale-target protection
- Semantic task facts preserved across pages without selectors or DOM paths
- Recovery policy for unavailable, disabled, stale, and failed actions
- Bounded planner context and candidate diagnostics
- Append-only, local JSON traces with run/event IDs and atomic persistence
- Run summaries and structured failure categories for regression analysis
- Fresh-browser deterministic replay of safe recorded actions; password input
  is redacted and deliberately non-replayable
- Local benchmark case/result models for deterministic and real-Qwen baselines

## Project layout

```text
agent/       Goal decomposition, planning, evaluation, recovery, memory
browser/     Playwright browser wrapper, structured reader, and actions
llm/         Local Ollama client
tests/       Local HTML fixtures for deterministic browser tests
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run Ollama locally with the configured model:

```powershell
ollama pull qwen2.5-coder:7b
ollama serve
```

## Validation

Deterministic browser integration tests use only local HTML:

```powershell
python -m compileall .\agent .\browser .\llm
.\.venv\Scripts\python.exe .\milestone43_test.py
```

Real local-model validation:

```powershell
.\.venv\Scripts\python.exe .\milestone43_real_llm_test.py
```

The Milestone 43 tests cover a multi-control form (text fields, select,
checkbox, radio, submit) and a cross-page fact-to-form flow.

Milestone 47 adds local observability validation:

```powershell
.\.venv\Scripts\python.exe .\milestone47_test.py
.\.venv\Scripts\python.exe .\milestone47_real_llm_test.py
```

`AgentLoop.last_trace` holds the chronological run trace and
`AgentLoop.last_run_summary` holds its compact metrics. Call
`loop.last_trace.save()` to persist a trace below `.tara/traces/`. Password
values are redacted in trace, working-memory observations, browser snapshots,
and consequently checkpoints/planner context.

Milestone 48 provides isolated, UTF-8 benchmark execution and local result
artifacts:

```powershell
.\.venv\Scripts\python.exe .\milestone48_test.py
```

`agent.benchmark_registry.regression_cases()` declares the regression matrix.
`BenchmarkRunner` launches each configured test in a separate child process,
captures stdout/stderr, applies its timeout, checks local Ollama before
real-model cases, and writes schema-versioned reports under
`.tara/benchmarks/`. A prior PASS changing to any non-PASS status is reported
as a regression; small timing changes are informational only.

## Design principles

- Keep semantic facts separate from browser references.
- Re-resolve every executable target from the current PageState.
- Never treat an old element ID as permanent truth.
- Keep planner context bounded while preserving full internal memory.
- Prefer structured browser semantics over screenshots.
