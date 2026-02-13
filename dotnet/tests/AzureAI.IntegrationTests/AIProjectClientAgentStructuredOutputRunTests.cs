// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace AzureAI.IntegrationTests;

public class AIProjectClientAgentStructuredOutputRunTests() : StructuredOutputRunTests<AIProjectClientStructuredOutputFixture<CityInfo>>(() => new AIProjectClientStructuredOutputFixture<CityInfo>())
{
    private const string NotSupported = "AIProjectClient does not support specifying structured output type at invocation time.";

    /// <summary>
    /// Verifies that response format provided at agent initialization is used when invoking RunAsync.
    /// </summary>
    /// <returns></returns>
    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public async Task RunWithResponseFormatAtAgentInitializationReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var session = await agent.CreateSessionAsync();
        await using var cleanup = new SessionCleanup(session, this.Fixture);

        // Act
        var response = await agent.RunAsync(new ChatMessage(ChatRole.User, "Provide information about the capital of France."), session);

        // Assert
        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
        Assert.True(TryDeserialize(response.Text, AgentAbstractionsJsonUtilities.DefaultOptions, out CityInfo cityInfo));
        Assert.Equal("Paris", cityInfo.Name);
    }

    /// <summary>
    /// Verifies that generic RunAsync works with AIProjectClient when structured output is configured at agent initialization.
    /// </summary>
    /// <remarks>
    /// AIProjectClient does not support specifying the structured output type at invocation time yet.
    /// The type T provided to RunAsync&lt;T&gt; is ignored by AzureAIProjectChatClient and is only used
    /// for deserializing the agent response by AgentResponse&lt;T&gt;.Result.
    /// </remarks>
    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public async Task RunGenericWithResponseFormatAtAgentInitializationReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var session = await agent.CreateSessionAsync();
        await using var cleanup = new SessionCleanup(session, this.Fixture);

        // Act
        AgentResponse<CityInfo> response = await agent.RunAsync<CityInfo>(
            new ChatMessage(ChatRole.User, "Provide information about the capital of France."),
            session);

        // Assert
        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);

        Assert.NotNull(response.Result);
        Assert.Equal("Paris", response.Result.Name);
    }

    [Fact(Skip = NotSupported)]
    public override Task RunWithGenericTypeReturnsExpectedResultAsync() =>
        base.RunWithGenericTypeReturnsExpectedResultAsync();

    [Fact(Skip = NotSupported)]
    public override Task RunWithResponseFormatReturnsExpectedResultAsync() =>
        base.RunWithResponseFormatReturnsExpectedResultAsync();

    [Fact(Skip = NotSupported)]
    public override Task RunWithPrimitiveTypeReturnsExpectedResultAsync() =>
        base.RunWithPrimitiveTypeReturnsExpectedResultAsync();
}

/// <summary>
/// Represents a fixture for testing AIProjectClient with structured output of type <typeparamref name="T"/> provided at agent initialization.
/// </summary>
public class AIProjectClientStructuredOutputFixture<T> : AIProjectClientFixture
{
    public override Task InitializeAsync()
    {
        var agentOptions = new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions()
            {
                ResponseFormat = ChatResponseFormat.ForJsonSchema<T>(AgentAbstractionsJsonUtilities.DefaultOptions)
            },
        };

        return this.InitializeAsync(agentOptions);
    }
}
