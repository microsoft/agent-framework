// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=tool-calling-approval</c> mode.
/// The container declares an AIFunction tagged <c>RequiresApproval=true</c> so tests can exercise
/// the human in the loop approval flow (request, grant, deny).
/// </summary>
public sealed class ToolCallingApprovalHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "tool-calling-approval";
}
