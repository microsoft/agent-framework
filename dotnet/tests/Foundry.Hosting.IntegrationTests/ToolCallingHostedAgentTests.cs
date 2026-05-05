// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Extensions.AI;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Tests that exercise server side tool invocation by a hosted agent. The container
/// declares deterministic AIFunctions (e.g. <c>GetUtcNow</c>, <c>Multiply</c>) and the
/// model decides whether to call them based on the prompt.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class ToolCallingHostedAgentTests(ToolCallingHostedAgentFixture fixture) : IClassFixture<ToolCallingHostedAgentFixture>
{
    private readonly ToolCallingHostedAgentFixture _fixture = fixture;

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task ServerSideTool_IsInvokedWhenPromptedAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("What is the current UTC date and time? Use the GetUtcNow tool.");

        // Assert: response references a timestamp (very loose check; deterministic-ish).
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.True(response.Messages.Any(m => m.Contents.OfType<FunctionCallContent>().Any()),
            "Expected at least one FunctionCallContent in the response messages.");
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task ServerSideTool_NotInvokedWhenNotNeededAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Say hello in one word.");

        // Assert: no tool call expected for a simple greeting.
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        var toolCallCount = response.Messages.SelectMany(m => m.Contents.OfType<FunctionCallContent>()).Count();
        Assert.Equal(0, toolCallCount);
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task ServerSideTool_MultiTurn_RemembersPriorToolResultAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;
        var session = await agent.CreateSessionAsync();

        // Act
        var first = await agent.RunAsync("Multiply 6 by 7 using the Multiply tool. Reply with the result.", session);
        Assert.Contains("42", first.Text);

        var second = await agent.RunAsync("What was the result of the last multiplication?", session);

        // Assert
        Assert.Contains("42", second.Text);
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task ServerSideTool_WithArguments_ReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync("Use the Multiply tool with a=12 and b=11. Reply with just the numeric result.");

        // Assert
        Assert.Contains("132", response.Text);
    }
}
