// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=tool-calling</c> mode.
/// The container declares one or more deterministic AIFunctions on the server side
/// (e.g. <c>GetUtcNow</c>, <c>Multiply(int,int)</c>) so tests can verify tool invocation behavior
/// without requiring approvals.
/// </summary>
public sealed class ToolCallingHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "tool-calling";
}
