// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Experimental Responses API surfaces

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Tests that a container-local Foundry Toolbox execution uses the caller-facing MCP contract.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class McpToolboxHostedAgentTests(McpToolboxHostedAgentFixture fixture)
    : IClassFixture<McpToolboxHostedAgentFixture>
{
    private readonly McpToolboxHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task ToolboxExecution_UsesMcpCallerContractAsync()
    {
        // Arrange
        ResponsesClient responses = this._fixture.AgentOpenAIClient.GetProjectResponsesClient();
        CreateResponseOptions options = ProjectResponsesTestOptions.Create();
        options.StoredOutputEnabled = false;
        options.InputItems.Add(ResponseItem.CreateUserMessageItem(
            "Call the GitHub get_me tool from the toolbox and report only the returned login."));
        using CancellationTokenSource timeout = new(TimeSpan.FromMinutes(3));

        // Act
        ResponseResult response = (await responses.CreateResponseAsync(options, timeout.Token)).Value;

        // Assert
        Assert.Equal(ResponseStatus.Completed, response.Status);
        McpToolCallItem mcpCall = Assert.Single(response.OutputItems.OfType<McpToolCallItem>());
        Assert.Equal(this._fixture.ToolboxName, mcpCall.ServerLabel);
        Assert.EndsWith("___get_me", mcpCall.ToolName, StringComparison.Ordinal);
        Assert.False(string.IsNullOrWhiteSpace(mcpCall.ToolOutput));
        Assert.Contains("rogerbarreto", mcpCall.ToolOutput, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(response.OutputItems, item =>
            item is FunctionCallResponseItem or FunctionCallOutputResponseItem);
        Assert.Contains("rogerbarreto", response.GetOutputText(), StringComparison.OrdinalIgnoreCase);
    }

}
