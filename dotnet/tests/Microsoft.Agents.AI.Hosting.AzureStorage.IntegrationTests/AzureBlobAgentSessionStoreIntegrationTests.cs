// Copyright (c) Microsoft. All rights reserved.

#if NET8_0_OR_GREATER
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Azure;
using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;
using Microsoft.Agents.AI.Hosting.AzureStorage.Tests;
using Shared.IntegrationTests;
#endif

namespace Microsoft.Agents.AI.Hosting.AzureStorage.IntegrationTests;

public sealed class AzureBlobAgentSessionStoreIntegrationTests
{
#if NET8_0_OR_GREATER
    [Fact(Skip = "Requires a provisioned Azure Storage account and data-plane permissions in CI.")]
    public async Task HostedAgentThroughTestServer_PersistsSessionInLiveBlobStorageAsync()
    {
        // Arrange
        string? endpoint = Environment.GetEnvironmentVariable("AZURE_STORAGE_BLOB_ENDPOINT");
        Assert.SkipWhen(string.IsNullOrWhiteSpace(endpoint), "AZURE_STORAGE_BLOB_ENDPOINT is not configured.");

        BlobServiceClient serviceClient = new(
            new Uri(endpoint),
            TestAzureCliCredentials.CreateAzureCliCredential());
        BlobContainerClient containerClient =
            serviceClient.GetBlobContainerClient($"af-session-it-{Guid.NewGuid():N}");

        try
        {
            // Act
            await using FakeTestAgentHost host =
                await FakeTestAgentHost.StartAsync(containerClient);
            FakeTestAgentHost.FakeTestAgentRunResult result = await host.RunTwoTurnsAsync();
            List<BlobItem> blobs = [];
            await foreach (BlobItem blob in containerClient.GetBlobsAsync())
            {
                blobs.Add(blob);
            }

            BlobItem storedBlob = Assert.Single(blobs);
            BlobClient storedBlobClient = containerClient.GetBlobClient(storedBlob.Name);
            Response<BlobDownloadResult> download = await storedBlobClient.DownloadContentAsync();
            string persistedSession = download.Value.Content.ToString();

            // Assert
            Assert.Contains("Turn 1", result.FirstResponse, StringComparison.Ordinal);
            Assert.Contains("Turn 2", result.SecondResponse, StringComparison.Ordinal);
            Assert.EndsWith(".json", storedBlob.Name, StringComparison.Ordinal);
            Assert.Equal("application/json", storedBlob.Properties.ContentType);
            Assert.Contains("turnCounter", persistedSession, StringComparison.Ordinal);
            Assert.Contains("\"count\":2", persistedSession, StringComparison.Ordinal);
            Assert.True((await storedBlobClient.ExistsAsync()).Value);
        }
        finally
        {
            await containerClient.DeleteIfExistsAsync();
        }
    }
#endif
}
