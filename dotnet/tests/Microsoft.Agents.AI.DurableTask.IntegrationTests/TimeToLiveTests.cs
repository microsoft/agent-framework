// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Reflection;
using Microsoft.Agents.AI.DurableTask.State;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Client.Entities;
using Microsoft.Extensions.Configuration;
using OpenAI.Chat;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests;

/// <summary>
/// Tests for Time-To-Live (TTL) functionality of durable agent entities.
/// </summary>
[Collection("Sequential")]
[Trait("Category", "Integration")]
public sealed class TimeToLiveTests(ITestOutputHelper outputHelper) : IDisposable
{
    private static readonly TimeSpan s_defaultTimeout = Debugger.IsAttached
        ? TimeSpan.FromMinutes(5)
        : TimeSpan.FromSeconds(30);

    private static readonly IConfiguration s_configuration =
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();

    private readonly ITestOutputHelper _outputHelper = outputHelper;
    private readonly CancellationTokenSource _cts = new(delay: s_defaultTimeout);

    private CancellationToken TestTimeoutToken => this._cts.Token;

    public void Dispose() => this._cts.Dispose();

    [Fact]
    public async Task EntityExpiresAfterTTLAsync()
    {
        // Arrange: Create agent with short TTL (10 seconds)
        TimeSpan ttl = TimeSpan.FromSeconds(10);
        AIAgent simpleAgent = TestHelper.GetAzureOpenAIChatClient(s_configuration).CreateAIAgent(
            name: "TTLTestAgent",
            instructions: "You are a helpful assistant."
        );

        using TestHelper testHelper = TestHelper.Start(
            this._outputHelper,
            options =>
            {
                options.DefaultTimeToLive = ttl;
                options.MinimumTimeToLiveSignalDelay = TimeSpan.FromSeconds(1);
                options.AddAIAgent(simpleAgent);
            });

        AIAgent agentProxy = simpleAgent.AsDurableAgentProxy(testHelper.Services);
        AgentThread thread = agentProxy.GetNewThread();
        DurableTaskClient client = testHelper.GetClient();
        AgentSessionId sessionId = thread.GetService<AgentSessionId>();

        // Act: Send a message to the agent
        await agentProxy.RunAsync(
            message: "Hello!",
            thread,
            cancellationToken: this.TestTimeoutToken);

        // Verify entity exists and get expiration time
        EntityMetadata? entity = await client.Entities.GetEntityAsync(sessionId, true, this.TestTimeoutToken);
        Assert.NotNull(entity);
        Assert.True(entity.IncludesState);

        DurableAgentState state = entity.State.ReadAs<DurableAgentState>();
        Assert.NotNull(state.Data.ExpirationTimeUtc);
        DateTime expirationTime = state.Data.ExpirationTimeUtc.Value;
        Assert.True(expirationTime > DateTime.UtcNow);

        // Calculate how long to wait: expiration time + buffer for signal processing
        TimeSpan waitTime = expirationTime - DateTime.UtcNow + TimeSpan.FromSeconds(1);
        if (waitTime > TimeSpan.Zero)
        {
            await Task.Delay(waitTime, this.TestTimeoutToken);
        }

        // Poll the entity state until it's deleted (with timeout)
        DateTime pollTimeout = DateTime.UtcNow.AddSeconds(10);
        bool entityDeleted = false;
        while (DateTime.UtcNow < pollTimeout && !entityDeleted)
        {
            entity = await client.Entities.GetEntityAsync(sessionId, true, this.TestTimeoutToken);
            entityDeleted = entity is null;

            if (!entityDeleted)
            {
                await Task.Delay(TimeSpan.FromSeconds(1), this.TestTimeoutToken);
            }
        }

        // Assert: Verify entity state is deleted
        Assert.True(entityDeleted, "Entity should have been deleted after TTL expiration");
    }

    [Fact]
    public async Task EntityTTLResetsOnInteractionAsync()
    {
        // Arrange: Create agent with short TTL
        TimeSpan ttl = TimeSpan.FromSeconds(6);
        AIAgent simpleAgent = TestHelper.GetAzureOpenAIChatClient(s_configuration).CreateAIAgent(
            name: "TTLResetTestAgent",
            instructions: "You are a helpful assistant."
        );

        using TestHelper testHelper = TestHelper.Start(
            this._outputHelper,
            options =>
            {
                options.DefaultTimeToLive = ttl;
                options.MinimumTimeToLiveSignalDelay = TimeSpan.FromSeconds(1);
                options.AddAIAgent(simpleAgent);
            });

        AIAgent agentProxy = simpleAgent.AsDurableAgentProxy(testHelper.Services);
        AgentThread thread = agentProxy.GetNewThread();
        DurableTaskClient client = testHelper.GetClient();
        AgentSessionId sessionId = thread.GetService<AgentSessionId>();

        // Act: Send first message
        await agentProxy.RunAsync(
            message: "Hello!",
            thread,
            cancellationToken: this.TestTimeoutToken);

        EntityMetadata? entity = await client.Entities.GetEntityAsync(sessionId, true, this.TestTimeoutToken);
        Assert.NotNull(entity);
        Assert.True(entity.IncludesState);

        DurableAgentState state = entity.State.ReadAs<DurableAgentState>();
        DateTime firstExpirationTime = state.Data.ExpirationTimeUtc!.Value;

        // Wait partway through TTL
        await Task.Delay(TimeSpan.FromSeconds(3), this.TestTimeoutToken);

        // Send second message (should reset TTL)
        await agentProxy.RunAsync(
            message: "Hello again!",
            thread,
            cancellationToken: this.TestTimeoutToken);

        // Verify expiration time was updated
        entity = await client.Entities.GetEntityAsync(sessionId, true, this.TestTimeoutToken);
        Assert.NotNull(entity);
        Assert.True(entity.IncludesState);

        state = entity.State.ReadAs<DurableAgentState>();
        DateTime secondExpirationTime = state.Data.ExpirationTimeUtc!.Value;
        Assert.True(secondExpirationTime > firstExpirationTime);

        // Calculate when the original expiration time would have been
        DateTime originalExpirationTime = firstExpirationTime;
        TimeSpan waitUntilOriginalExpiration = originalExpirationTime - DateTime.UtcNow + TimeSpan.FromSeconds(2);

        if (waitUntilOriginalExpiration > TimeSpan.Zero)
        {
            await Task.Delay(waitUntilOriginalExpiration, this.TestTimeoutToken);
        }

        // Assert: Entity should still exist because TTL was reset
        // The new expiration time should be in the future
        entity = await client.Entities.GetEntityAsync(sessionId, true, this.TestTimeoutToken);
        Assert.NotNull(entity);
        Assert.True(entity.IncludesState);

        state = entity.State.ReadAs<DurableAgentState>();
        Assert.NotNull(state);
        Assert.NotNull(state.Data.ExpirationTimeUtc);
        Assert.True(
            state.Data.ExpirationTimeUtc > DateTime.UtcNow,
            "Entity should still be valid because TTL was reset");

        // Wait for the entity to be deleted
        DateTime pollTimeout = DateTime.UtcNow.AddSeconds(10);
        bool entityDeleted = false;
        while (DateTime.UtcNow < pollTimeout && !entityDeleted)
        {
            entity = await client.Entities.GetEntityAsync(sessionId, true, this.TestTimeoutToken);
            entityDeleted = entity is null;

            if (!entityDeleted)
            {
                await Task.Delay(TimeSpan.FromSeconds(1), this.TestTimeoutToken);
            }
        }

        // Assert: Entity should have been deleted
        Assert.True(entityDeleted, "Entity should have been deleted after TTL expiration");
    }
}
