// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=mcp-toolbox</c> mode.
/// The container connects to a public MCP server (the Microsoft Learn MCP endpoint) so tests
/// can verify MCP tool discovery and invocation flowing through the Foundry hosted agent.
/// </summary>
public sealed class McpToolboxHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "mcp-toolbox";
}
