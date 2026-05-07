// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Extensions.AI;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Tests for an MCP backed toolbox: the hosted container connects to a public MCP server
/// (the Microsoft Learn MCP endpoint) at startup and exposes its tools to the model.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class McpToolboxHostedAgentTests(McpToolboxHostedAgentFixture fixture)
    : IClassFixture<McpToolboxHostedAgentFixture>
{
    private readonly McpToolboxHostedAgentFixture _fixture = fixture;

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task McpTool_IsInvokedSuccessfullyAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Use the Microsoft Learn MCP tool to look up 'Azure AI Foundry'. Reply with one short paragraph.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.True(response.Messages.Any(m => m.Contents.OfType<FunctionCallContent>().Any()),
            "Expected at least one MCP tool invocation in the response messages.");
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task McpTool_WithStructuredArguments_ReturnsValidResultAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Use the MCP search tool with the query 'agent framework hosted agents'. Reply with at least one fact.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task McpTool_ProducesUsableResponseAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Tell me one thing about Microsoft Foundry that would only be in MS Learn docs.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
    }
}
