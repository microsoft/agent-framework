# Providers and integrations

Choose integrations only after the application contract is clear. Provider and connector capabilities, package
maturity, and framework compatibility change more frequently than core Agent Framework patterns.

## Version and package selection

- Check each selected package's current version suffix (released, `-preview`, or `-alpha`) and its supported target
  frameworks before adding it. Packages with different maturity can be combined, but prerelease packages may have
  breaking changes between versions.
- Keep all `Microsoft.Agents.AI.*` packages and the underlying `Microsoft.Extensions.AI` packages on compatible
  versions; mismatches typically show up as missing-method or binding errors.
- Add only the selected integrations and allow prerelease packages only when required.

## Provider selection

Start with the current
[model provider catalog](https://learn.microsoft.com/agent-framework/integrations/by-component/model-providers/) and
[agent service catalog](https://learn.microsoft.com/agent-framework/integrations/by-component/agent-services/).

Verify authentication, streaming, structured output, hosted tools, history ownership, approval, and function-loop
support instead of assuming provider parity. If the backend exposes an `IChatClient`, wrap it with `ChatClientAgent`;
otherwise see [Extensibility](extensibility.md#custom-providers).

## Capability categories

- Use `AIFunction` tools for application-owned code and MCP (`Microsoft.Agents.AI.Mcp`, or MCP tools from the
  official MCP C# SDK) for external tool services.
- Use sessions and context providers first; add memory, retrieval, or vector-store connectors when persistence,
  search, scale, or an external data model requires them. Examples include `Microsoft.Agents.AI.CosmosNoSql`,
  `Microsoft.Agents.AI.Valkey`, `Microsoft.Agents.AI.Mem0`, and the vector-store-backed `TextSearchProvider` and
  `ChatHistoryMemoryProvider`.
- Remote agents and agent services: `Microsoft.Agents.AI.A2A`, `Microsoft.Agents.AI.CopilotStudio`,
  `Microsoft.Agents.AI.GitHub.Copilot`, and `Microsoft.Agents.AI.AzureAI.Persistent`.
- Governance and policy: `Microsoft.Agents.AI.Purview`.
- Code execution: `Microsoft.Agents.AI.LocalCodeAct`, `Microsoft.Agents.AI.Hyperlight`, and
  `Microsoft.Agents.AI.Tools.Shell`; treat all of them as security-sensitive and sandbox accordingly.
- A2A connects agents across services; AG-UI connects agents or workflows to compatible frontends; hosting adapters
  expose protocols. None of these replace application authorization.
- Durable agents and workflows run on Azure Functions and Durable Task; see
  [Hosting and deployment](hosting-and-deployment.md).

LocalCodeAct and Hyperlight redact host tool exception diagnostics by default. Enable
`IncludeDetailedErrors` on their provider options only for a trusted channel; full exceptions include
stack traces and inner exceptions. This is separate from the
outer `FunctionInvokingChatClient` error policy and sensitive-data logging; outer redaction cannot repair
diagnostics already caught and returned by generated code.

Hyperlight guest execution defaults to a finite 30-second limit, configurable through
`HyperlightCodeActProviderOptions.ExecutionTimeoutSeconds`. Caller cancellation interrupts
guest code, but neither cancellation nor the limit interrupts runtime initialization
or host tool callbacks. Host tools must enforce their own limits. This requires the
upstream SDK's cancellation-aware `Run` API; verify that it is available in the selected
package version before using this option.

For AG-UI, remember that thread and run IDs are correlation identifiers, not authentication boundaries. The
application owns authorization, durable snapshots, scaling, and rendering policy.

For Purview, all prompt content uses the `UploadText` activity and all response content uses `DownloadText`,
including binary content. The middleware cannot reliably distinguish file attachments from inline binary
content. Configure DLP policies for these text activities; `UploadFile`-only or `DownloadFile`-only rules do
not block binary content through this integration.

## Selection checklist

Confirm the provider/service, authentication model (prefer token credentials), required capabilities, package
maturity, target-framework support, data and tenant boundaries, approval policy, and required permissions. Add a
focused integration test or opt-in live smoke test.

## Learn more

- [Agent Framework integrations](https://learn.microsoft.com/agent-framework/integrations/)
- [.NET samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples)
- [Provider samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/AgentProviders)
- [MCP samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/ModelContextProtocol)
- [AG-UI samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/AGUI)
- [A2A samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/A2A)
