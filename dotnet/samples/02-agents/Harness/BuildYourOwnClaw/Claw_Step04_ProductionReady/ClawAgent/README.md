# ClawAgent

Shared class library for the production-ready personal finance claw.

`ClawAgentFactory.CreateAsync(...)` returns a `ClawAgentBuild` containing the fully configured `AIAgent` plus disposable resources. It preserves the Step 03 capabilities: Foundry Responses `IChatClient`, local file skills, optional Foundry Toolbox MCP skills, background research agent, confined `LocalShellExecutor`, Hyperlight CodeAct, file access, approvals, agent modes, stock tools, and trading tools.

Purview is opt-in via `PURVIEW_CLIENT_APP_ID`; when unset, the chat client is not wrapped. Telemetry is always enabled through `HarnessAgentOptions.OpenTelemetrySourceName`.
