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
/// Tests that inference-hosted MCP execution is preserved as a caller-facing MCP contract.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class HostedMcpHostedAgentTests(HostedMcpHostedAgentFixture fixture)
    : IClassFixture<HostedMcpHostedAgentFixture>
{
    private readonly HostedMcpHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task InferenceHostedMcpExecution_UsesMcpCallerContractAsync()
    {
        // Arrange
        ResponsesClient responses = this._fixture.AgentOpenAIClient.GetProjectResponsesClient();
        CreateResponseOptions options = ProjectResponsesTestOptions.Create();
        options.StoredOutputEnabled = false;
        options.InputItems.Add(ResponseItem.CreateUserMessageItem(
            "Use microsoft_docs_search to find the Microsoft Learn page about Agent Framework hosted agents. " +
            "Reply with one short fact."));
        using CancellationTokenSource timeout = new(TimeSpan.FromMinutes(3));

        // Act
        ResponseResult response = (await responses.CreateResponseAsync(options, timeout.Token)).Value;

        // Assert
        Assert.Equal(ResponseStatus.Completed, response.Status);
        McpToolCallItem mcpCall = Assert.Single(response.OutputItems.OfType<McpToolCallItem>());
        Assert.Equal("microsoft_learn_hosted", mcpCall.ServerLabel);
        Assert.Equal("microsoft_docs_search", mcpCall.ToolName);
        Assert.False(string.IsNullOrWhiteSpace(mcpCall.ToolOutput));
        Assert.DoesNotContain(response.OutputItems, item =>
            item is FunctionCallResponseItem or FunctionCallOutputResponseItem);
        Assert.False(string.IsNullOrWhiteSpace(response.GetOutputText()));
    }
}
