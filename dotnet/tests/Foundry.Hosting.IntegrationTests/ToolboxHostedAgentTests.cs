// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Tests for the Foundry toolbox: the hosted container registers tools via the toolbox API
/// (server side), and tests can also add tools client side. The model should be able to
/// invoke tools from both sources.
/// </summary>
public sealed class ToolboxHostedAgentTests(ToolboxHostedAgentFixture fixture) : IClassFixture<ToolboxHostedAgentFixture>
{
    private readonly ToolboxHostedAgentFixture _fixture = fixture;

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task ServerRegisteredToolboxTool_IsCallableAsync()
    {
        // Arrange: the container side toolbox registers GetEnvironmentName which returns a constant.
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Call GetEnvironmentName via the toolbox and reply with just the value.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.Contains("integration-test", response.Text, System.StringComparison.OrdinalIgnoreCase);
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task ClientSideAddedToolboxTool_IsListedAndCallableAsync()
    {
        // TODO: requires AgentToolboxes API surface. Placeholder asserting the test runs.
        var agent = this._fixture.Agent;
        var response = await agent.RunAsync("List all tools you have access to.");
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task ListingTools_ReturnsBothServerAndClientSideEntriesAsync()
    {
        // TODO: requires AgentAdministrationClient toolbox listing. Placeholder.
        var agent = this._fixture.Agent;
        var response = await agent.RunAsync("Briefly describe what tools are available.");
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
    }
}
