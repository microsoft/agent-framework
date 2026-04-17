# Hyperlight CodeAct samples

These samples demonstrate the alpha `agent-framework-hyperlight` package.

## When to use which pattern

- **Provider pattern** (`codeact_context_provider.py`): Use when the tool
  registry, file mounts, or network allow-list may change between runs, or when
  you want the provider to manage CodeAct instructions and approval computation
  automatically on every invocation. This is the recommended default for
  production agents that need dynamic capability management or concurrent runs
  sharing one provider.

- **Manual static wiring** (`codeact_manual_wiring.py`): Use when the sandbox
  tool set and capabilities are fixed for the agent's lifetime. This pattern
  builds instructions once, passes `execute_code` alongside direct tools in
  `tools=`, and skips the per-run provider lifecycle entirely. Simpler setup,
  but changes to the tool registry after construction will not update the
  agent's instructions automatically.

- **Standalone tool** (`codeact_tool.py`): Use for the simplest integration
  where `execute_code` is added directly to the agent tool list. The tool's own
  description advertises `call_tool(...)` and the registered sandbox tools, so
  no extra agent instructions are needed. Best for quick prototyping or when
  CodeAct is just another tool alongside the agent's direct tools.

## Samples

- `codeact_context_provider.py` shows the provider-owned CodeAct model where the
  agent only sees `execute_code` and sandbox tools are owned by
  `HyperlightCodeActProvider`.
- `codeact_manual_wiring.py` shows static wiring where `HyperlightExecuteCodeTool`
  and its instructions are passed directly to the `Agent` constructor.
- `codeact_tool.py` shows the standalone `HyperlightExecuteCodeTool` surface
  where `execute_code` is added directly to the agent tool list.

Run the samples from the repository after installing the workspace dependencies:

```bash
uv run --directory packages/hyperlight python samples/codeact_context_provider.py
uv run --directory packages/hyperlight python samples/codeact_manual_wiring.py
uv run --directory packages/hyperlight python samples/codeact_tool.py
```
