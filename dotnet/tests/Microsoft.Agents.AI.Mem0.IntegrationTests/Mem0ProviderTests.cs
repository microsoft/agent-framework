// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
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

    private static readonly AIAgent s_mockAgent = new Moq.Mock<AIAgent>().Object;

    private readonly HttpClient _httpClient;

    public Mem0ProviderTests()
    {
        IConfigurationRoot configuration = new ConfigurationBuilder()
            .AddJsonFile(path: "testsettings.development.json", optional: true, reloadOnChange: true)
            .AddEnvironmentVariables()
            .AddUserSecrets<Mem0ProviderTests>(optional: true)
            .Build();

        var serviceUri = configuration[TestSettings.Mem0Endpoint];
        var apiKey = configuration[TestSettings.Mem0ApiKey];

        this._httpClient = new HttpClient();

        if (!string.IsNullOrWhiteSpace(serviceUri) && !string.IsNullOrWhiteSpace(apiKey))
        {
            this._httpClient.BaseAddress = new Uri(serviceUri);
            this._httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Token", apiKey);
        }
    }

    [Fact(Skip = SkipReason)]
    public async Task CanAddAndRetrieveUserMemoriesAsync()
    {
        // Arrange
        var question = new ChatMessage(ChatRole.User, "What is my name?");
        var input = new ChatMessage(ChatRole.User, "Hello, my name is Caoimhe.");
        var storageScope = new Mem0ProviderScope { ThreadId = "it-thread-1", UserId = "it-user-1" };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope));

        await sut.ClearStoredMemoriesAsync(mockSession);
        var ctxBefore = await sut.InvokingAsync(new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = new List<ChatMessage> { question } }));
        Assert.DoesNotContain("Caoimhe", ctxBefore.Messages?.LastOrDefault()?.Text ?? string.Empty);

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(s_mockAgent, mockSession, [input], []));
        var ctxAfterAdding = await GetContextWithRetryAsync(sut, mockSession, question);
        await sut.ClearStoredMemoriesAsync(mockSession);
        var ctxAfterClearing = await sut.InvokingAsync(new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = new List<ChatMessage> { question } }));

        // Assert
        Assert.Contains("Caoimhe", ctxAfterAdding.Messages?.LastOrDefault()?.Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxAfterClearing.Messages?.LastOrDefault()?.Text ?? string.Empty);
    }

    [Fact(Skip = SkipReason)]
    public async Task CanAddAndRetrieveAgentMemoriesAsync()
    {
        // Arrange
        var question = new ChatMessage(ChatRole.User, "What is your name?");
        var assistantIntro = new ChatMessage(ChatRole.Assistant, "Hello, I'm a friendly assistant and my name is Caoimhe.");
        var storageScope = new Mem0ProviderScope { AgentId = "it-agent-1" };
        var mockSession = new TestAgentSession();
        var sut = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope));

        await sut.ClearStoredMemoriesAsync(mockSession);
        var ctxBefore = await sut.InvokingAsync(new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = new List<ChatMessage> { question } }));
        Assert.DoesNotContain("Caoimhe", ctxBefore.Messages?.LastOrDefault()?.Text ?? string.Empty);

        // Act
        await sut.InvokedAsync(new AIContextProvider.InvokedContext(s_mockAgent, mockSession, [assistantIntro], []));
        var ctxAfterAdding = await GetContextWithRetryAsync(sut, mockSession, question);
        await sut.ClearStoredMemoriesAsync(mockSession);
        var ctxAfterClearing = await sut.InvokingAsync(new AIContextProvider.InvokingContext(s_mockAgent, mockSession, new AIContext { Messages = new List<ChatMessage> { question } }));

        // Assert
        Assert.Contains("Caoimhe", ctxAfterAdding.Messages?.LastOrDefault()?.Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxAfterClearing.Messages?.LastOrDefault()?.Text ?? string.Empty);
    }

    [Fact(Skip = SkipReason)]
    public async Task DoesNotLeakMemoriesAcrossAgentScopesAsync()
    {
        // Arrange
        var question = new ChatMessage(ChatRole.User, "What is your name?");
        var assistantIntro = new ChatMessage(ChatRole.Assistant, "I'm an AI tutor and my name is Caoimhe.");
        var storageScope1 = new Mem0ProviderScope { AgentId = "it-agent-a" };
        var storageScope2 = new Mem0ProviderScope { AgentId = "it-agent-b" };
        var mockSession1 = new TestAgentSession();
        var mockSession2 = new TestAgentSession();
        var sut1 = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope1));
        var sut2 = new Mem0Provider(this._httpClient, _ => new Mem0Provider.State(storageScope2));

        await sut1.ClearStoredMemoriesAsync(mockSession1);
        await sut2.ClearStoredMemoriesAsync(mockSession2);

        var ctxBefore1 = await sut1.InvokingAsync(new AIContextProvider.InvokingContext(s_mockAgent, mockSession1, new AIContext { Messages = new List<ChatMessage> { question } }));
        var ctxBefore2 = await sut2.InvokingAsync(new AIContextProvider.InvokingContext(s_mockAgent, mockSession2, new AIContext { Messages = new List<ChatMessage> { question } }));
        Assert.DoesNotContain("Caoimhe", ctxBefore1.Messages?.LastOrDefault()?.Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxBefore2.Messages?.LastOrDefault()?.Text ?? string.Empty);

        // Act
        await sut1.InvokedAsync(new AIContextProvider.InvokedContext(s_mockAgent, mockSession1, [assistantIntro], []));
        var ctxAfterAdding1 = await GetContextWithRetryAsync(sut1, mockSession1, question);
        var ctxAfterAdding2 = await GetContextWithRetryAsync(sut2, mockSession2, question);

        // Assert
        Assert.Contains("Caoimhe", ctxAfterAdding1.Messages?.LastOrDefault()?.Text ?? string.Empty);
        Assert.DoesNotContain("Caoimhe", ctxAfterAdding2.Messages?.LastOrDefault()?.Text ?? string.Empty);

        // Cleanup
        await sut1.ClearStoredMemoriesAsync(mockSession1);
        await sut2.ClearStoredMemoriesAsync(mockSession2);
    }

    private static async Task<AIContext> GetContextWithRetryAsync(Mem0Provider provider, AgentSession session, ChatMessage question, int attempts = 5, int delayMs = 1000)
    {
        AIContext? ctx = null;
        for (int i = 0; i < attempts; i++)
        {
            ctx = await provider.InvokingAsync(new AIContextProvider.InvokingContext(s_mockAgent, session, new AIContext { Messages = new List<ChatMessage> { question } }), CancellationToken.None);
            var text = ctx.Messages?.LastOrDefault()?.Text;
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

    private sealed class TestAgentSession : AgentSession
    {
        public TestAgentSession()
        {
            this.StateBag = new AgentSessionStateBag();
        }
    }
}
