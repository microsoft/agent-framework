// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure;
using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;
#if NET8_0_OR_GREATER
using Microsoft.Agents.AI.Hosting.AzureStorage.Tests;
#endif

namespace Microsoft.Agents.AI.Hosting.AzureStorage.UnitTests;

/// <summary>
/// Verifies Azure Blob Storage session persistence.
/// </summary>
public sealed class AzureBlobAgentSessionStoreTests : IAsyncLifetime
{
    private static readonly string s_connectionString =
        Environment.GetEnvironmentVariable("AZURE_STORAGE_BLOB_CONNECTION_STRING") ?? "UseDevelopmentStorage=true";
    private static readonly BlobClientOptions s_clientOptions = new()
    {
        Retry =
        {
            MaxRetries = 0,
            NetworkTimeout = TimeSpan.FromSeconds(3),
        },
    };
    private static readonly BlobServiceClient s_blobServiceClient = new(s_connectionString, s_clientOptions);
    private static readonly Task<bool> s_azuriteAvailability = IsAzuriteAvailableAsync();

    private readonly BlobContainerClient _containerClient;
    private bool _azuriteAvailable;

    /// <summary>
    /// Initializes a new instance of the <see cref="AzureBlobAgentSessionStoreTests"/> class.
    /// </summary>
    public AzureBlobAgentSessionStoreTests()
    {
        this._containerClient = s_blobServiceClient.GetBlobContainerClient($"agent-sessions-{Guid.NewGuid():N}");
    }

    /// <inheritdoc />
    public async ValueTask InitializeAsync()
    {
        this._azuriteAvailable = await s_azuriteAvailability;
        bool required = string.Equals(
            Environment.GetEnvironmentVariable("AZURITE_AVAILABLE"),
            bool.TrueString,
            StringComparison.OrdinalIgnoreCase);

        Assert.SkipWhen(!required && !this._azuriteAvailable, "Azurite is not available.");
        Assert.True(this._azuriteAvailable, "Azurite was required but could not be reached.");
    }

    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        if (this._azuriteAvailable)
        {
            await this._containerClient.DeleteIfExistsAsync();
        }
        GC.SuppressFinalize(this);
    }

    [Fact]
    public async Task SaveAndGetSessionAsync_PersistsAcrossStoreAndAgentInstancesAsync()
    {
        // Arrange
        AIAgent savingAgent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        AIAgent loadingAgent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        AgentSession session = await savingAgent.CreateSessionAsync();
        session.StateBag.SetValue("marker", "saved");

        var savingStore = new AzureBlobAgentSessionStore(this._containerClient, "assistant");
        var loadingStore = new AzureBlobAgentSessionStore(this._containerClient, "assistant");
        var key = new AgentSessionStoreKey("session-1").WithPartition("user", "user-1");

        // Act
        await savingStore.SaveSessionAsync(savingAgent, key, session);
        AgentSession? restored = await loadingStore.GetSessionAsync(loadingAgent, key);

        // Assert
        Assert.NotNull(restored);
        Assert.Equal("saved", restored.StateBag.GetValue<string>("marker"));
    }

    [Fact]
    public async Task SaveAndGetSessionAsync_SupportsDistinctLongOpaqueIdsAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        var store = new AzureBlobAgentSessionStore(this._containerClient, "assistant");
        string commonPrefix = new('s', 2048);
        string firstId = commonPrefix + "\0:first";
        string secondId = commonPrefix + "\u0001/second";
        var firstKey = new AgentSessionStoreKey(firstId);
        var secondKey = new AgentSessionStoreKey(secondId);

        AgentSession firstSession = await agent.CreateSessionAsync();
        firstSession.StateBag.SetValue("marker", "first");
        AgentSession secondSession = await agent.CreateSessionAsync();
        secondSession.StateBag.SetValue("marker", "second");

        // Act
        await store.SaveSessionAsync(agent, firstKey, firstSession);
        await store.SaveSessionAsync(agent, secondKey, secondSession);
        AgentSession? restoredFirst = await store.GetSessionAsync(agent, firstKey);
        AgentSession? restoredSecond = await store.GetSessionAsync(agent, secondKey);
        List<string> blobNames = [];
        await foreach (BlobItem blob in this._containerClient.GetBlobsAsync())
        {
            blobNames.Add(blob.Name);
        }

        // Assert
        Assert.NotNull(restoredFirst);
        Assert.NotNull(restoredSecond);
        Assert.Equal("first", restoredFirst.StateBag.GetValue<string>("marker"));
        Assert.Equal("second", restoredSecond.StateBag.GetValue<string>("marker"));
        Assert.Equal(2, blobNames.Count);
        Assert.All(blobNames, blobName => Assert.InRange(blobName.Length, 1, 1024));
    }

    [Fact]
    public async Task GetSessionAsync_MissingSession_ReturnsNullAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        var store = new AzureBlobAgentSessionStore(this._containerClient, "assistant");

        // Act
        AgentSession? restored = await store.GetSessionAsync(
            agent,
            new AgentSessionStoreKey("missing").WithPartition("user", "user-1"));

        // Assert
        Assert.Null(restored);
    }

    [Fact]
    public async Task SaveAndGetSessionAsync_IsolatesPartitionsAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        var store = new AzureBlobAgentSessionStore(this._containerClient, "assistant");
        var user1Key = new AgentSessionStoreKey("session-1").WithPartition("user", "user-1");
        var user2Key = new AgentSessionStoreKey("session-1").WithPartition("user", "user-2");
        AgentSession first = await agent.CreateSessionAsync();
        first.StateBag.SetValue("marker", "first");
        AgentSession second = await agent.CreateSessionAsync();
        second.StateBag.SetValue("marker", "second");

        // Act
        await store.SaveSessionAsync(agent, user1Key, first);
        await store.SaveSessionAsync(agent, user2Key, second);
        AgentSession? restoredFirst = await store.GetSessionAsync(agent, user1Key);
        AgentSession? restoredSecond = await store.GetSessionAsync(agent, user2Key);

        // Assert
        Assert.NotNull(restoredFirst);
        Assert.NotNull(restoredSecond);
        Assert.Equal("first", restoredFirst.StateBag.GetValue<string>("marker"));
        Assert.Equal("second", restoredSecond.StateBag.GetValue<string>("marker"));
    }

    [Fact]
    public async Task SaveAndGetSessionAsync_ScopedAndUnscopedIdentifiersDoNotCollideAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        var store = new AzureBlobAgentSessionStore(this._containerClient, "assistant");
        var partitionedKey = new AgentSessionStoreKey("conversation").WithPartition("tenant", "tenant");
        var unpartitionedKey = new AgentSessionStoreKey("tenant::conversation");
        AgentSession scoped = await agent.CreateSessionAsync();
        scoped.StateBag.SetValue("marker", "scoped");
        AgentSession unscoped = await agent.CreateSessionAsync();
        unscoped.StateBag.SetValue("marker", "unscoped");

        // Act
        await store.SaveSessionAsync(agent, partitionedKey, scoped);
        await store.SaveSessionAsync(agent, unpartitionedKey, unscoped);
        AgentSession? restoredScoped = await store.GetSessionAsync(agent, partitionedKey);
        AgentSession? restoredUnscoped = await store.GetSessionAsync(agent, unpartitionedKey);

        // Assert
        Assert.NotNull(restoredScoped);
        Assert.NotNull(restoredUnscoped);
        Assert.Equal("scoped", restoredScoped.StateBag.GetValue<string>("marker"));
        Assert.Equal("unscoped", restoredUnscoped.StateBag.GetValue<string>("marker"));
    }

    [Fact]
    public async Task SaveSessionAsync_OverwritesExistingSessionAsJsonAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        var store = new AzureBlobAgentSessionStore(this._containerClient, "assistant");
        var key = new AgentSessionStoreKey("session-1");
        AgentSession first = await agent.CreateSessionAsync();
        first.StateBag.SetValue("marker", "first");
        AgentSession second = await agent.CreateSessionAsync();
        second.StateBag.SetValue("marker", "second");

        // Act
        await store.SaveSessionAsync(agent, key, first);
        await store.SaveSessionAsync(agent, key, second);
        AgentSession? restored = await store.GetSessionAsync(agent, key);
        List<BlobItem> blobs = [];
        await foreach (BlobItem blob in this._containerClient.GetBlobsAsync())
        {
            blobs.Add(blob);
        }

        // Assert
        Assert.NotNull(restored);
        BlobItem storedBlob = Assert.Single(blobs);
        Assert.Equal("application/json", storedBlob.Properties.ContentType);
        Assert.Equal("second", restored.StateBag.GetValue<string>("marker"));
    }

    [Fact]
    public async Task GetSessionAsync_MissingContainerWithoutAutoCreatePropagatesErrorAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        BlobContainerClient missingContainer = s_blobServiceClient.GetBlobContainerClient($"missing-{Guid.NewGuid():N}");
        var store = new AzureBlobAgentSessionStore(
            missingContainer,
            "assistant",
            new AzureBlobAgentSessionStoreOptions { CreateContainerIfNotExists = false });

        // Act
        RequestFailedException exception = await Assert.ThrowsAsync<RequestFailedException>(
            () => store.GetSessionAsync(agent, new AgentSessionStoreKey("session-1")).AsTask());

        // Assert
        Assert.Equal(BlobErrorCode.ContainerNotFound.ToString(), exception.ErrorCode);
    }

    [Fact]
    public async Task GetSessionAsync_ReturnsIndependentSnapshotsAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        var store = new AzureBlobAgentSessionStore(this._containerClient, "assistant");
        var key = new AgentSessionStoreKey("session-1");
        AgentSession original = await agent.CreateSessionAsync();
        original.StateBag.SetValue("marker", "saved");
        await store.SaveSessionAsync(agent, key, original);

        // Act
        AgentSession? first = await store.GetSessionAsync(agent, key);
        AgentSession? second = await store.GetSessionAsync(agent, key);
        Assert.NotNull(first);
        Assert.NotNull(second);
        first.StateBag.SetValue("marker", "changed");
        AgentSession? third = await store.GetSessionAsync(agent, key);

        // Assert
        Assert.NotNull(third);
        Assert.NotSame(first, second);
        Assert.Equal("saved", second.StateBag.GetValue<string>("marker"));
        Assert.Equal("saved", third.StateBag.GetValue<string>("marker"));
    }

    [Fact]
    public async Task SaveSessionAsync_ConcurrentFirstWritesCreateContainerSafelyAsync()
    {
        // Arrange
        AIAgent agent = new ChatClientAgent(new NotInvokedChatClient(), name: "assistant");
        var store = new AzureBlobAgentSessionStore(this._containerClient, "assistant");
        List<Task> writes = [];

        for (int index = 0; index < 16; index++)
        {
            AgentSession session = await agent.CreateSessionAsync();
            session.StateBag.SetValue("marker", index.ToString());
            writes.Add(store.SaveSessionAsync(
                agent,
                new AgentSessionStoreKey($"session-{index}"),
                session).AsTask());
        }

        // Act
        await Task.WhenAll(writes);
        List<BlobItem> blobs = [];
        await foreach (BlobItem blob in this._containerClient.GetBlobsAsync())
        {
            blobs.Add(blob);
        }

        // Assert
        Assert.Equal(16, blobs.Count);
    }

#if NET8_0_OR_GREATER
    [Fact]
    public async Task HostedAgentThroughTestServer_PersistsSessionInAzuriteAsync()
    {
        // Arrange
        await using FakeTestAgentHost host =
            await FakeTestAgentHost.StartAsync(this._containerClient);

        // Act
        FakeTestAgentHost.FakeTestAgentRunResult result = await host.RunTwoTurnsAsync();
        List<BlobItem> blobs = [];
        await foreach (BlobItem blob in this._containerClient.GetBlobsAsync())
        {
            blobs.Add(blob);
        }

        BlobItem storedBlob = Assert.Single(blobs);
        Response<BlobDownloadResult> download = await this._containerClient
            .GetBlobClient(storedBlob.Name)
            .DownloadContentAsync();
        string persistedSession = download.Value.Content.ToString();

        // Assert
        Assert.Contains("Turn 1", result.FirstResponse, StringComparison.Ordinal);
        Assert.Contains("Turn 2", result.SecondResponse, StringComparison.Ordinal);
        Assert.Equal("application/json", storedBlob.Properties.ContentType);
        Assert.Contains("turnCounter", persistedSession, StringComparison.Ordinal);
        Assert.Contains("\"count\":2", persistedSession, StringComparison.Ordinal);
    }
#endif

    [Fact]
    public void Constructor_BlobNamePrefixExceedsAzureLimit_Throws()
    {
        // Arrange
        var options = new AzureBlobAgentSessionStoreOptions
        {
            BlobNamePrefix = new string('p', 887),
        };

        // Act & Assert
        Assert.Throws<ArgumentException>(
            () => new AzureBlobAgentSessionStore(this._containerClient, "assistant", options));
    }

    [Fact]
    public void Constructor_InvalidUtf16AgentNamespace_Throws()
    {
        // Arrange
        string invalid = new((char)0xD800, 1);

        // Act and assert
        Assert.Throws<ArgumentException>(
            () => new AzureBlobAgentSessionStore(this._containerClient, invalid));
    }

    private static async Task<bool> IsAzuriteAvailableAsync()
    {
        using CancellationTokenSource cancellationTokenSource = new(TimeSpan.FromSeconds(3));

        try
        {
            await s_blobServiceClient.GetPropertiesAsync(cancellationToken: cancellationTokenSource.Token);
            return true;
        }
        catch (RequestFailedException)
        {
            return false;
        }
        catch (OperationCanceledException) when (cancellationTokenSource.IsCancellationRequested)
        {
            return false;
        }
    }
}
