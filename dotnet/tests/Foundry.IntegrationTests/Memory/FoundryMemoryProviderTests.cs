// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.AI.Projects.Memory;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace Foundry.IntegrationTests.Memory;

/// <summary>
/// Integration tests for <see cref="FoundryMemoryProvider"/> against a configured Azure AI Foundry Memory service.
/// </summary>
/// <remarks>
/// These integration tests are skipped by default and require a live Azure AI Foundry Memory service.
/// The tests need to be updated to use the new AIAgent-based API pattern.
/// </remarks>
public sealed class FoundryMemoryProviderTests : IDisposable
{
    private const string SkipReason = "Requires an Azure AI Foundry Memory service configured"; // Set to null to enable.

    private readonly AIProjectClient? _client;
    private readonly string? _memoryStoreName;
    private readonly string? _deploymentName;
    private readonly string? _embeddingDeploymentName;
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
        var embeddingDeploymentName = configuration[TestSettings.AzureAIEmbeddingDeploymentName];

        if (!string.IsNullOrWhiteSpace(endpoint) &&
            !string.IsNullOrWhiteSpace(memoryStoreName))
        {
            this._client = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential());
            this._memoryStoreName = memoryStoreName;
            this._deploymentName = deploymentName ?? "gpt-4.1-mini";
            this._embeddingDeploymentName = embeddingDeploymentName ?? "text-embedding-ada-002";
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

        await memoryProvider.EnsureMemoryStoreCreatedAsync(this._deploymentName!, this._embeddingDeploymentName!);

        AIAgent agent = this._client!.AsAIAgent(new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                ModelId = this._deploymentName!,
                Instructions = "You are a helpful assistant. Use known memories about the user when responding, and do not invent details."
            },
            AIContextProviders = [memoryProvider]
        });

        AgentSession session = await agent.CreateSessionAsync();

        await memoryProvider.EnsureStoredMemoriesDeletedAsync(session);

        // Act
        AgentResponse resultBefore = await agent.RunAsync("What is my name?", session);
        Assert.DoesNotContain("Caoimhe", resultBefore.Text);

        await agent.RunAsync("Hello, my name is Caoimhe.", session);
        await memoryProvider.WhenUpdatesCompletedAsync();
        await Task.Delay(2000);

        // Assert - verify memories were actually created in the store before querying via agent
        var searchResult = await this._client!.MemoryStores.SearchMemoriesAsync(
            this._memoryStoreName!,
            new MemorySearchOptions("it-user-1")
            {
                Items = { ResponseItem.CreateUserMessageItem("Caoimhe") }
            });
        Assert.NotEmpty(searchResult.Value.Memories);

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

        await memoryProvider1.EnsureMemoryStoreCreatedAsync(this._deploymentName!, this._embeddingDeploymentName!);

        AIAgent agent1 = this._client!.AsAIAgent(new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                ModelId = this._deploymentName!,
                Instructions = "You are a helpful assistant. Use known memories about the user when responding, and do not invent details."
            },
            AIContextProviders = [memoryProvider1]
        });

        AIAgent agent2 = this._client!.AsAIAgent(new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                ModelId = this._deploymentName!,
                Instructions = "You are a helpful assistant. Use known memories about the user when responding, and do not invent details."
            },
            AIContextProviders = [memoryProvider2]
        });

        AgentSession session1 = await agent1.CreateSessionAsync();
        AgentSession session2 = await agent2.CreateSessionAsync();

        await memoryProvider1.EnsureStoredMemoriesDeletedAsync(session1);
        await memoryProvider2.EnsureStoredMemoriesDeletedAsync(session2);

        // Act - add memory only to scope A
        await agent1.RunAsync("Hello, I'm an AI tutor and my name is Caoimhe.", session1);
        await memoryProvider1.WhenUpdatesCompletedAsync();
        await Task.Delay(2000);

        // Assert - verify memories were created in scope A but not in scope B
        var searchResultA = await this._client!.MemoryStores.SearchMemoriesAsync(
            this._memoryStoreName!,
            new MemorySearchOptions("it-scope-a")
            {
                Items = { ResponseItem.CreateUserMessageItem("Caoimhe") }
            });
        Assert.NotEmpty(searchResultA.Value.Memories);

        var searchResultB = await this._client.MemoryStores.SearchMemoriesAsync(
            this._memoryStoreName!,
            new MemorySearchOptions("it-scope-b")
            {
                Items = { ResponseItem.CreateUserMessageItem("Caoimhe") }
            });
        Assert.Empty(searchResultB.Value.Memories);

        AgentResponse result1 = await agent1.RunAsync("What is my name?", session1);
        AgentResponse result2 = await agent2.RunAsync("What is my name?", session2);

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
