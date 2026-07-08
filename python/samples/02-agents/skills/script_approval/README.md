# Skill Tool Approval — Human-in-the-Loop for Skill Tools

This sample demonstrates the **manual human-in-the-loop** approval pattern for
skill tools. Every tool exposed by `SkillsProvider` (`load_skill`,
`read_skill_resource`, and `run_skill_script`) requires host approval by
default, so the agent pauses and returns approval requests that your
application approves or rejects.

## How It Works

By default, skill tools require approval. The agent pauses before running any of
them and returns approval requests instead:

1. The agent tries to call a skill tool (e.g. `load_skill` or `run_skill_script`) — execution is paused
2. `result.user_input_requests` contains approval request(s) with function name and arguments
3. The application inspects each request and decides to approve or reject
4. `request.to_function_approval_response(approved=True|False)` creates the response
5. The response is sent back via `agent.run(approval_response, session=session)`
6. If approved, the tool runs; if rejected, the agent receives an error

## Key Components

- **Approval-by-default** — All skill tools require host approval; no extra configuration is needed
- **`result.user_input_requests`** — Contains pending approval requests after `agent.run()`
- **`request.to_function_approval_response()`** — Creates an approval or rejection response

To approve skill tools automatically instead of prompting for each one, use
`ToolApprovalMiddleware` with one of the static auto-approval rules — see the
[Skills Auto-Approval Sample](../skills_auto_approval/).

## Running the Sample

### Prerequisites
- An [Azure AI Foundry](https://ai.azure.com/) project with a deployed model (e.g. `gpt-4o-mini`)

### Environment Variables

Set the required environment variables in a `.env` file (see `python/.env.example`):

- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL`: The name of your model deployment (defaults to `gpt-4o-mini`)

### Authentication

This sample uses `AzureCliCredential` for authentication. Run `az login` in your terminal before running the sample.

### Run

```bash
cd python
uv run samples/02-agents/skills/script_approval/script_approval.py
```

## Learn More

- [Skills Auto-Approval Sample](../skills_auto_approval/)
- [File-Based Skills Sample](../file_based_skill/)
- [Code-Defined Skills Sample](../code_defined_skill/)
- [Mixed Skills Sample](../mixed_skills/)
- [Agent Skills Specification](https://agentskills.io/)
