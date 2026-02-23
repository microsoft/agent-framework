# Foundry Local Examples

This folder contains examples demonstrating how to run local models with `FoundryLocalClient` via `agent_framework.microsoft`.

## Prerequisites

1. Install Foundry Local and required local runtime components.
2. Install the connector package:

   ```bash
   pip install agent-framework-foundry-local --pre
   ```

## Examples

| File | Description |
|------|-------------|
| [`foundry_local_agent.py`](foundry_local_agent.py) | Basic Foundry Local agent usage with streaming and non-streaming responses, plus function tool calling. |

## Environment Variables

- `FOUNDRY_LOCAL_MODEL_ID`: Optional model alias/ID to use by default when `model_id` is not passed to `FoundryLocalClient`.
