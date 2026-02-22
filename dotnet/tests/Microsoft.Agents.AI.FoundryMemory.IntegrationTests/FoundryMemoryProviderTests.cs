// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Shared.IntegrationTests;

namespace Microsoft.Agents.AI.FoundryMemory.IntegrationTests;

/// <summary>
/// Integration tests for <see cref="FoundryMemoryProvider"/> against a configured Azure AI Foundry Memory service.
/// </summary>
/// <remarks>
/// These integration tests are skipped by default and require a live Azure AI Foundry Memory service.
/// The tests need to be updated to use the new AIAgent-based API pattern.
/// Set <see cref="SkipReason"/> to null to enable them after configuring the service.
/// </remarks>
public sealed class FoundryMemoryProviderTests : IDisposable
{
    private const string SkipReason = "Requires an Azure AI Foundry Memory service configured"; // Set to null to enable.

    private readonly AIProjectClient? _client;
    private readonly string? _memoryStoreName;
    private readonly string? _deploymentName;
    private bool _disposed;

    public FoundryMemoryProviderTests()
    {
        IConfigurationRoot configuration = new ConfigurationBuilder()
            .AddJsonFile(path: "testsettings.development.json", optional: true, reloadOnChange: true)
            .AddEnvironmentVariables()
            .AddUserSecrets<FoundryMemoryProviderTests>(optional: true)
            .Build();

        var endpoint = configuration[TestSettings.AzureAIProjectEndpoint];
        var memoryStoreName = configuration[TestSettings.AzureAIMemoryStoreId];
        var deploymentName = configuration[TestSettings.AzureAIModelDeploymentName];

        if (!string.IsNullOrWhiteSpace(endpoint) &&
            !string.IsNullOrWhiteSpace(memoryStoreName))
        {
            this._client = new AIProjectClient(new Uri(endpoint), new AzureCliCredential());
            this._memoryStoreName = memoryStoreName;
            this._deploymentName = deploymentName ?? "gpt-4.1-mini";
        }
    }

    [Fact(Skip = SkipReason)]
    public async Task CanAddAndRetrieveUserMemoriesAsync()
    {
        // Arrange
        FoundryMemoryProvider memoryProvider = new(
            this._client!,
            this._memoryStoreName!,
            stateInitializer: _ => new(new FoundryMemoryProviderScope("it-user-1")));

        AIAgent agent = await this._client!.CreateAIAgentAsync(this._deploymentName!,
            options: new ChatClientAgentOptions { AIContextProviders = [memoryProvider] });

        AgentSession session = await agent.CreateSessionAsync();

        await memoryProvider.EnsureStoredMemoriesDeletedAsync(session);

        // Act
        AgentResponse resultBefore = await agent.RunAsync("What is my name?", session);
        Assert.DoesNotContain("Caoimhe", resultBefore.Text);

        await agent.RunAsync("Hello, my name is Caoimhe.", session);
        await memoryProvider.WhenUpdatesCompletedAsync();
        await Task.Delay(2000);

        AgentResponse resultAfter = await agent.RunAsync("What is my name?", session);

        // Cleanup
        await memoryProvider.EnsureStoredMemoriesDeletedAsync(session);

        // Assert
        Assert.Contains("Caoimhe", resultAfter.Text);
    }

    [Fact(Skip = SkipReason)]
    public async Task DoesNotLeakMemoriesAcrossScopesAsync()
    {
        // Arrange
        FoundryMemoryProvider memoryProvider1 = new(
            this._client!,
            this._memoryStoreName!,
            stateInitializer: _ => new(new FoundryMemoryProviderScope("it-scope-a")));

        FoundryMemoryProvider memoryProvider2 = new(
            this._client!,
            this._memoryStoreName!,
            stateInitializer: _ => new(new FoundryMemoryProviderScope("it-scope-b")));

        AIAgent agent1 = await this._client!.CreateAIAgentAsync(this._deploymentName!,
            options: new ChatClientAgentOptions { AIContextProviders = [memoryProvider1] });
        AIAgent agent2 = await this._client!.CreateAIAgentAsync(this._deploymentName!,
            options: new ChatClientAgentOptions { AIContextProviders = [memoryProvider2] });

        AgentSession session1 = await agent1.CreateSessionAsync();
        AgentSession session2 = await agent2.CreateSessionAsync();

        await memoryProvider1.EnsureStoredMemoriesDeletedAsync(session1);
        await memoryProvider2.EnsureStoredMemoriesDeletedAsync(session2);

        // Act - add memory only to scope A
        await agent1.RunAsync("Hello, I'm an AI tutor and my name is Caoimhe.", session1);
        await memoryProvider1.WhenUpdatesCompletedAsync();
        await Task.Delay(2000);

        AgentResponse result1 = await agent1.RunAsync("What is your name?", session1);
        AgentResponse result2 = await agent2.RunAsync("What is your name?", session2);

        // Assert
        Assert.Contains("Caoimhe", result1.Text);
        Assert.DoesNotContain("Caoimhe", result2.Text);

        // Cleanup
        await memoryProvider1.EnsureStoredMemoriesDeletedAsync(session1);
        await memoryProvider2.EnsureStoredMemoriesDeletedAsync(session2);
    }

    public void Dispose()
    {
        if (!this._disposed)
        {
            this._disposed = true;
        }
    }
}
