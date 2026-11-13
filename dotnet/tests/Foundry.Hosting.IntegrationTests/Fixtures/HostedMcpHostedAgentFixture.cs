// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=mcp-hosted</c> mode.
/// The inference provider executes the public Microsoft Learn MCP tool so the test can verify the
/// caller-facing native MCP contract independently from locally executed functions.
/// </summary>
public sealed class HostedMcpHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "mcp-hosted";
}
