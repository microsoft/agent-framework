// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Reflection;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Client.Entities;
using Microsoft.DurableTask.Entities;
using Microsoft.Extensions.Configuration;
using OpenAI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests;

/// <summary>
/// Tests for scenarios where an external client interacts with Durable Task Agents.
/// </summary>
[Collection("Sequential")]
[Trait("Category", "Integration")]
public sealed class AgentEntityTests(ITestOutputHelper outputHelper) : IDisposable
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
    public async Task EntityNamePrefixAsync()
    {
        // Setup
        AIAgent simpleAgent = TestHelper.GetAzureOpenAIChatClient(s_configuration).CreateAIAgent(
            name: "TestAgent",
            instructions: "You are a helpful assistant that always responds with a friendly greeting."
        );

        using TestHelper testHelper = TestHelper.Start([simpleAgent], this._outputHelper);

        // A proxy agent is needed to call the hosted test agent
        AIAgent simpleAgentProxy = simpleAgent.AsDurableAgentProxy(testHelper.Services);

        AgentThread thread = simpleAgentProxy.GetNewThread();

        DurableTaskClient client = testHelper.GetClient();

        AgentSessionId sessionId = thread.GetService<AgentSessionId>();
        EntityInstanceId expectedEntityId = new($"dafx-{simpleAgent.Name}", sessionId.Key);

        EntityMetadata? entity = await client.Entities.GetEntityAsync(expectedEntityId, false, this.TestTimeoutToken);

        Assert.Null(entity);

        // Act: send a prompt to the agent
        await simpleAgentProxy.RunAsync(
            message: "Hello!",
            thread,
            cancellationToken: this.TestTimeoutToken);

        // Assert: verify the agent state was stored with the correct entity name prefix
        entity = await client.Entities.GetEntityAsync(expectedEntityId, false, this.TestTimeoutToken);

        Assert.NotNull(entity);
    }
}
