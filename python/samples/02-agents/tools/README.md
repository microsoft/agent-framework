# Function Tool Samples

This folder contains Python samples that show how to expose functions as Agent
Framework tools, configure invocation behavior, and connect tools to external
systems.

| Sample | What it shows |
| --- | --- |
| [`agent_as_tool_with_session_propagation.py`](agent_as_tool_with_session_propagation.py) | Using an agent as a tool while preserving session context. |
| [`control_total_tool_executions.py`](control_total_tool_executions.py) | Limiting total tool executions during an agent run. |
| [`function_invocation_configuration.py`](function_invocation_configuration.py) | Configuring function invocation behavior. |
| [`function_tool_declaration_only.py`](function_tool_declaration_only.py) | Declaring a function tool schema without a local implementation. |
| [`function_tool_from_dict_with_dependency_injection.py`](function_tool_from_dict_with_dependency_injection.py) | Rehydrating a serialized function tool with dependency injection. |
| [`function_tool_recover_from_failures.py`](function_tool_recover_from_failures.py) | Letting an agent recover after a tool raises an exception. |
| [`function_tool_with_approval.py`](function_tool_with_approval.py) | Requesting approval before tool execution. |
| [`function_tool_with_approval_and_sessions.py`](function_tool_with_approval_and_sessions.py) | Combining approval requests with sessions. |
| [`function_tool_with_explicit_schema.py`](function_tool_with_explicit_schema.py) | Defining an explicit tool input schema. |
| [`function_tool_with_kwargs.py`](function_tool_with_kwargs.py) | Accepting flexible keyword arguments. |
| [`function_tool_with_max_exceptions.py`](function_tool_with_max_exceptions.py) | Capping repeated tool exceptions. |
| [`function_tool_with_max_invocations.py`](function_tool_with_max_invocations.py) | Capping repeated tool invocations. |
| [`function_tool_with_session_injection.py`](function_tool_with_session_injection.py) | Reading the active agent session inside a tool. |
| [`local_code_interpreter/`](local_code_interpreter/) | Running code through the Hyperlight local code interpreter tool. |
| [`tool_in_class.py`](tool_in_class.py) | Defining tools as methods on a class. |
| [`xquik_function_tools.py`](xquik_function_tools.py) | Calling API-key backed Xquik read endpoints from async function tools. |

## Xquik Sample

`xquik_function_tools.py` demonstrates read-only external API tools for public
X/Twitter research:

- `search_x_posts` calls `GET /x/tweets/search`.
- `get_x_user` calls `GET /x/users/{id}`.
- `get_x_user_posts` calls `GET /x/users/{id}/tweets`.
- `get_x_trends` calls `GET /x/trends`.

Set these environment variables for live API calls:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
export FOUNDRY_MODEL="gpt-4o"
export XQUIK_API_KEY="your-xquik-api-key"
```

`XQUIK_API_KEY` is optional for sample validation. Without it, the tools return
local sample data and the agent still demonstrates the function-tool flow.
