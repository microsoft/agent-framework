// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace Foundry.IntegrationTests;

public class ResponsesAgentStructuredOutputRunTests() : StructuredOutputRunTests<ResponsesAgentStructuredOutputFixture<CityInfo>>(() => new())
{
    private const string NotSupported = "The direct Responses AsAIAgent path does not support specifying structured output type at invocation time.";

    /// <summary>
    /// Verifies that response format provided at agent initialization is used when invoking RunAsync.
    /// </summary>
    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public async Task RunWithResponseFormatAtAgentInitializationReturnsExpectedResultAsync()
    {
        // Arrange
        AIAgent agent = this.Fixture.Agent;
        AgentSession session = await agent.CreateSessionAsync();
        await using var cleanup = new SessionCleanup(session, this.Fixture);

        // Act
        AgentResponse response = await agent.RunAsync(new ChatMessage(ChatRole.User, "Provide information about the capital of France."), session);

        // Assert
        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
        Assert.True(TryDeserialize(response.Text, AgentAbstractionsJsonUtilities.DefaultOptions, out CityInfo cityInfo));
        Assert.Equal("Paris", cityInfo.Name);
    }

    /// <summary>
    /// Verifies that generic RunAsync works when structured output is configured at agent initialization.
    /// </summary>
    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public async Task RunGenericWithResponseFormatAtAgentInitializationReturnsExpectedResultAsync()
    {
        // Arrange
        AIAgent agent = this.Fixture.Agent;
        AgentSession session = await agent.CreateSessionAsync();
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

    public override Task RunWithGenericTypeReturnsExpectedResultAsync()
    {
        Assert.Skip(NotSupported);
        return base.RunWithGenericTypeReturnsExpectedResultAsync();
    }

    public override Task RunWithResponseFormatReturnsExpectedResultAsync()
    {
        Assert.Skip(NotSupported);
        return base.RunWithResponseFormatReturnsExpectedResultAsync();
    }

    public override Task RunWithPrimitiveTypeReturnsExpectedResultAsync()
    {
        Assert.Skip(NotSupported);
        return base.RunWithPrimitiveTypeReturnsExpectedResultAsync();
    }
}

/// <summary>
/// Fixture for testing the direct Responses <see cref="ChatClientAgent"/> path with structured output of type <typeparamref name="T"/> provided at agent initialization.
/// </summary>
public class ResponsesAgentStructuredOutputFixture<T> : ResponsesAgentFixture
{
    public override ValueTask InitializeAsync()
    {
        ChatClientAgentOptions agentOptions = new()
        {
            ChatOptions = new ChatOptions()
            {
                ModelId = TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
                ResponseFormat = ChatResponseFormat.ForJsonSchema<T>(AgentAbstractionsJsonUtilities.DefaultOptions)
            },
        };

        return this.InitializeAsync(agentOptions);
    }
}
