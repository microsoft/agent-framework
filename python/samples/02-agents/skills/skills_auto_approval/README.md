# Skills Auto-Approval — Configure Auto-Approval Rules for Skill Tools

This sample demonstrates how to configure **auto-approval rules** for skill
tools using `ToolApprovalMiddleware`. Every tool exposed by `SkillsProvider`
(`load_skill`, `read_skill_resource`, and `run_skill_script`) requires host
approval by default. Auto-approval rules let you selectively bypass the approval
prompt for safe operations.

## How It Works

1. A code-defined unit-converter skill (with a resource and a script) is registered via `SkillsProvider`.
2. The agent installs `ToolApprovalMiddleware` with `SkillsProvider.read_only_tools_auto_approval_rule`.
3. The read-only tools (`load_skill`, `read_skill_resource`) are approved automatically.
4. `run_skill_script` still requires explicit approval and is handled with the standard `result.user_input_requests` loop.

## Auto-Approval Rules

`SkillsProvider` exposes two static rules to pass to `ToolApprovalMiddleware(auto_approval_rules=[...])`:

- **`SkillsProvider.read_only_tools_auto_approval_rule`** — approves only the read-only tools (`load_skill`, `read_skill_resource`), while still prompting for `run_skill_script`.
- **`SkillsProvider.all_tools_auto_approval_rule`** — approves every skill tool, including `run_skill_script` (no manual approval loop needed).

Both rules reject any call carrying a `server_label`, so they stay scoped to this provider's local tools and never auto-approve a same-named hosted tool.

> **Note:** To use auto-approval rules, the agent must have `ToolApprovalMiddleware` in its middleware stack.

## Key Components

- **`ToolApprovalMiddleware(auto_approval_rules=[...])`** — Drives the approval handshake and applies the rules
- **`SkillsProvider.read_only_tools_auto_approval_rule`** — Auto-approves read-only skill tools
- **`SkillsProvider.all_tools_auto_approval_rule`** — Auto-approves all skill tools
- **`SkillsProvider.LOAD_SKILL_TOOL_NAME` / `READ_SKILL_RESOURCE_TOOL_NAME` / `RUN_SKILL_SCRIPT_TOOL_NAME`** — Tool-name constants for building custom rules

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
uv run samples/02-agents/skills/skills_auto_approval/skills_auto_approval.py
```

## Learn More

- [Skill Tool Approval Sample](../script_approval/) — manual human-in-the-loop approval
- [Code-Defined Skills Sample](../code_defined_skill/)
- [File-Based Skills Sample](../file_based_skill/)
- [Agent Skills Specification](https://agentskills.io/)
