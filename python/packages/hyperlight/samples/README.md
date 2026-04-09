# Hyperlight CodeAct samples

These samples demonstrate the alpha `agent-framework-hyperlight` package.

- `codeact_context_provider.py` shows the provider-owned CodeAct model where the
  agent only sees `execute_code` and sandbox tools are owned by
  `HyperlightCodeActProvider`.
- `codeact_tool.py` shows the standalone `HyperlightExecuteCodeTool` surface
  where `execute_code` is added directly to the agent tool list.

Run the samples from the repository after installing the workspace dependencies:

```bash
uv run --directory packages/hyperlight python samples/codeact_context_provider.py
uv run --directory packages/hyperlight python samples/codeact_tool.py
```
