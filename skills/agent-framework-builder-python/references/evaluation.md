# Evaluation

Use evaluation to turn expected behavior, failures, and user feedback into repeatable checks.

The local evaluation APIs and Foundry evaluation APIs are currently experimental. Keep their use isolated and review
feature maturity before exposing them as a long-term application contract.

## Capture a useful regression case

Record:

- input prompt or triggering event;
- current and expected output;
- expected tool calls and important arguments;
- relevant conversation, session, or workflow state;
- provider and model configuration;
- agent or workflow version;
- user feedback and the behavior it implies.

Translate feedback into an expected output, expected tool call, context fixture, or custom evaluator instead of
inventing an unsupported framework field.

## Diagnose before changing

Classify the failure:

1. deterministic code, schema, or tool bug;
2. wrong tool selection or approval behavior;
3. missing context, retrieval, memory, or history;
4. ambiguous instructions or output contract;
5. workflow routing, state, checkpoint, or output selection;
6. provider or client configuration;
7. hosting or runtime environment;
8. model limitation after application-layer causes are excluded.

Change the lowest layer that caused the failure.

## Local evaluation

```python
from agent_framework import LocalEvaluator, evaluate_agent, keyword_check, tool_called_check


evaluator = LocalEvaluator(
    keyword_check("weather"),
    tool_called_check("get_weather"),
)

results = await evaluate_agent(
    agent=agent,
    queries=["What is the weather in Amsterdam?"],
    expected_output=["A concise weather answer."],
    evaluators=evaluator,
)
```

Useful APIs include:

- `EvalItem`, `EvalResults`, `Evaluator`, and `LocalEvaluator`;
- `@evaluator` for custom checks;
- `ExpectedToolCall`;
- `evaluate_agent(...)` and `evaluate_workflow(...)`;
- `keyword_check`, `tool_called_check`, `tool_calls_present`, and tool-argument checks.

Use exact string comparison only when exact wording is part of the contract. Prefer deterministic checks for tools,
schemas, required facts, and output structure before adding model-based graders.

See [agent evaluation](https://learn.microsoft.com/agent-framework/agents/evaluation).

## Foundry evaluation

Use `FoundryEvals`, `evaluate_foundry_target`, or `evaluate_traces` when cloud evaluators, dashboards, or trace-derived
evaluation are required. These APIs are experimental.

Keep local deterministic checks for fast inner-loop and CI coverage. Treat prompt optimization and continuous
monitoring as platform workflows rather than implicit Agent Framework behavior.

## Improvement loop

1. Reproduce the failure.
2. Add or update a regression case.
3. Fix the responsible layer.
4. Run deterministic checks.
5. Run model-based or Foundry evaluators only where they add signal.
6. Compare results.
7. Keep the case after the fix.

Current examples:

- [Local agent evaluation](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/evaluation/evaluate_agent.py)
- [Expected outputs and tool calls](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/evaluation/evaluate_with_expected.py)
- [Workflow evaluation](https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/evaluation/evaluate_workflow.py)
