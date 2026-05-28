# Foundry Evals Integration Samples

These samples demonstrate evaluating agent-framework agents using Azure AI Foundry's built-in evaluators.

## Available Evaluators

| Category | Evaluators |
|----------|-----------|
| **Agent behavior** | `intent_resolution`, `task_adherence`, `task_completion`, `task_navigation_efficiency` |
| **Tool usage** | `tool_call_accuracy`, `tool_selection`, `tool_input_accuracy`, `tool_output_utilization`, `tool_call_success` |
| **Quality** | `coherence`, `fluency`, `relevance`, `groundedness`, `response_completeness`, `similarity` |
| **Safety** | `violence`, `sexual`, `self_harm`, `hate_unfairness` |

## Samples

### `evaluate_agent_sample.py` — Dataset Evaluation (Path 3)

The dev inner loop. Two patterns from simplest to most control:

1. **`evaluate_agent()`** — One call: runs agent → converts → evaluates
2. **`FoundryEvals.evaluate()`** — Run agent yourself, convert with `AgentEvalConverter`, inspect/modify, then evaluate

```bash
uv run samples/05-end-to-end/evaluation/foundry_evals/evaluate_agent_sample.py
```

### `evaluate_traces_sample.py` — Trace & Response Evaluation (Path 1)

Evaluate what already happened — zero changes to agent code:

1. **`evaluate_traces(response_ids=...)`** — Evaluate Responses API responses by ID
2. **`evaluate_traces(agent_id=...)`** — Evaluate agent behavior from OTel traces in App Insights

```bash
uv run samples/05-end-to-end/evaluation/foundry_evals/evaluate_traces_sample.py
```

### `evaluate_with_generated_rubric_sample.py` — Auto-Generate a Rubric

Let Foundry draft the rubric dimensions for you from the agent's
context (instructions, tools, description).  Best when you don't yet
have a fixed scoring rubric and want a strong baseline you can refine.

```bash
uv run samples/05-end-to-end/evaluation/foundry_evals/evaluate_with_generated_rubric_sample.py
```

### `evaluate_with_manual_rubric_sample.py` — Author a Rubric Yourself

Bring your own `RubricDimension`s (from a spec, a competing framework,
or hand tuning) and register them as a versioned evaluator.  Use this
when you already know what you want to score.

```bash
uv run samples/05-end-to-end/evaluation/foundry_evals/evaluate_with_manual_rubric_sample.py
```

## Setup

Create a `.env` file with configuration as in the `.env.example` file in this folder.

## Which sample should I start with?

- **"I want to test my agent during development"** → `evaluate_agent_sample.py`, Pattern 1
- **"I want to evaluate past agent runs"** → `evaluate_traces_sample.py`
- **"I want to inspect/modify eval data before submitting"** → `evaluate_agent_sample.py`, Pattern 2
- **"I want Foundry to draft a custom rubric for my agent"** → `evaluate_with_generated_rubric_sample.py`
- **"I already have a rubric I want to bring into Foundry"** → `evaluate_with_manual_rubric_sample.py`
