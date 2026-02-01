// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Shared.IntegrationTests;

namespace Microsoft.Agents.AI.FoundryMemory.IntegrationTests;

/// <summary>
/// Integration tests for <see cref="FoundryMemoryProvider"/> against a configured Azure AI Foundry Memory service.
/// </summary>
public sealed class FoundryMemoryProviderTests : IDisposable
{
    private const string SkipReason = "Requires an Azure AI Foundry Memory service configured"; // Set to null to enable.

    private readonly AIProjectClient? _client;
    private readonly string? _memoryStoreName;
    private bool _disposed;

    public FoundryMemoryProviderTests()
    {
        IConfigurationRoot configuration = new ConfigurationBuilder()
            .AddJsonFile(path: "testsettings.json", optional: true, reloadOnChange: true)
            .AddJsonFile(path: "testsettings.development.json", optional: true, reloadOnChange: true)
            .AddEnvironmentVariables()
            .AddUserSecrets<FoundryMemoryProviderTests>(optional: true)
            .Build();

        var foundrySettings = configuration.GetSection("FoundryMemory").Get<FoundryMemoryConfiguration>();

        if (foundrySettings is not null &&
            !string.IsNullOrWhiteSpace(foundrySettings.Endpoint) &&
            !string.IsNullOrWhiteSpace(foundrySettings.MemoryStoreName))
        {
            this._client = new AIProjectClient(new Uri(foundrySettings.Endpoint), new AzureCliCredential());
            this._memoryStoreName = foundrySettings.MemoryStoreName;
        }
    }

    [Fact(Skip = SkipReason)]
    public async Task CanAddAndRetrieveUserMemoriesAsync()
    {
        // Arrange
        var question = new ChatMessage(ChatRole.User, "What is my name?");
        var input = new ChatMessage(ChatRole.User, "Hello, my name is Caoimhe.");
        var storageScope = new FoundryMemoryProviderScope { Scope = "it-user-1" };
        var options = new FoundryMemoryProviderOptions { MemoryStoreName = this._memoryStoreName! };
        var sut = new FoundryMemoryProvider(this._client!, storageScope, options);

        await sut.EnsureStoredMemoriesDeletedAsync();
        var ctxBefore = await sut.InvokingAsync(new AIContextProvider.InvokingContext([question]));
        Assert.DoesNotContain("Caoimhe", ctxBefore.Messages?[0].Text ?? string.Empty);

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext([input], aiContextProviderMessages: null));
        var ctxAfterAdding = await GetContextWithRetryAsync(sut, question);
        await sut.EnsureStoredMemoriesDeletedAsync();
        var ctxAfterClearing = await sut.InvokingAsync(new AIContextProvider.InvokingContext([question]));

        // Assert
        Assert.Contains("Caoimhe", ctxAfterAdding.Messages?[0].Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxAfterClearing.Messages?[0].Text ?? string.Empty);
    }

    [Fact(Skip = SkipReason)]
    public async Task CanAddAndRetrieveAssistantMemoriesAsync()
    {
        // Arrange
        var question = new ChatMessage(ChatRole.User, "What is your name?");
        var assistantIntro = new ChatMessage(ChatRole.Assistant, "Hello, I'm a friendly assistant and my name is Caoimhe.");
        var storageScope = new FoundryMemoryProviderScope { Scope = "it-agent-1" };
        var options = new FoundryMemoryProviderOptions { MemoryStoreName = this._memoryStoreName! };
        var sut = new FoundryMemoryProvider(this._client!, storageScope, options);

        await sut.EnsureStoredMemoriesDeletedAsync();
        var ctxBefore = await sut.InvokingAsync(new AIContextProvider.InvokingContext([question]));
        Assert.DoesNotContain("Caoimhe", ctxBefore.Messages?[0].Text ?? string.Empty);

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext([assistantIntro], aiContextProviderMessages: null));
        var ctxAfterAdding = await GetContextWithRetryAsync(sut, question);
        await sut.EnsureStoredMemoriesDeletedAsync();
        var ctxAfterClearing = await sut.InvokingAsync(new AIContextProvider.InvokingContext([question]));

        // Assert
        Assert.Contains("Caoimhe", ctxAfterAdding.Messages?[0].Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxAfterClearing.Messages?[0].Text ?? string.Empty);
    }

    [Fact(Skip = SkipReason)]
    public async Task DoesNotLeakMemoriesAcrossScopesAsync()
    {
        // Arrange
        var question = new ChatMessage(ChatRole.User, "What is your name?");
        var assistantIntro = new ChatMessage(ChatRole.Assistant, "I'm an AI tutor and my name is Caoimhe.");
        var options = new FoundryMemoryProviderOptions { MemoryStoreName = this._memoryStoreName! };
        var sut1 = new FoundryMemoryProvider(this._client!, new FoundryMemoryProviderScope { Scope = "it-scope-a" }, options);
        var sut2 = new FoundryMemoryProvider(this._client!, new FoundryMemoryProviderScope { Scope = "it-scope-b" }, options);

        await sut1.EnsureStoredMemoriesDeletedAsync();
        await sut2.EnsureStoredMemoriesDeletedAsync();

        var ctxBefore1 = await sut1.InvokingAsync(new AIContextProvider.InvokingContext([question]));
        var ctxBefore2 = await sut2.InvokingAsync(new AIContextProvider.InvokingContext([question]));
        Assert.DoesNotContain("Caoimhe", ctxBefore1.Messages?[0].Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxBefore2.Messages?[0].Text ?? string.Empty);

        // Act
        await sut1.InvokedAsync(new AIContextProvider.InvokedContext([assistantIntro], aiContextProviderMessages: null));
        var ctxAfterAdding1 = await GetContextWithRetryAsync(sut1, question);
        var ctxAfterAdding2 = await GetContextWithRetryAsync(sut2, question);

        // Assert
        Assert.Contains("Caoimhe", ctxAfterAdding1.Messages?[0].Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxAfterAdding2.Messages?[0].Text ?? string.Empty);

        // Cleanup
        await sut1.EnsureStoredMemoriesDeletedAsync();
        await sut2.EnsureStoredMemoriesDeletedAsync();
    }

    [Fact(Skip = SkipReason)]
    public async Task ClearStoredMemoriesRemovesAllMemoriesAsync()
    {
        // Arrange
        var input1 = new ChatMessage(ChatRole.User, "My favorite color is blue.");
        var input2 = new ChatMessage(ChatRole.User, "My favorite food is pizza.");
        var question = new ChatMessage(ChatRole.User, "What do you know about my preferences?");
        var storageScope = new FoundryMemoryProviderScope { Scope = "it-clear-test" };
        var options = new FoundryMemoryProviderOptions { MemoryStoreName = this._memoryStoreName! };
        var sut = new FoundryMemoryProvider(this._client!, storageScope, options);

        await sut.EnsureStoredMemoriesDeletedAsync();

        // Act - Add multiple memories
        await sut.InvokedAsync(new AIContextProvider.InvokedContext([input1], aiContextProviderMessages: null));
        await sut.InvokedAsync(new AIContextProvider.InvokedContext([input2], aiContextProviderMessages: null));
        var ctxBeforeClear = await GetContextWithRetryAsync(sut, question, searchTerms: ["blue", "pizza"]);

        await sut.EnsureStoredMemoriesDeletedAsync();
        var ctxAfterClear = await sut.InvokingAsync(new AIContextProvider.InvokingContext([question]));

        // Assert
        var textBefore = ctxBeforeClear.Messages?[0].Text ?? string.Empty;
        var textAfter = ctxAfterClear.Messages?[0].Text ?? string.Empty;

        Assert.True(textBefore.Contains("blue") || textBefore.Contains("pizza"), "Should contain at least one preference before clear");
        Assert.DoesNotContain("blue", textAfter);
        Assert.DoesNotContain("pizza", textAfter);
    }

    private static async Task<AIContext> GetContextWithRetryAsync(
        FoundryMemoryProvider provider,
        ChatMessage question,
        string[]? searchTerms = null,
        int attempts = 5,
        int delayMs = 2000)
    {
        searchTerms ??= ["Caoimhe"];
        AIContext? ctx = null;

        for (int i = 0; i < attempts; i++)
        {
            ctx = await provider.InvokingAsync(new AIContextProvider.InvokingContext([question]), CancellationToken.None);
            var text = ctx.Messages?[0].Text ?? string.Empty;

            if (Array.Exists(searchTerms, term => text.Contains(term, StringComparison.OrdinalIgnoreCase)))
            {
                break;
            }

            await Task.Delay(delayMs);
        }

        return ctx!;
    }

    public void Dispose()
    {
        if (!this._disposed)
        {
            this._disposed = true;
        }
    }
}
