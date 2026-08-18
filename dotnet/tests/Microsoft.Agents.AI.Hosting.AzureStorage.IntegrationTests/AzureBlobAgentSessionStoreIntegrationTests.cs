// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure;
using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Shared.IntegrationTests;

namespace Microsoft.Agents.AI.Hosting.AzureStorage.IntegrationTests;

public sealed class AzureBlobAgentSessionStoreIntegrationTests
{
    [Fact(Skip = "Requires a provisioned Azure Storage account and data-plane permissions in CI.")]
    public async Task HostedRegistration_PersistsAndRestoresSessionInLiveBlobStorageAsync()
    {
        // Arrange
        string? endpoint = Environment.GetEnvironmentVariable("AZURE_STORAGE_BLOB_ENDPOINT");
        Assert.SkipWhen(string.IsNullOrWhiteSpace(endpoint), "AZURE_STORAGE_BLOB_ENDPOINT is not configured.");

        BlobServiceClient serviceClient = new(
            new Uri(endpoint),
            TestAzureCliCredentials.CreateAzureCliCredential());
        BlobContainerClient containerClient =
            serviceClient.GetBlobContainerClient($"af-session-it-{Guid.NewGuid():N}");
        string marker = $"live-blob-{Guid.NewGuid():N}";
        const string AgentName = "live-blob-agent";
        const string SessionId = "live-session";

        await containerClient.CreateAsync();

        try
        {
            var services = new ServiceCollection();
            IHostedAgentBuilder builder = services.AddAIAgent(
                AgentName,
                (_, key) => new ChatClientAgent(new NotInvokedChatClient(), name: key));
            builder.WithAzureBlobSessionStore(containerClient, withIsolation: false);

            using ServiceProvider serviceProvider = services.BuildServiceProvider();
            AIAgent agent = serviceProvider.GetRequiredKeyedService<AIAgent>(AgentName);
            AgentSessionStore sessionStore =
                serviceProvider.GetRequiredKeyedService<AgentSessionStore>(AgentName);
            var hostAgent = new AIHostAgent(agent, sessionStore);
            AgentSession session = await agent.CreateSessionAsync();
            session.StateBag.SetValue("marker", marker);

            // Act
            await hostAgent.SaveSessionAsync(SessionId, session);

            List<BlobItem> blobs = [];
            await foreach (BlobItem blob in containerClient.GetBlobsAsync())
            {
                blobs.Add(blob);
            }

            BlobItem storedBlob = Assert.Single(blobs);
            BlobClient storedBlobClient = containerClient.GetBlobClient(storedBlob.Name);
            Response<BlobDownloadResult> download = await storedBlobClient.DownloadContentAsync();

            var restartedStore = new AzureBlobAgentSessionStore(containerClient, AgentName);
            AgentSession restored = await restartedStore.GetSessionAsync(agent, SessionId);

            // Assert
            Assert.EndsWith(".json", storedBlob.Name, StringComparison.Ordinal);
            Assert.Equal("application/json", storedBlob.Properties.ContentType);
            Assert.Contains(marker, download.Value.Content.ToString(), StringComparison.Ordinal);
            Assert.Equal(marker, restored.StateBag.GetValue<string>("marker"));
            Assert.True((await storedBlobClient.ExistsAsync()).Value);

            await sessionStore.DeleteSessionAsync(agent, SessionId);
            Assert.False((await storedBlobClient.ExistsAsync()).Value);
        }
        finally
        {
            await containerClient.DeleteIfExistsAsync();
        }
    }

    private sealed class NotInvokedChatClient : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            CancellationToken cancellationToken = default)
            => throw new NotImplementedException();

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose()
        {
        }
    }
}
