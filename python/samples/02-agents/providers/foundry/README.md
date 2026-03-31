# Foundry Provider Samples

This folder contains Azure AI Foundry and Foundry Local samples for Agent Framework.

## FoundryAgent Samples

| File | Description |
|------|-------------|
| [`foundry_agent_basic.py`](foundry_agent_basic.py) | Foundry Agent basic example |
| [`foundry_agent_custom_client.py`](foundry_agent_custom_client.py) | Foundry Agent custom client configuration |
| [`foundry_agent_hosted.py`](foundry_agent_hosted.py) | Foundry Agent for hosted agents |
| [`foundry_agent_with_env_vars.py`](foundry_agent_with_env_vars.py) | Foundry Agent using environment variables |
| [`foundry_agent_with_function_tools.py`](foundry_agent_with_function_tools.py) | Foundry Agent with local function tools |

## FoundryChatClient Samples

| File | Description |
|------|-------------|
| [`foundry_chat_client.py`](foundry_chat_client.py) | Foundry Chat Client with project endpoint example |
| [`foundry_chat_client_basic.py`](foundry_chat_client_basic.py) | Foundry Chat Client basic example |
| [`foundry_chat_client_code_interpreter_files.py`](foundry_chat_client_code_interpreter_files.py) | Foundry Chat Client with code interpreter and files |
| [`foundry_chat_client_image_analysis.py`](foundry_chat_client_image_analysis.py) | Foundry Chat Client with image analysis |
| [`foundry_chat_client_with_code_interpreter.py`](foundry_chat_client_with_code_interpreter.py) | Foundry Chat Client with code interpreter |
| [`foundry_chat_client_with_explicit_settings.py`](foundry_chat_client_with_explicit_settings.py) | Foundry Chat Client with explicit settings |
| [`foundry_chat_client_with_file_search.py`](foundry_chat_client_with_file_search.py) | Foundry Chat Client with file search |
| [`foundry_chat_client_with_function_tools.py`](foundry_chat_client_with_function_tools.py) | Foundry Chat Client with function tools |
| [`foundry_chat_client_with_hosted_mcp.py`](foundry_chat_client_with_hosted_mcp.py) | Foundry Chat Client with hosted MCP |
| [`foundry_chat_client_with_local_mcp.py`](foundry_chat_client_with_local_mcp.py) | Foundry Chat Client with local MCP |
| [`foundry_chat_client_with_session.py`](foundry_chat_client_with_session.py) | Foundry Chat Client with session management |

## FoundryLocalClient Samples

### Prerequisites

1. Install Foundry Local and required local runtime components.
2. Install the connector package:

   ```bash
   pip install agent-framework-foundry-local --pre
   ```

| File | Description |
|------|-------------|
| [`foundry_local_agent.py`](foundry_local_agent.py) | Basic Foundry Local agent usage with streaming and non-streaming responses, plus function tool calling. |

### Environment Variables

- `FOUNDRY_LOCAL_MODEL_ID`: Optional model alias/ID to use by default when `model_id` is not passed to `FoundryLocalClient`.
