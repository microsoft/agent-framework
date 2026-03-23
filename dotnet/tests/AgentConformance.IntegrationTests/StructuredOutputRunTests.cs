// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Conformance tests for structured output handling for run methods on agents.
/// </summary>
/// <typeparam name="TAgentFixture">The type of test fixture used by the concrete test implementation.</typeparam>
/// <param name="createAgentFixture">Function to create the test fixture with.</param>
public abstract class StructuredOutputRunTests<TAgentFixture>(Func<TAgentFixture> createAgentFixture) : AgentTests<TAgentFixture>(createAgentFixture)
    where TAgentFixture : IAgentFixture
{
    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithResponseFormatReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var session = await agent.CreateSessionAsync();
        await using var cleanup = new SessionCleanup(session, this.Fixture);

        var options = new AgentRunOptions
        {
            ResponseFormat = ChatResponseFormat.ForJsonSchema<CityInfo>(AgentAbstractionsJsonUtilities.DefaultOptions)
        };

        // Act
        var response = await agent.RunAsync(new ChatMessage(ChatRole.User, "Provide information about the capital of France."), session, options);

        // Assert
        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Contains("Paris", response.Text);
        Assert.True(TryDeserialize(response.Text, AgentAbstractionsJsonUtilities.DefaultOptions, out CityInfo cityInfo));
        Assert.Equal("Paris", cityInfo.Name);
    }

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithGenericTypeReturnsExpectedResultAsync()
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

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithPrimitiveTypeReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = this.Fixture.Agent;
        var session = await agent.CreateSessionAsync();
        await using var cleanup = new SessionCleanup(session, this.Fixture);

        // Act - Request a primitive type, which requires wrapping in an object schema
        AgentResponse<int> response = await agent.RunAsync<int>(
            new ChatMessage(ChatRole.User, "What is the sum of 15 and 27? Respond with just the number."),
            session);

        // Assert
        Assert.NotNull(response);
        Assert.Single(response.Messages);
        Assert.Equal(42, response.Result);
    }

    protected static bool TryDeserialize<T>(string json, JsonSerializerOptions jsonSerializerOptions, out T structuredOutput)
    {
        try
        {
            T? deserialized = JsonSerializer.Deserialize<T>(json, jsonSerializerOptions);
            if (deserialized is null)
            {
                structuredOutput = default!;
                return false;
            }

            structuredOutput = deserialized;
            return true;
        }
        catch
        {
            structuredOutput = default!;
            return false;
        }
    }
}

public sealed class CityInfo
{
    public string? Name { get; set; }
}
