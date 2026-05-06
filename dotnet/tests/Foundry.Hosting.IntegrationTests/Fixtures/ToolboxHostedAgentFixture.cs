// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=toolbox</c> mode.
/// The container hosts a Foundry toolbox with at least one server registered tool. Tests verify
/// that the model can invoke those tools and that client side toolbox additions surface alongside
/// server side registrations when listed.
/// </summary>
public sealed class ToolboxHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "toolbox";
}
