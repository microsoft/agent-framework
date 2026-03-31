# Script Approval — Human-in-the-Loop for Skill Scripts

This sample demonstrates how to require **human approval** before executing skill scripts using the `require_script_approval=True` option on `SkillsProvider`.

## How It Works

When `require_script_approval=True` is set, the agent pauses before executing any skill script and returns approval requests instead:

1. The agent tries to call `run_skill_script` — execution is paused
2. `result.user_input_requests` contains approval request(s) with function name and arguments
3. The application inspects each request and decides to approve or reject
4. `request.to_function_approval_response(approved=True|False)` creates the response
5. The response is sent back via `agent.run(approval_response, session=session)`
6. If approved, the script executes; if rejected, the agent receives an error

## Key Components

- **`require_script_approval=True`** — Gates all script execution on human approval
- **`result.user_input_requests`** — Contains pending approval requests after `agent.run()`
- **`request.to_function_approval_response()`** — Creates an approval or rejection response

## Running the Sample

### Prerequisites
- An [Azure AI Foundry](https://ai.azure.com/) project with a deployed model (e.g. `gpt-4o-mini`)

### Environment Variables

Set the required environment variables in a `.env` file (see `python/.env.example`):

- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `AZURE_OPENAI_DEPLOYMENT_NAME`: The name of your model deployment (defaults to `gpt-4o-mini`)

### Authentication

This sample uses `AzureCliCredential` for authentication. Run `az login` in your terminal before running the sample.

### Run

```bash
cd python
uv run samples/02-agents/skills/script_approval/script_approval.py
```

## Learn More

- [File-Based Skills Sample](../file_based_skill/)
- [Code-Defined Skills Sample](../code_defined_skill/)
- [Mixed Skills Sample](../mixed_skills/)
- [Agent Skills Specification](https://agentskills.io/)
