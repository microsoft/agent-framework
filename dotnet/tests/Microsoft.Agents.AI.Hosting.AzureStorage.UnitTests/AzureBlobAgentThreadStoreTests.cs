// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Azure.Storage.Blobs;
using Microsoft.Agents.AI.Hosting.AzureStorage.Blob;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Hosting.AzureStorage.UnitTests;

/// <summary>
/// Tests for <see cref="AzureBlobAgentThreadStore"/>.
/// </summary>
public sealed class AzureBlobAgentThreadStoreTests(ITestOutputHelper output) : IAsyncLifetime
{
    private const string AzuriteConnectionString = "UseDevelopmentStorage=true";
    private const string TestContainerName = "agent-threads-test";

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    private BlobServiceClient _blobServiceClient;
    private BlobContainerClient _containerClient;
#pragma warning restore CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

    public async Task InitializeAsync()
    {
        await AzureStorageEmulatorAvailabilityHelper.SkipIfNotAvailableAsync();

        this._blobServiceClient = new BlobServiceClient(AzuriteConnectionString);
        this._containerClient = this._blobServiceClient.GetBlobContainerClient(TestContainerName);

        // Clean up any existing test container
        await this._containerClient.DeleteIfExistsAsync();
    }

    public async Task DisposeAsync()
    {
        if (this._containerClient is not null)
        {
            await this._containerClient.DeleteIfExistsAsync();
        }
    }

    [SkippableFact]
    public async Task AIHostAgent_SavesAndRetrievesThread_UsingAzureBlobStoreAsync()
    {
        AzureBlobAgentThreadStore threadStore = new(this._containerClient!);
        var testRunner = TestRunner.Initialize(output, threadStore);
        var blobName = GetBlobContainerName(threadStore, testRunner);

        var runResult = await testRunner.RunAgentAsync("hello agent");
        Assert.Single(runResult.ResponseMessages);
        Assert.Equal(2, runResult.ThreadMessages.Count);
        await this.AssertBlobHasTextAsync(blobName, runResult.ThreadMessages);

        var runResult2 = await testRunner.RunAgentAsync("hello again");
        Assert.Single(runResult2.ResponseMessages);
        Assert.Equal(4, runResult2.ThreadMessages.Count);
        await this.AssertBlobHasTextAsync(blobName, runResult2.ThreadMessages);
    }

    private Task AssertBlobHasTextAsync(string blobName, IList<ChatMessage> chatMessages)
    {
        var texts = chatMessages.SelectMany(x => x.Contents).OfType<TextContent>().Select(x => x.Text).ToArray();
        return this.AssertBlobHasTextAsync(blobName, texts);
    }

    private async Task AssertBlobHasTextAsync(string blobName, params string[] expectedTexts)
    {
        var blobClient = this._containerClient.GetBlobClient(blobName);
        var exists = await blobClient.ExistsAsync();
        Assert.True(exists, $"Blob '{blobName}' should exist.");

        var downloadResponse = await blobClient.DownloadContentAsync();
        var blobJson = downloadResponse.Value.Content.ToString();
        output.WriteLine($"Actual blob json: {blobJson}");

        foreach (var text in expectedTexts)
        {
            Assert.Contains(text, blobJson);
        }
    }

    private static string GetBlobContainerName(AzureBlobAgentThreadStore threadStore, TestRunner testRunner)
        => threadStore.GetBlobName(testRunner.HostAgent.Id, testRunner.ConversationId);
}
