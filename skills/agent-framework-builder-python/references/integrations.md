# Providers and integrations

Choose integrations only after the application contract is clear. Provider and connector capabilities, package
maturity, and Python compatibility change more frequently than core Agent Framework patterns.

## Version and package selection

- Check each selected distribution's `Requires-Python` metadata and the current
  [Python package status](https://github.com/microsoft/agent-framework/blob/main/python/PACKAGE_STATUS.md).
- Read the [Python README compatibility notes](https://github.com/microsoft/agent-framework/blob/main/python/README.md)
  for current boundary-version limitations rather than copying that matrix into application guidance.
- Install only the selected integrations and allow prerelease packages only when required.

## Provider selection

Start with the current
[model provider catalog](https://learn.microsoft.com/agent-framework/integrations/by-component/model-providers/) and
[agent service catalog](https://learn.microsoft.com/agent-framework/integrations/by-component/agent-services/).

Verify authentication, streaming, structured output, hosted tools, history ownership, approval, and function-loop
support instead of assuming provider parity. If no provider matches, use
[Extensibility](extensibility.md#custom-providers).

## Connection and credential ownership

Use `async with client` for standalone chat clients, or `async with Agent(client=client, ...)` to have the agent
enter and exit the client's context. Direct requests without a context remain supported; call
`await client.close()` when finished. Connectors release their own connections, not caller-injected SDK clients,
HTTP transports, or credentials. Scope supplied credentials outside the clients and agents that use them.
For Foundry, the derived OpenAI connection is owned by the connector even when the project client is supplied.
Do not share a connector-owned connection across overlapping agent contexts; inject an externally managed SDK
client when its lifetime must extend beyond any one agent context. Do not assume a closed SDK connection can reopen.

## Capability categories

- Use function tools for application-owned code and MCP for external tool services.
- Use sessions and ContextProviders first; add memory, retrieval, or vector-store connectors when persistence, search,
  scale, or an external data model requires them.
- A2A connects agents across services; AG-UI connects agents or workflows to compatible frontends; hosting adapters
  expose protocols. None of these replace application authorization.
- Durable Task and Azure Functions integrations are maintained in the
  [Durable Agent Framework extension](https://github.com/microsoft/agent-framework-durable-extension).

For AG-UI, remember that thread and run IDs are correlation identifiers, not authentication boundaries. The
application owns authorization, durable snapshots, scaling, and rendering policy.

## Code execution

For Monty, distinguish interpreter `resource_limits` from host-side attachment capture. Capture has per-call
file-count and raw-byte limits shared across read-write mounts. Omitted attachments do not undo filesystem writes.
Check the [Monty file-mount and resource-limit guidance](https://github.com/microsoft/agent-framework/blob/main/python/packages/monty/README.md#file-mounts-and-resource-limits)
before relying on output attachments or treating interpreter limits as host resource limits.

## Selection checklist

Confirm the provider/service, authentication model, required capabilities, package maturity, Python range, data and
tenant boundaries, approval policy, and required permissions. Add a focused integration test or opt-in live smoke test.

## Learn more

- [Agent Framework integrations](https://learn.microsoft.com/agent-framework/integrations/)
- [Python package status](https://github.com/microsoft/agent-framework/blob/main/python/PACKAGE_STATUS.md)
- [Python samples](https://github.com/microsoft/agent-framework/tree/main/python/samples)
- [AG-UI sample](https://github.com/microsoft/agent-framework/tree/main/python/samples/05-end-to-end/ag_ui_single_agent)
