## Summary

Issue #4861 is **reproduced**. The `AzureOpenAIChatClient._prepare_tools_for_openai()` method passes MCP tool dicts (with `"type": "mcp"`) through unchanged to the Chat Completions API, which only accepts `"function"` and `"custom"` tool types, resulting in a 400 error.

## Reproduction Attempt

Two tests were written and both pass, confirming the bug:

1. **`test_mcp_tool_dict_is_passed_through_unchanged`**: Calls `_prepare_tools_for_openai()` with the exact MCP tool dict from the sample. Confirms the tool is included in the output with `type="mcp"` — an unsupported type for the Chat Completions API.

2. **`test_mcp_tool_causes_api_rejection`**: Mocks the API call and verifies that when MCP tools are provided through `_inner_get_response`, the `type="mcp"` dict reaches the API call unchanged, which would cause the 400 error described in the issue.

Test output:
```
packages/core/tests/openai/test_issue_4861_mcp_tool_chat_client.py ..    [100%]
2 passed in 3.74s
```

## Affected Code

- **`python/packages/core/agent_framework/openai/_chat_client.py`** lines 357-364: `_prepare_tools_for_openai()` has a `MutableMapping` branch that passes through all dict-based tools unchanged (line 364: `chat_tools.append(typed_tool)`). Only `"web_search"` type gets special handling. MCP tools (`"type": "mcp"`) fall through to the generic pass-through.

- **`python/samples/05-end-to-end/hosted_agents/agent_with_hosted_mcp/main.py`**: The sample uses `AzureOpenAIChatClient` with `{"type": "mcp", ...}` dict, but should use `AzureOpenAIResponsesClient` which natively supports MCP tools via its `get_mcp_tool()` helper.

## Verdict

**Reproduced** — High confidence.

The bug is clearly present in the current codebase. The `_prepare_tools_for_openai` method passes MCP tool dicts through to the Chat Completions API, which rejects `"type": "mcp"`. The fix should change the sample to use `AzureOpenAIResponsesClient` instead, as the Chat Completions API fundamentally does not support MCP tools.
