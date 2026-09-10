# Foundry Evals Integration Samples

These samples demonstrate evaluating agent-framework agents using Microsoft Foundry's built-in evaluators.

## Available Evaluators

| Category | Evaluators |
|----------|-----------|
| **Agent behavior** | `intent_resolution`, `task_adherence`, `task_completion`, `task_navigation_efficiency` |
| **Tool usage** | `tool_call_accuracy`, `tool_selection`, `tool_input_accuracy`, `tool_output_utilization`, `tool_call_success` |
| **Quality** | `coherence`, `fluency`, `relevance`, `groundedness`, `response_completeness`, `similarity` |
| **Safety** | `violence`, `sexual`, `self_harm`, `hate_unfairness` |

## Samples

### `evaluate_agent_sample.py` — Dataset Evaluation (Path 3)

The dev inner loop. Pass existing responses or let `evaluate_agent()` run the
agent against test queries before submitting provider-neutral `EvalItem` data
to Foundry.

```bash
uv run samples/05-end-to-end/evaluation/foundry_evals/evaluate_agent_sample.py
```

### `evaluate_tool_calls_sample.py` — Explicit Eval Items

For more control, run the agent yourself, construct public `EvalItem` instances
from the conversation and typed tools, inspect or modify them, and pass them to
`FoundryEvals.evaluate()`.

```bash
uv run samples/05-end-to-end/evaluation/foundry_evals/evaluate_tool_calls_sample.py
```

### `evaluate_traces_sample.py` — Trace & Response Evaluation (Path 1)

Evaluate what already happened — zero changes to agent code:

1. **`evaluate_traces(response_ids=...)`** — Evaluate Responses API responses by ID
2. **`evaluate_traces(agent_id=...)`** — Evaluate agent behavior from OTel traces in App Insights

```bash
uv run samples/05-end-to-end/evaluation/foundry_evals/evaluate_traces_sample.py
```

### Referencing a rubric evaluator created in Foundry

Foundry users can create rubric evaluators in the Foundry portal (or
through the dedicated SDK / REST surface). Once an evaluator exists,
agent-framework consumes it like any other evaluator: pass a
`GeneratedEvaluatorRef(name=..., version=...)` in the `evaluators=`
list and pin the version for reproducible runs.

```python
from agent_framework.foundry import FoundryEvals, GeneratedEvaluatorRef

evals = FoundryEvals(
    evaluators=[
        GeneratedEvaluatorRef(name="reservation-policy-rubric", version="3"),
        "relevance",
        "coherence",
    ],
)
```

Quality gates on rubric output use the standard `EvalResults` helpers,
including `assert_dimension_score_at_least(...)` for per-dimension
thresholds.

See [`evaluate_with_rubric_sample.py`](./evaluate_with_rubric_sample.py)
for a runnable end-to-end example that combines a rubric evaluator with
built-in evaluators and gates a per-dimension threshold.

## Setup

Create a `.env` file with configuration as in the `.env.example` file in this folder.

## Which sample should I start with?

- **"I want to test my agent during development"** → `evaluate_agent_sample.py`, Pattern 1
- **"I want to evaluate past agent runs"** → `evaluate_traces_sample.py`
- **"I want to inspect/modify eval data before submitting"** → `evaluate_tool_calls_sample.py`
- **"I want to score against a custom rubric I created in Foundry"** → `evaluate_with_rubric_sample.py`
