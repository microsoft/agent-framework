# Agent Framework CodeAct (Hyperlight) Samples

These samples show how to enable an agent to write and execute code in a
Hyperlight-backed sandbox via the CodeAct pattern. Guest code can be pure
Python (interpreter mode) or orchestrate host-provided tools through
`call_tool(...)` — all inside a secure sandbox with opt-in filesystem and
network access.

|Sample|Description|
|---|---|
|[Code interpreter](./AgentWithCodeAct_Step01_Interpreter/)|Uses `HyperlightCodeActProvider` as a sandboxed Python interpreter with no host tools.|
|[Tool-enabled CodeAct](./AgentWithCodeAct_Step02_ToolEnabled/)|Registers provider-owned tools that guest code can orchestrate via `call_tool(...)`, with an approval-required tool for sensitive actions.|
|[Manual wiring](./AgentWithCodeAct_Step03_ManualWiring/)|Uses `HyperlightExecuteCodeFunction` directly as an agent tool when the sandbox configuration is fixed.|

All samples require a Hyperlight Python guest module. Set
`HYPERLIGHT_PYTHON_GUEST_PATH` to its absolute path before running.
