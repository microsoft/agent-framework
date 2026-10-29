# Evaluation

Use evaluation to turn expected behavior, failures, and feedback into repeatable evidence. Evaluation determines whether
behavior is acceptable; observability explains what happened during execution.

Evaluation APIs are experimental. Check current feature maturity and API docstrings before making them a long-term
application contract.

## Capture the case

Record the input, current and expected output, expected tool calls, relevant session or workflow state, provider/model,
application version, and actionable user feedback. Express feedback as expected behavior or a custom evaluator instead
of inventing unsupported fields.

## Diagnose before changing

Classify the failure before modifying prompts or models:

1. deterministic code, schema, or tool behavior;
2. tool selection or approval;
3. missing context, retrieval, memory, or history;
4. instructions or output contract;
5. workflow routing, state, checkpoint, or output selection;
6. provider, hosting, or environment configuration;
7. model limitation after application causes are excluded.

Fix the lowest responsible layer. Prefer deterministic checks for tools, schemas, required facts, and output structure;
use model-based or Foundry evaluators only where they add signal.

## Improvement loop

Reproduce the failure, add a regression case, fix the responsible layer, run deterministic checks, add model-based
evaluation if needed, compare results, and retain the case.

## Learn more

- [Agent evaluation](https://learn.microsoft.com/agent-framework/agents/evaluation)
- [Local evaluation samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/evaluation)
- [Workflow evaluation sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/evaluation/evaluate_workflow.py)
- [Foundry evaluation samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/05-end-to-end/evaluation)
