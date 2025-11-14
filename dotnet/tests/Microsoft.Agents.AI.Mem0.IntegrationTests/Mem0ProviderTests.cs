// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Shared.IntegrationTests;

namespace Microsoft.Agents.AI.Mem0.IntegrationTests;

/// <summary>
/// Integration tests for <see cref="Mem0Provider"/> against a configured Mem0 service.
/// </summary>
public sealed class Mem0ProviderTests : IDisposable
{
    private const string SkipReason = "Requires a Mem0 service configured"; // Set to null to enable.

    private readonly HttpClient _httpClient;

    public Mem0ProviderTests()
    {
        IConfigurationRoot configuration = new ConfigurationBuilder()
            .AddJsonFile(path: "testsettings.json", optional: true, reloadOnChange: true)
            .AddJsonFile(path: "testsettings.development.json", optional: true, reloadOnChange: true)
            .AddEnvironmentVariables()
            .AddUserSecrets<Mem0ProviderTests>(optional: true)
            .Build();

        var mem0Settings = configuration.GetSection("Mem0").Get<Mem0Configuration>();
        this._httpClient = new HttpClient();

        if (mem0Settings is not null && !string.IsNullOrWhiteSpace(mem0Settings.ServiceUri) && !string.IsNullOrWhiteSpace(mem0Settings.ApiKey))
        {
            this._httpClient.BaseAddress = new Uri(mem0Settings.ServiceUri);
            this._httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Token", mem0Settings.ApiKey);
        }
    }

    [Fact(Skip = SkipReason)]
    public async Task CanAddAndRetrieveUserMemoriesAsync()
    {
        // Arrange
        var question = new ChatMessage(ChatRole.User, "What is my name?");
        var input = new ChatMessage(ChatRole.User, "Hello, my name is Caoimhe.");
        var storageScope = new Mem0ProviderScope { ThreadId = "it-thread-1", UserId = "it-user-1" };
        var sut = new Mem0Provider(this._httpClient, storageScope);

        await sut.ClearStoredMemoriesAsync();
        var ctxBefore = await sut.InvokingAsync(new AIContextProvider.InvokingContext(new[] { question }));
        Assert.DoesNotContain("Caoimhe", ctxBefore.Messages?[0].Text ?? string.Empty);

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(new[] { input }, aiContextProviderMessages: null));
        var ctxAfterAdding = await GetContextWithRetryAsync(sut, question);
        await sut.ClearStoredMemoriesAsync();
        var ctxAfterClearing = await sut.InvokingAsync(new AIContextProvider.InvokingContext(new[] { question }));

        // Assert
        Assert.Contains("Caoimhe", ctxAfterAdding.Messages?[0].Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxAfterClearing.Messages?[0].Text ?? string.Empty);
    }

    [Fact(Skip = SkipReason)]
    public async Task CanAddAndRetrieveAgentMemoriesAsync()
    {
        // Arrange
        var question = new ChatMessage(ChatRole.User, "What is your name?");
        var assistantIntro = new ChatMessage(ChatRole.Assistant, "Hello, I'm a friendly assistant and my name is Caoimhe.");
        var storageScope = new Mem0ProviderScope { AgentId = "it-agent-1" };
        var sut = new Mem0Provider(this._httpClient, storageScope);

        await sut.ClearStoredMemoriesAsync();
        var ctxBefore = await sut.InvokingAsync(new AIContextProvider.InvokingContext(new[] { question }));
        Assert.DoesNotContain("Caoimhe", ctxBefore.Messages?[0].Text ?? string.Empty);

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(new[] { assistantIntro }, aiContextProviderMessages: null));
        var ctxAfterAdding = await GetContextWithRetryAsync(sut, question);
        await sut.ClearStoredMemoriesAsync();
        var ctxAfterClearing = await sut.InvokingAsync(new AIContextProvider.InvokingContext(new[] { question }));

        // Assert
        Assert.Contains("Caoimhe", ctxAfterAdding.Messages?[0].Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxAfterClearing.Messages?[0].Text ?? string.Empty);
    }

    [Fact(Skip = SkipReason)]
    public async Task DoesNotLeakMemoriesAcrossAgentScopesAsync()
    {
        // Arrange
        var question = new ChatMessage(ChatRole.User, "What is your name?");
        var assistantIntro = new ChatMessage(ChatRole.Assistant, "I'm an AI tutor and my name is Caoimhe.");
        var sut1 = new Mem0Provider(this._httpClient, new Mem0ProviderScope { AgentId = "it-agent-a" });
        var sut2 = new Mem0Provider(this._httpClient, new Mem0ProviderScope { AgentId = "it-agent-b" });

        await sut1.ClearStoredMemoriesAsync();
        await sut2.ClearStoredMemoriesAsync();

        var ctxBefore1 = await sut1.InvokingAsync(new AIContextProvider.InvokingContext(new[] { question }));
        var ctxBefore2 = await sut2.InvokingAsync(new AIContextProvider.InvokingContext(new[] { question }));
        Assert.DoesNotContain("Caoimhe", ctxBefore1.Messages?[0].Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxBefore2.Messages?[0].Text ?? string.Empty);

        // Act
        await sut1.InvokedAsync(new AIContextProvider.InvokedContext(new[] { assistantIntro }, aiContextProviderMessages: null));
        var ctxAfterAdding1 = await GetContextWithRetryAsync(sut1, question);
        var ctxAfterAdding2 = await GetContextWithRetryAsync(sut2, question);

        // Assert
        Assert.Contains("Caoimhe", ctxAfterAdding1.Messages?[0].Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxAfterAdding2.Messages?[0].Text ?? string.Empty);

        // Cleanup
        await sut1.ClearStoredMemoriesAsync();
        await sut2.ClearStoredMemoriesAsync();
    }

    private static async Task<AIContext> GetContextWithRetryAsync(Mem0Provider provider, ChatMessage question, int attempts = 5, int delayMs = 1000)
    {
        AIContext? ctx = null;
        for (int i = 0; i < attempts; i++)
        {
            ctx = await provider.InvokingAsync(new AIContextProvider.InvokingContext(new[] { question }), CancellationToken.None);
            var text = ctx.Messages?[0].Text;
            if (!string.IsNullOrEmpty(text) && text.IndexOf("Caoimhe", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                break;
            }
            await Task.Delay(delayMs);
        }
        return ctx!;
    }

    public void Dispose()
    {
        this._httpClient.Dispose();
    }
}
